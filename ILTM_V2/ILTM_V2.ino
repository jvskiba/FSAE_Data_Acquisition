#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include <TinyGPSPlus.h>
#include <map>
#include <functional>
#include <mcp_can.h>

#include "NTP_Client.h"
#include "DataLogger.h"
#include "SerialTcpBridge.h"
#include "config.h"

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D3
#define CAN_SCK  D4
#define CAN_MISO D6
#define CAN_MOSI D5

#define RS232_RX D9
#define RS232_TX D10

// ---- Config ----
WiFiUDP udp;
LoggerConfig config = defaultConfig;
DataLogger logger;

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

bool runECUBridge = false;

WiFiServer server(config.tcpPort);
WiFiClient client;

// One entry per defaultSignals[i]
SignalValue signalValues[defaultSignalCount_T];

MCP_CAN CAN(CAN_CS);

HardwareSerial GPSSerial(1);
//portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

using MessageHandler = std::function<void(const JsonDocument&)>;
std::map<String, MessageHandler> messageHandlers;

// Create bridge object (Serial2 -> WiFi TCP)
SerialTcpBridge ecuBridge(
    Serial2,
    RS232_RX,     // RX pin
    RS232_TX,    // TX pin
    115200, // baud
    &client,
    512,    // buffer size
    2000    // flush interval (µs)
);

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
float decodeCanSignal(CanSignal sig, const uint8_t* data) {
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
        return (signed_val * sig.mult) / sig.div;
    } else {
        return (raw * sig.mult) / sig.div;
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

    // linear fit between 0V→val_0v and 3.3V→val_3v
    float slope = (defaultSignals_Analogue[i].val_3v - defaultSignals_Analogue[i].val_0v) / 4095;
    float fittedValue = defaultSignals_Analogue[i].val_0v + slope * rawADC;

    // store into signalValues (assuming same ordering)
    size_t signalIndex = defaultSignalCount + i; // offset for analog signals
    signalValues[signalIndex].value = fittedValue;
    signalValues[signalIndex].recent = true;
  }
}

// Initialize the state at boot
void initSignalValues() {
  // ----- CAN Signals -----
  for (size_t i = 0; i < defaultSignalCount; ++i) {
    signalValues[i].name  = defaultSignals[i].name;
    signalValues[i].value = NAN;
    signalValues[i].recent = false;
  }

  // ----- Analogue Signals -----
  for (size_t i = 0; i < defaultSignalCount_Analogue; ++i) {
    size_t idx = defaultSignalCount + i;
    signalValues[idx].name  = defaultSignals_Analogue[i].name;
    signalValues[idx].value = NAN;
    signalValues[idx].recent = false;
  }

  // ----- GPS Signals -----
  for (size_t i = 0; i < defaultSignalCount_GPS; ++i) {
    size_t idx = defaultSignalCount + defaultSignalCount_Analogue + i;
    signalValues[idx].name  = defaultSignals_GPS[i].name;
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
    doc["ntp_delay"] = ntp.get_delay_us();
    //doc["timestamp"] = millis();

    char buffer[128];
    size_t len = serializeJson(doc, buffer);
    udp.beginPacket(config.host, config.udpPort);
    udp.write((uint8_t*)buffer, len);
    udp.endPacket();
}

bool updateGPSValues() {
    // Access your TinyGPSPlus instance inside the NTP client
    TinyGPSPlus &gps = ntp.gps;

    if (!gps.location.isUpdated() &&
        !gps.speed.isUpdated() &&
        !gps.course.isUpdated()) {
        return false; // ✅ nothing new
    }

    size_t base = defaultSignalCount + defaultSignalCount_Analogue;

    // Lat
    if (gps.location.isValid())
        signalValues[base + 0].value = gps.location.lat();
    else
        signalValues[base + 0].value = NAN;

    // Lon
    if (gps.location.isValid())
        signalValues[base + 1].value = gps.location.lng();
    else
        signalValues[base + 1].value = NAN;

    // Heading
    if (gps.course.isValid())
        signalValues[base + 2].value = gps.course.deg();
    else
        signalValues[base + 2].value = NAN;

    // Speed (m/s or km/h? TinyGPS uses knots by default)
    if (gps.speed.isValid())
        signalValues[base + 3].value = gps.speed.knots(); // or gps.speed.kmph()
    else
        signalValues[base + 3].value = NAN;

    if (gps.satellites.isValid())
        signalValues[base + 4].value = gps.satellites.value(); // or gps.speed.kmph()
    else
        signalValues[base + 4].value = NAN;

    // Mark data as recent
    signalValues[base + 0].recent = true;
    signalValues[base + 1].recent = true;
    signalValues[base + 2].recent = true;
    signalValues[base + 3].recent = true;
    signalValues[base + 4].recent = true;

    return true; // ✅ new GPS data ready
}


// Logger Helper Functions
String buildCSV(size_t startIndex, size_t count) {
    String data = "";
    for (size_t i = 0; i < count; ++i) {
        float value = signalValues[startIndex + i].value;
        signalValues[startIndex + i].recent = false;  // mark consumed

        data += String(value, 3);
        if (i < count - 1)
            data += ",";
    }
    return data;
}

String getCANData() {
    return buildCSV(0, defaultSignalCount);
}

String getAnalogueData() {
    readAnalogueSignals();   // required before reading
    return buildCSV(defaultSignalCount, defaultSignalCount_Analogue);
}

String getGPSData() {
    if (!updateGPSValues()) {
        return "";  // ✅ no new data
    }

    size_t base = defaultSignalCount + defaultSignalCount_Analogue;

    return buildCSV(base, defaultSignalCount_GPS);
}



template <typename T>
String makeHeaderFromSignals(const T* signals, size_t count) {
    String header = "";
    for (size_t i = 0; i < count; i++) {
        header += signals[i].name;
        if (i < count - 1) header += ",";
    }
    return header;
}

long long now_us() {
    return ntp.now_us();
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

void setMessageHandlers() {
  messageHandlers["SYNC_RESP"] = [&](const JsonDocument& msg) {
    ntp.handleMessage(msg);
  };

  messageHandlers["COMMAND"] = [](const JsonDocument& msg) {
    String cmd = msg["cmd"];
    Serial.printf("Executing command: %s\n", cmd.c_str());
    if (cmd == "Start_Log") {
      logger.endLog();
      logger.startNewLog();
    } else if (cmd == "Start_ECU_Bridge") {
      runECUBridge = true;
    } else if (cmd == "Stop_ECU_Bridge") {
      runECUBridge = false;
    }
  };
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

  setMessageHandlers();
  
  String canHeader = makeHeaderFromSignals(defaultSignals, defaultSignalCount);
  String anlgHeader = makeHeaderFromSignals(defaultSignals_Analogue, defaultSignalCount_Analogue);
  String gpsHeader = makeHeaderFromSignals(defaultSignals_GPS, defaultSignalCount_GPS);

  logger.setTimeCallback(now_us);
  logger.addSource("CAN", 10, getCANData, canHeader);
  logger.addSource("ANLG", 5, getAnalogueData, anlgHeader);
  logger.addSource("GPS", 100, getGPSData, gpsHeader);
  logger.begin("/logs", "data", SD_CS); // Needs to be LAST
  
  initSignalValues();

  ecuBridge.begin();
}

// ---- Loop ----
void loop() {
  wireless_OK = update_Wireless_Con();
  // NTP Processing
  receiveAndDispatch();
  ntp.run();

  // CAN Processing
  while (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long rxId;
    byte len = 0;
    byte rxBuf[8];
    CAN.readMsgBuf(&rxId, &len, rxBuf);
    updateSignalsFromFrame(rxId, rxBuf, len);
  }

  // Wireless Telemetry
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

  // Local Logging
  logger.update();

  // RS232 to TCP
  if (!client || !client.connected()) {
        WiFiClient newClient = server.available();
        if (newClient) {
            client = newClient;
            Serial.println("Client connected!");
        }
  }

  if (runECUBridge) {
    ecuBridge.process();
  }
}



