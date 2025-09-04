#include <SPI.h>
#include <mcp_can.h>
#include <SD.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "config.h"
#include <math.h>

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D3
#define CAN_SCK  D4
#define CAN_MISO D6
#define CAN_MOSI D5

// ==== GPS CONFIG ====
const int gpsRXPin = D0;
const int gpsTXPin = D1;
const int ppsPin = D2;

volatile uint32_t ppsMicros = 0;
volatile uint32_t ppsMicrosLast = 0;
volatile bool ppsFlag = false;

// Holds the live value for each configured signal
struct SignalValue {
  String name;
  float value;   // last decoded value
  bool recent;    // true once we've seen it at least once
};

LoggerConfig config = defaultConfig;

// ---- snapshot logging helpers ----
unsigned long lastSampleMs = 0;
const unsigned long sampleIntervalMs = 1000UL / config.sampleRateHz;
static unsigned long lastFlush = 0;
const unsigned long flushIntervalMS = 1000;

unsigned long lastHeartbeat = 0;
const unsigned long heartbeatIntervalMs = 1000;

// === Globals for Wi-Fi state tracking ===
unsigned long lastWifiAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 5000; // ms
bool wifiConnecting = false;
bool wifiReportedConnected = false;

bool wireless_OK = false;
bool can_OK = false;
bool sd_OK = false;
bool logfile_OK = false;

// One entry per defaultSignals[i]
SignalValue signalValues[defaultSignalCount];

MCP_CAN CAN(CAN_CS);
HardwareSerial GPSSerial(1);  // Use UART1

WiFiUDP udp;
TinyGPSPlus gps;
File logfile;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

// -- Interrupts --- 

void IRAM_ATTR onPPS() {
  portENTER_CRITICAL_ISR(&mux);
  ppsMicrosLast = ppsMicros;
  ppsMicros = micros();
  ppsFlag = true;
  portEXIT_CRITICAL_ISR(&mux);
}

void init_Wireless_Con() {
  Serial.println("Starting Wi-Fi connection...");
  WiFi.begin(config.ssid, config.password);
  wifiConnecting = true;
  wifiReportedConnected = false;
  lastWifiAttempt = millis();
}

// Returns true if connected, false otherwise
bool update_Wireless_Con() {
  wl_status_t status = WiFi.status();

  if (status == WL_CONNECTED) {
    if (!wifiReportedConnected) {
      Serial.println("\nWi-Fi connected!");
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
      wifiReportedConnected = true;
    }
    return true;  // safe to transmit
  }

  // If not connected, reset flag and retry every interval
  wifiReportedConnected = false;

  if (millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    Serial.println("Wi-Fi disconnected, retrying...");
    WiFi.disconnect();
    WiFi.begin(config.ssid, config.password);
    lastWifiAttempt = millis();
  }

  return false; // not connected yet
}


void init_Sockets() {
  // start UDP
  udp.begin(config.udpPort); // opens local port (can be any, or same as udpPort)
  Serial.println("UDP socket opened");
}

// Initialize the state at boot
void initSignalValues() {
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    signalValues[i].name  = defaultSignals[i].name;
    signalValues[i].value = NAN;
    signalValues[i].recent = false;
  }
}

void transmit_telem() {
  // send UDP packet
  udp.beginPacket(config.host, config.udpPort);
  udp.print("1, ");
  udp.print(millis());
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    udp.print(",");
    if (signalValues[i].recent) {
      udp.print(signalValues[i].value, 6);
    } else {
      if (defaultConfig.useNaNForMissing) udp.print("nan");
      else udp.print(signalValues[i].value, 6); // last-known (initially NAN)
    }
  }
  udp.println();
  udp.endPacket();
}

void transmit_heartbeat() {
  // send UDP packet
  udp.beginPacket(config.host, config.udpPort);
  udp.print("0, ");
  udp.print(millis());
  udp.println();
  udp.endPacket();
}

// Decode raw bytes from a CAN payload per CanSignal
double decodeCanSignal(CanSignal sig, const uint8_t* data) {
    uint32_t raw = 0;

    // Extract raw value (endian-aware)
    if (sig.littleEndian) {
        for (int i = 0; i < sig.length; i++) {
            raw |= (data[sig.startByte + i] << (8 * i));
        }
    } else {
        for (int i = 0; i < sig.length; i++) {
            raw = (raw << 8) | data[sig.startByte + i];
        }
    }

    // Handle signed vs unsigned
    int32_t signed_val = 0;
    if (sig.is_signed) {
        switch (sig.length) {
            case 1:
                signed_val = (int8_t) raw;
                break;
            case 2:
                signed_val = (int16_t) raw;
                break;
            case 4:
                signed_val = (int32_t) raw;
                break;
            default:
                signed_val = (int32_t) raw;
        }
        return signed_val * sig.scale + sig.offset;
    } else {
        return raw * sig.scale + sig.offset;
    }
}



// Apply an incoming frame to the signals table
void updateSignalsFromFrame(uint32_t rxId, const uint8_t* rxBuf, uint8_t rxLen) {
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    const CanSignal& s = defaultSignals[i];
    if (s.canId != rxId) continue;

    // bounds check: skip if the bytes we need aren't in this frame
    if ((int)s.startByte + (int)s.length > rxLen) continue;

    const float v = decodeCanSignal(s, rxBuf);
    signalValues[i].value = v;
    signalValues[i].recent = true;
  }
}

void writeCsvHeaderIfNeeded(File& f) {
  static bool wrote = false;
  if (wrote) return;
  f.print("Time_ms");
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    f.print(",");
    f.print(signalValues[i].name);
  }
  f.println();
  f.flush();
  wrote = true;
}

void writeSnapshotRow(File& f) {
  f.print(millis());
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    f.print(",");
    if (signalValues[i].recent) {
      f.print(signalValues[i].value, 6);
    } else {
      if (defaultConfig.useNaNForMissing) f.print("nan");
      else f.print(signalValues[i].value, 6); // last-known (initially NAN)
    }
  }
  f.println();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Booting...");
  pinMode(ppsPin, INPUT);

  attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS, RISING);
  GPSSerial.begin(9600, SERIAL_8N1, gpsRXPin, gpsTXPin);

  // --- Init SPI for both devices ---
  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);

  // --- Init CAN ---
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");
    can_OK = true;
    CAN.setMode(MCP_NORMAL);
    // Init Can Filtering
    /*
    CAN.init_Mask(0, 0, 0x7FF);     // Mask 0 (all bits must match)
    CAN.init_Filt(0, 0, 0x100);     // Accept ID 0x100
    */
    CAN.init_Mask(0, 0, 0x000);  // 0x000 mask = accept all IDs
    CAN.init_Filt(0, 0, 0x000);  // doesn't matter
    } else {
      Serial.println("Error Initializing MCP2515...");
    }

  // --- Init SD card ---
  if (!SD.begin(SD_CS)) {
    Serial.println("Card Mount Failed");
  } else {
    Serial.println("SD card initialized.");
    sd_OK = true;

    // Open log file (append mode)
    logfile = SD.open("/canlog.txt", FILE_APPEND);
    if (!logfile) {
      Serial.println("Failed to open log file");
    } else {
      Serial.println("Logging to /canlog.txt");
      logfile_OK = true;
    }
  }

  init_Wireless_Con();

  initSignalValues();
  if (logfile_OK) {writeCsvHeaderIfNeeded(logfile);}
}

void loop() {
  while (GPSSerial.available() > 0) {
    char c = GPSSerial.read();
    gps.encode(c);
  }

  wireless_OK = update_Wireless_Con();

  if (ppsFlag && gps.time.isUpdated()) {
    portENTER_CRITICAL(&mux);
    uint32_t interval = ppsMicros - ppsMicrosLast;
    ppsFlag = false;
    portEXIT_CRITICAL(&mux);
    Serial.printf("%lu\n", interval);
  }

  while (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long rxId;
    byte len = 0;
    byte rxBuf[8];
    CAN.readMsgBuf(&rxId, &len, rxBuf);
    updateSignalsFromFrame(rxId, rxBuf, len);
  }

  if (millis() - lastSampleMs >= sampleIntervalMs) {
    lastSampleMs += sampleIntervalMs;
    
    if (wireless_OK) {
      transmit_telem();

      if (millis() - lastHeartbeat >= heartbeatIntervalMs) {
        lastHeartbeat = millis();
        transmit_heartbeat();
      }
    }

    if (logfile_OK) { 
      writeSnapshotRow(logfile);
      if (millis() - lastFlush > flushIntervalMS) { 
        logfile.flush(); 
        lastFlush = millis(); 
      }
    }

    for (size_t i = 0; i < defaultSignalCount; ++i) {
      signalValues[i].recent = false;
    }
  }
}