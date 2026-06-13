#include <HardwareSerial.h>

HardwareSerial RYLR(2);  // UART2

unsigned long seq = 0;
String addition = "";

void sendAT(String cmd, bool print = true) {
  RYLR.println(cmd);

  if (print) {
    Serial.print(">> "); Serial.println(cmd);
  }
}

void setup() {
  Serial.begin(115200);
  RYLR.begin(115200, SERIAL_8N1, D10, D9);

  delay(1000);
  Serial.println("Init RYLR998...");

  sendAT("AT"); delay(200);
  sendAT("AT+RESET"); delay(500);
  String resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);
  sendAT("AT+ADDRESS=1");
  resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);
  sendAT("AT+NETWORKID=18");
  resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);
  sendAT("AT+BAND=915000000");
  resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);
  sendAT("AT+PARAMETER=7,9,1,8");
  resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);

  addition += "BB234567A1234567A1234567A1234567";
  addition += "BB234567A1234567A1234567A1234567";
}

void loop() {
  unsigned long t0 = micros();

  if (seq%150 == 0) {
    //addition += "BB234567A1234567A1234567A1234567";
  }
  String payload = "SEQ=" + String(seq) + "=A1234567A1234567A1234567" + addition;
  int len = payload.length();

  String cmd = "AT+SEND=2," + String(len) + "," + payload;
  sendAT(cmd);

  // Wait for response
  String resp = RYLR.readStringUntil('\n');
  resp.trim();
  if (resp.length()) Serial.println("<< " + resp);

  unsigned long t1 = micros();
  float dt_ms = (t1 - t0) / 1000.0;

  Serial.printf("Packet %lu sent in %.2f ms\n", seq, dt_ms);

  seq++;  
}
