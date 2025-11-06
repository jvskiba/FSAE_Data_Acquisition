#include <mcp_can.h>

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D3
#define CAN_SCK  D4
#define CAN_MISO D6
#define CAN_MOSI D5

MCP_CAN CAN(CAN_CS);
bool can_OK = false;

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("Starting CAN Sniffer...");

  // Initialize SPI
  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);

  // Initialize MCP2515 @ 500 kbps with 8 MHz crystal
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");
    can_OK = true;

    // Set normal mode to receive CAN traffic
    CAN.setMode(MCP_NORMAL);

    // Accept all IDs (no filtering)
    CAN.init_Mask(0, 0, 0x000);
    CAN.init_Filt(0, 0, 0x000);
  } else {
    Serial.println("Error Initializing MCP2515...");
  }
}

void loop() {
  if (!can_OK) return;

  unsigned long canId;
  byte len;
  byte buf[8];

  if (CAN.checkReceive() == CAN_MSGAVAIL) {
    Serial.println("MSG");
    CAN.readMsgBuf(&canId, &len, buf);

    // --- Print CAN message ---
    Serial.print("ID: 0x");
    Serial.print(canId, HEX);
    Serial.print("  DLC: ");
    Serial.print(len);
    Serial.print("  Data: ");

    for (byte i = 0; i < len; i++) {
      if (buf[i] < 0x10) Serial.print("0");
      Serial.print(buf[i], HEX);
      Serial.print(" ");
    }
    Serial.println();
  }
}
