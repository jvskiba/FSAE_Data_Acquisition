#include <WiFi.h>
#include "SerialTcpBridge.h"

const char* SSID = "JvS Wifi";
const char* PASS = "alllowercase";
const uint16_t TCP_PORT = 2000;

WiFiServer server(TCP_PORT);
WiFiClient client;

// Create bridge object (Serial2 -> WiFi TCP)
SerialTcpBridge ecuBridge(
    Serial2,
    D9,     // RX pin
    D10,    // TX pin
    115200, // baud
    &client,
    512,    // buffer size
    2000    // flush interval (µs)
);

void setup() {
    Serial.begin(115200);

    // Connect WiFi
    WiFi.begin(SSID, PASS);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("WiFi connected.");

    server.begin();
    server.setNoDelay(true);

    ecuBridge.begin();
}

void loop() {
    // Replace the client if a new one connects
    if (!client || !client.connected()) {
        WiFiClient newClient = server.available();
        if (newClient) {
            client = newClient;
            Serial.println("Client connected!");
        }
    }

    ecuBridge.process(); // 🚀 Do all the heavy lifting
}
