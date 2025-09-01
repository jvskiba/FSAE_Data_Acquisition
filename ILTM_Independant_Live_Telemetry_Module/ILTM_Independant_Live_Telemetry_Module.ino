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

unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 10000; // ms

// Holds the live value for each configured signal
struct SignalValue {
  String name;
  float value;   // last decoded value
  bool valid;    // true once we've seen it at least once
};

LoggerConfig config = defaultConfig;

// ---- 100 Hz snapshot logging helpers ----
unsigned long lastSampleMs = 0;
const unsigned long sampleIntervalMs = 1000UL / config.sampleRateHz;


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
  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(config.ssid, config.password);
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWi-Fi connected!");
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
  }
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
    signalValues[i].valid = false;
  }
}

void transmit_telem() {
  // send UDP packet
  udp.beginPacket(config.host, config.udpPort);
  udp.print(millis());
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    udp.print(",");
    if (signalValues[i].valid) {
      udp.print(signalValues[i].value, 6);
    } else {
      if (defaultConfig.useNaNForMissing) udp.print("nan");
      else udp.print(signalValues[i].value, 6); // last-known (initially NAN)
    }
  }
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
    signalValues[i].valid = true;
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
    if (signalValues[i].valid) {
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
  pinMode(ppsPin, INPUT);

  attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS, RISING);
  GPSSerial.begin(9600, SERIAL_8N1, gpsRXPin, gpsTXPin);

  // --- Init SPI for both devices ---
  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);

  // --- Init CAN ---
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");
  } else {
    Serial.println("Error Initializing MCP2515...");
    while (1);
  }
  CAN.setMode(MCP_NORMAL);

  // --- Init SD card ---
  if (!SD.begin(SD_CS)) {
    Serial.println("Card Mount Failed");
    while (1);
  }
  Serial.println("SD card initialized.");

  // Open log file (append mode)
  logfile = SD.open("/canlog.txt", FILE_APPEND);
  if (!logfile) {
    Serial.println("Failed to open log file");
    while (1);
  }
  Serial.println("Logging to /canlog.txt");

  // Init Can Filtering
  /*
  CAN.init_Mask(0, 0, 0x7FF);     // Mask 0 (all bits must match)
  CAN.init_Filt(0, 0, 0x100);     // Accept ID 0x100
  */
  CAN.init_Mask(0, 0, 0x000);  // 0x000 mask = accept all IDs
  CAN.init_Filt(0, 0, 0x000);  // doesn't matter

  init_Wireless_Con();

  initSignalValues();
  writeCsvHeaderIfNeeded(logfile);
}

void loop() {
  while (GPSSerial.available() > 0) {
    char c = GPSSerial.read();
    gps.encode(c);
  }

  if (ppsFlag && gps.time.isUpdated()) {
    portENTER_CRITICAL(&mux);
    uint32_t interval = ppsMicros - ppsMicrosLast;
    ppsFlag = false;
    portEXIT_CRITICAL(&mux);
    Serial.printf("%lu\n", interval);
  }

  String payload = String(millis()) + ", testdata";

  if (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long rxId;
    byte len = 0;
    byte rxBuf[8];
    CAN.readMsgBuf(&rxId, &len, rxBuf);
    updateSignalsFromFrame(rxId, rxBuf, len);
  }

  // 100 Hz snapshot
  if (millis() - lastSampleMs >= sampleIntervalMs) {
    lastSampleMs += sampleIntervalMs;
    writeSnapshotRow(logfile);
    transmit_telem();
    // (optional) also stream the same CSV row over UDP here
    static unsigned long lastFlush = 0;
    if (millis() - lastFlush > 1000) { logfile.flush(); lastFlush = millis(); }
  }
}