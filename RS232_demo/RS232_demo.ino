#include <WiFi.h>  // Use the ESP32 WiFi library

// === Wi-Fi credentials ===
const char* SSID = "JvS Wifi";
const char* PASS = "alllowercase";

// === Configuration ===
const uint16_t TCP_PORT = 2000;
const uint32_t ECU_BAUD = 115200;
const uint32_t FLUSH_INTERVAL_US = 2000; // Flush every BLANKms max
const size_t BUFFER_SIZE = 512; 

// === Network objects ===
WiFiServer server(TCP_PORT);
WiFiClient client;

// === Serial pins (adjust for your wiring) ===
// Example: Using Serial2 for ECU (pins 16 = RX2, 17 = TX2 on most ESP32 boards)
#define ECU_RX D9
#define ECU_TX D10

// === Buffers ===
uint8_t uartBuffer[BUFFER_SIZE];
uint8_t tcpBuffer[BUFFER_SIZE];
size_t uartPos = 0;
size_t tcpPos = 0;
unsigned long lastFlushUs = 0;

void setup() {
  Serial.begin(115200);  // USB serial to laptop
  delay(1000);

  // Start ECU serial
  Serial2.begin(ECU_BAUD, SERIAL_8N1, ECU_RX, ECU_TX);
  Serial.println("\nESP32 Serial–TCP Bridge Starting...");

  // Connect Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASS);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ Wi-Fi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // Start TCP server
  server.begin();
  server.setNoDelay(true);
  Serial.printf("📡 TCP server started on port %d\n", TCP_PORT);
}

void loop() {
  // Handle client connection
  if (!client || !client.connected()) {
    WiFiClient newClient = server.available();
    if (newClient) {
      client = newClient;
      Serial.println("🔌 Client connected!");
    }
  }

  // === ECU → TCP + USB buffer ===
  while (Serial2.available() && uartPos < BUFFER_SIZE) {
    uartBuffer[uartPos++] = Serial2.read();
  }

  // === TCP → ECU buffer ===
  if (client && client.connected()) {
    while (client.available() && tcpPos < BUFFER_SIZE) {
      tcpBuffer[tcpPos++] = client.read();
    }
  }

  unsigned long nowUs = micros();

  // === Flush conditions ===
  if (uartPos >= BUFFER_SIZE || tcpPos >= BUFFER_SIZE || (nowUs - lastFlushUs) > FLUSH_INTERVAL_US) {
    if (uartPos > 0) {
      if (client && client.connected())
        client.write(uartBuffer, uartPos); // burst send
      Serial.write(uartBuffer, uartPos);   // mirror to USB
      uartPos = 0;
    }

    if (tcpPos > 0) {
      Serial2.write(tcpBuffer, tcpPos);
      Serial.write(tcpBuffer, tcpPos);     // mirror to USB
      tcpPos = 0;
    }

    lastFlushUs = nowUs;
  }
}