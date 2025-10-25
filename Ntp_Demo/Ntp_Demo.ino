#include <WiFi.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>
#include "NTP_Client.h"
#include <TinyGPSPlus.h>


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

volatile uint32_t ppsMicros = 0;
volatile uint32_t ppsMicrosLast = 0;
volatile bool ppsFlag = false;
volatile long long ntpMicros = 0;
volatile long long ntpMicrosLast = 0;

HardwareSerial GPSSerial(1);
TinyGPSPlus gps;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

// Forward declarations
void send(StaticJsonDocument<128> &doc);
bool receive(StaticJsonDocument<256> &resp);

// Create NTP client
NTP_Client ntp(send, receive, gps);



// ---- Send function ----
void send(StaticJsonDocument<128> &doc) {
  char buffer[128];
  size_t len = serializeJson(doc, buffer);

  udp.beginPacket(server_ip, server_port);
  udp.write((uint8_t*)buffer, len);
  udp.endPacket();
}

// ---- Receive function ----
bool receive(StaticJsonDocument<256>& resp) {
    int packetSize = udp.parsePacket();
    if (!packetSize) return false;

    char buf[256];
    int len = udp.read(buf, sizeof(buf) - 1);
    buf[len] = 0;

    DeserializationError err = deserializeJson(resp, buf);
    if (err) return false;

    return resp["type"] == "SYNC_RESP";
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

  GPSSerial.begin(9600, SERIAL_8N1, gpsRXPin, gpsTXPin);

  pinMode(ppsPin, INPUT);
  ntp.begin(ppsPin);
}

// ---- Loop ----
void loop() {
  ntp.run();

  while (GPSSerial.available() > 0) {
    char c = GPSSerial.read();
    gps.encode(c);
  }

  // Print diagnostics every 1 second
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 1000) {
    lastPrint = millis();
    //printGPSStatus();
  }
}



