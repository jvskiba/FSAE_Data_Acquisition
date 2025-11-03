#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include "NTP_Client.h"
#include <TinyGPSPlus.h>
#include <map>
#include <functional>
#include "config.h"
#include <mcp_can.h>

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D3
#define CAN_SCK  D4
#define CAN_MISO D6
#define CAN_MOSI D5

// ---- Config ----
WiFiUDP udp;
LoggerConfig config = defaultConfig;

// ==== GPS CONFIG ====
const int gpsRXPin = D0;
const int gpsTXPin = D1;
const int ppsPin = D2;

bool wireless_OK = false;
bool can_OK = false;
bool sd_OK = false;
bool logfile_OK = false;

// === Globals for Wi-Fi state tracking ===
unsigned long lastWifiAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 5000; // ms
bool wifiConnecting = false;
bool wifiReportedConnected = false;

unsigned long lastHeartbeat = 0;
const unsigned long heartbeatIntervalMs = 1000;

struct SignalValue {
  String name;
  float value;   // last decoded value
  bool recent;    // true once we've seen it at least once
};

unsigned long lastReadTime = 0;
const unsigned long readInterval = 1000; // 1 second

// ---- snapshot logging helpers ----
unsigned long lastSampleMs = 0;
const unsigned long sampleIntervalMs = 1000UL / config.sampleRateHz;
unsigned long lastTelemMs = 0;
const unsigned long telemIntervalMs = 1000UL / config.telemRateHz;
static unsigned long lastFlush = 0;
const unsigned long flushIntervalMS = 1000;

// One entry per defaultSignals[i]
SignalValue signalValues[defaultSignalCount+defaultSignalCount_Analogue];

MCP_CAN CAN(CAN_CS);

HardwareSerial GPSSerial(1);
//portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

using MessageHandler = std::function<void(const JsonDocument&)>;
std::map<String, MessageHandler> messageHandlers;

// Forward declarations
void send(StaticJsonDocument<128> &doc);

// Create NTP client
NTP_Client ntp(send);

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

// ---- Send function ----
void send(StaticJsonDocument<128> &doc) {
  char buffer[128];
  size_t len = serializeJson(doc, buffer);

  udp.beginPacket(config.host, config.udpPort);
  udp.write((uint8_t*)buffer, len);
  udp.endPacket();
}

void receiveAndDispatch() {
    if (!udp.parsePacket()) return;

    char buf[256];
    int len = udp.read(buf, sizeof(buf) - 1);
    buf[len] = 0;

    StaticJsonDocument<256> msg;
    DeserializationError err = deserializeJson(msg, buf);
    if (err) {
        Serial.println("JSON parse error");
        return;
    }

    String type = msg["type"].as<String>();
    if (type.length() == 0) {
        Serial.println("No message type");
        return;
    }

    if (messageHandlers.count(type)) {
        messageHandlers[type](msg);
    } else {
        Serial.printf("Unhandled message type: %s\n", type.c_str());
    }
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

void readAnalogueSignals() {
  for (size_t i = 0; i < defaultSignalCount_Analogue; ++i) {
    int rawADC = analogRead(defaultSignals_Analogue[i].pin); // read from A0, A1, A2... by index
    float voltage = rawADC * (3.3 / 1023.0); // convert ADC to voltage

    // linear fit between 0V→val_0v and 3.3V→val_3v
    float slope = (defaultSignals_Analogue[i].val_3v - defaultSignals_Analogue[i].val_0v) / 3.3;
    float fittedValue = defaultSignals_Analogue[i].val_0v + slope * voltage;

    // store into signalValues (assuming same ordering)
    size_t signalIndex = defaultSignalCount + i; // offset for analog signals
    signalValues[signalIndex].value = fittedValue;
    signalValues[signalIndex].recent = true;
  }
}

// Initialize the state at boot
void initSignalValues() {
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    signalValues[i].name  = defaultSignals[i].name;
    signalValues[i].value = NAN;
    signalValues[i].recent = false;
  }
  for (size_t i = 0; i < defaultSignalCount_Analogue; ++i) {
    size_t idx = defaultSignalCount + i; // offset into signalValues
    signalValues[idx].name  = defaultSignals_Analogue[i].name;
    signalValues[idx].value = NAN;
    signalValues[idx].recent = false;
  }
}

// Send telemetry as JSON
void transmit_telem() {
    StaticJsonDocument<2048> doc;  // adjust size if you have many signals
    doc["type"] = "TELEMETRY";
    doc["timestamp"] = millis();

    JsonArray signals = doc.createNestedArray("signals");
    for (size_t i = 0; i < defaultSignalCount_T; ++i) {
        JsonObject s = signals.createNestedObject();
        s["name"] = signalValues[i].name;
        if (signalValues[i].recent) {
            s["value"] = signalValues[i].value;
        } else {
            if (defaultConfig.useNaNForMissing) {
                s["value"] = "nan";  // could also use JsonNull()
            } else {
                s["value"] = signalValues[i].value; // last known (initially NAN)
            }
        }
    }

    // Send the JSON via UDP
    char buffer[2048];
    size_t len = serializeJson(doc, buffer);
    udp.beginPacket(config.host, config.udpPort);
    udp.write((uint8_t*)buffer, len);
    udp.endPacket();
}

// Send heartbeat as JSON
void transmit_heartbeat() {
    StaticJsonDocument<128> doc;
    doc["type"] = "HEARTBEAT";
    doc["timestamp"] = millis();

    char buffer[128];
    size_t len = serializeJson(doc, buffer);
    udp.beginPacket(config.host, config.udpPort);
    udp.write((uint8_t*)buffer, len);
    udp.endPacket();
}


// --- PRINT FUNCTION ---
void printSignalValues() {
  Serial.println("--- Signal Values ---");
  for (size_t i = 0; i < defaultSignalCount_T; ++i) {
    Serial.print(signalValues[i].name);
    Serial.print(": ");
    Serial.println(signalValues[i].value, 2); // print with 2 decimal places
  }
  Serial.println();
}

// ---- Setup ----
void setup() {
  Serial.begin(115200);
  Serial.println("Boot reason: " + String(esp_reset_reason()));
  delay(1000);

  init_Wireless_Con();
  init_Sockets();

  ntp.attachSerial(&GPSSerial, 9600, gpsRXPin, gpsTXPin);
  ntp.begin(ppsPin);

  messageHandlers["SYNC_RESP"] = [&](const JsonDocument& msg) {
    ntp.handleMessage(msg);
  };

  messageHandlers["COMMAND"] = [](const JsonDocument& msg) {
    String cmd = msg["cmd"];
    Serial.printf("Executing command: %s\n", cmd.c_str());
  };
  
  initSignalValues();
}

// ---- Loop ----
void loop() {
  receiveAndDispatch();
  ntp.run();
  wireless_OK = update_Wireless_Con();
  unsigned long currentTime = millis();
  if (currentTime - lastReadTime >= readInterval) {
    lastReadTime = currentTime;

    readAnalogueSignals();
    //printSignalValues();
  }

  while (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long rxId;
    byte len = 0;
    byte rxBuf[8];
    CAN.readMsgBuf(&rxId, &len, rxBuf);
    updateSignalsFromFrame(rxId, rxBuf, len);
  }

  if (wireless_OK) {
    if (millis() - lastTelemMs >= telemIntervalMs) {
      lastTelemMs += telemIntervalMs;
      transmit_telem();
    }

    if (millis() - lastHeartbeat >= heartbeatIntervalMs) {
      lastHeartbeat = millis();
      transmit_heartbeat();
    }
  }

  if (millis() - lastSampleMs >= sampleIntervalMs) {
    lastSampleMs += sampleIntervalMs;
    /*
    if (logfile_OK) { 
      writeSnapshotRow(logfile);
      if (millis() - lastFlush > flushIntervalMS) { 
        logfile.flush(); 
        lastFlush = millis(); 
      }
    }
    */

    for (size_t i = 0; i < defaultSignalCount; ++i) {
      signalValues[i].recent = false;
    }
  }
}



