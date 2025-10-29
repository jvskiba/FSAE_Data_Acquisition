#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include "NTP_Client.h"
#include <TinyGPSPlus.h>
#include <map>
#include <functional>

// ---- Config ----
WiFiUDP udp;

const char* ssid     = "FBI_Safehouse";
const char* password = "icanttellyou";
const char* server_ip = "192.168.1.207";
const int server_port = 5000;

// ==== GPS CONFIG ====
const int gpsRXPin = D0;
const int gpsTXPin = D1;
const int ppsPin = D2;

HardwareSerial GPSSerial(1);
//portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

using MessageHandler = std::function<void(const JsonDocument&)>;
std::map<String, MessageHandler> messageHandlers;

// Forward declarations
void send(StaticJsonDocument<128> &doc);

// Create NTP client
NTP_Client ntp(send);

// ---- Send function ----
void send(StaticJsonDocument<128> &doc) {
  char buffer[128];
  size_t len = serializeJson(doc, buffer);

  udp.beginPacket(server_ip, server_port);
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

// ---- Setup ----
void setup() {
  Serial.begin(115200);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  udp.begin(WiFi.localIP(), server_port);

  ntp.attachSerial(&GPSSerial, 9600, gpsRXPin, gpsTXPin);
  ntp.begin(ppsPin);

  messageHandlers["SYNC_RESP"] = [&](const JsonDocument& msg) {
    ntp.handleMessage(msg);
  };

  messageHandlers["GPS_DATA"] = [](const JsonDocument& msg) {
    Serial.printf("GPS: %.6f, %.6f\n", msg["lat"].as<double>(), msg["lon"].as<double>());
  };

  messageHandlers["COMMAND"] = [](const JsonDocument& msg) {
    String cmd = msg["cmd"];
    Serial.printf("Executing command: %s\n", cmd.c_str());
  };

}

// ---- Loop ----
void loop() {
  receiveAndDispatch();
  ntp.run();
}



