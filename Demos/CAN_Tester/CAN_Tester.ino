#include <mcp_can.h>
#include <SPI.h>

// --- PINS ---
#define CAN_CS   4
#define CAN_INT  37
#define CAN_SCK  5
#define CAN_MISO 21
#define CAN_MOSI 19

MCP_CAN CAN(CAN_CS);

void setup() {
  Serial.begin(115200);
  delay(2000);

  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI, CAN_CS);

  Serial.println("Starting CAN Node...");

  pinMode(CAN_CS, OUTPUT);
  digitalWrite(CAN_CS, HIGH);
  delay(10);

  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");
  } else {
    Serial.println("Error Initializing MCP2515...");
    while (1);
  }

  // Accept everything
  CAN.init_Mask(0, 0, 0x0000);
  CAN.init_Mask(1, 1, 0x00000000);

  for (byte i = 0; i < 6; i++) {
    CAN.init_Filt(i, 0, 0x0000);
  }

  CAN.setMode(MCP_NORMAL);  // Real CAN communication
  Serial.println("CAN in NORMAL mode");
}

void loop() {
  static unsigned long lastSend = 0;

  // --- SEND every 1 second ---
  if (millis() - lastSend > 1000) {
    lastSend = millis();

    byte data[8] = {0,1,2,3,4,5,6,7};

    byte status = CAN.sendMsgBuf(0x123, 0, 8, data);

    if (status == CAN_OK) {
      Serial.println("TX: Sent ID 0x123");
    } else {
      Serial.println("TX: Failed");
    }
  }

  // --- RECEIVE ---
  if (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long id;
    byte len;
    byte buf[8];

    CAN.readMsgBuf(&id, &len, buf);

    Serial.print("RX ID: 0x");
    Serial.println(id, HEX);

    Serial.print("Data: ");
    for (byte i = 0; i < len; i++) {
      Serial.print(buf[i]);
      Serial.print(" ");
    }
    Serial.println("\n---");
  }
}