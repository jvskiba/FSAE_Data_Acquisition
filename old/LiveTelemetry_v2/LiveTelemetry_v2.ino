#include <WiFi.h>

// ================= CONFIG =================
const char* ssid = "JvS Wifi";
const char* password = "alllowercase";
const uint16_t TCP_PORT = 4000;

// ECU pins (hardware UART)
#define ECU_SERIAL Serial1
const int ECU_RX = 0; // example GPIO for ECU RX
const int ECU_TX = 1; // example GPIO for ECU TX

// ================= BUFFERS =================
const int BUF_SIZE = 128;
uint8_t ecuBuffer[BUF_SIZE];
uint8_t tcpBuffer[BUF_SIZE];

// ================= TCP SERVER =================
WiFiServer server(TCP_PORT);
WiFiClient client;

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  ECU_SERIAL.begin(115200, SERIAL_8N1, ECU_RX, ECU_TX);

  // Connect Wi-Fi (non-blocking loop)
  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");
}

// ================= LOOP =================
void loop() {
  // Ensure Wi-Fi is connected
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastReconnectAttempt = 0;
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 5000) { // try every 5s
      Serial.println("\nReconnecting to Wi-Fi...");
      WiFi.begin(ssid, password);
      lastReconnectAttempt = now;
    }
    return; // wait until connected
  }

  // Start server if not already
  if (!server) server.begin();

  // Accept new client if needed
  if (!client || !client.connected()) {
    client = server.available();
    if (client) Serial.println("TCP client connected");
  }

  // ================= ECU -> TCP =================
  int len = 0;
  while (ECU_SERIAL.available() && len < BUF_SIZE) {
    ecuBuffer[len++] = ECU_SERIAL.read();
  }
  if (len > 0) {
    if (client && client.connected()) client.write(ecuBuffer, len);
    Serial.write(ecuBuffer, len); // optional debug
  }

  // ================= TCP -> ECU =================
  if (client && client.connected()) {
    len = 0;
    while (client.available() && len < BUF_SIZE) {
      tcpBuffer[len++] = client.read();
    }
    if (len > 0) {
      ECU_SERIAL.write(tcpBuffer, len);
      Serial.write(tcpBuffer, len); // optional debug
    }
  }
}
