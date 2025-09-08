#include <WiFiNINA.h>   // Nano 33 IoT Wi-Fi
// Fill these however you like (config.h, NVS, etc.)
const char* SSID = "FBI_Safehouse";
const char* PASS = "icanttellyou";
const uint16_t TCP_PORT = 2000;
const uint32_t ECU_BAUD = 115200;

WiFiServer server(TCP_PORT);
WiFiClient client;

void setup() {
  Serial.begin(115200);                 // USB to laptop
  while (!Serial) { ; }                 // wait for USB (optional)
  Serial1.begin(ECU_BAUD);              // ECU on D0/D1 through HW-044

  if (WiFi.begin(SSID, PASS) != WL_CONNECTED) {
    Serial.println("WiFi connect failed");
  } else {
    Serial.print("IP: "); Serial.println(WiFi.localIP());
    server.begin();
  }
}

void loop() {
  if (!client || !client.connected()) client = server.available();

  // ECU -> TCP + USB
  while (Serial1.available()) {
    int b = Serial1.read();
    if (client && client.connected()) client.write((uint8_t)b);
    Serial.write((uint8_t)b);          // mirror to USB for logging
  }

  // TCP -> ECU
  if (client && client.connected()) {
    while (client.available()) {
      int b = client.read();
      Serial1.write((uint8_t)b);
      Serial.write((uint8_t)b);          // mirror to USB for logging
    }
  }
}
