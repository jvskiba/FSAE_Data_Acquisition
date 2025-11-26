#include <HardwareSerial.h>

HardwareSerial RYLR(2);  // UART2

void sendAT(String cmd, int delay_ms = 200) {
  RYLR.println(cmd);              // Send command with CR+LF
  Serial.print(">> "); Serial.println(cmd);
  delay(delay_ms);

  while (RYLR.available()) {
    String resp = RYLR.readStringUntil('\n');
    resp.trim();
    if (resp.length() > 0) {
      Serial.print("<< "); Serial.println(resp);
    }
  }
}

void setup() {
  Serial.begin(115200);
  RYLR.begin(115200, SERIAL_8N1, D10, D9);  // RX, TX pins on ESP32
  delay(1000);

  Serial.println("Initializing RYLR998...");

  sendAT("AT");                  // Check module
  sendAT("AT+RESET");            // Reset module
  delay(500);

  sendAT("AT+ADDRESS=1");        // Sender address
  sendAT("AT+NETWORKID=18");     // Network ID (must match receiver)
  sendAT("AT+BAND=915000000");   // Frequency
  sendAT("AT+PARAMETER=9,7,1,12"); // SF9, BW125kHz, CR1, Preamble 12
}

void loop() {
  String msg = "Hello from ESP32!";
  int msgLen = msg.length();

  String cmd = "AT+SEND=2," + String(msgLen) + "," + msg;  // Send to ADDRESS 2
  sendAT(cmd);

  delay(2000);  // Wait 2 sec between transmissions
}
