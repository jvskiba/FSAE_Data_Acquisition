#include <mcp_can.h>
#include <SPI.h>

// --- PINS ---
#define CAN_CS   D7
#define CAN_INT  D3
#define CAN_SCK  D4
#define CAN_MISO D6
#define CAN_MOSI D5

MCP_CAN CAN(CAN_CS);

void setup() {
  Serial.begin(115200);
  delay(2000);
  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);

  Serial.println("Starting CAN Sniffer...");

  // Initialize MCP2515 @ 500 kbps with 8 MHz crystal
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");

    // Listen-only mode (safe with single node)
    CAN.setMode(MCP_LISTENONLY);

    // --- ACCEPT ALL STANDARD IDs ---
    CAN.init_Mask(0, 0, 0x0000); // mask 0, standard
    for (byte i = 0; i < 6; i++) CAN.init_Filt(i, 0, 0x0000);

    // --- ACCEPT ALL EXTENDED IDs ---
    CAN.init_Mask(1, 1, 0x00000000); // mask 1, extended
    for (byte i = 0; i < 6; i++) CAN.init_Filt(i, 1, 0x00000000);

    Serial.println("Filters set: accept all STD + EXT IDs");
  } else {
    Serial.println("Error Initializing MCP2515...");
    while (1);
  }
}

void loop() {
  if (CAN.checkReceive() == CAN_MSGAVAIL) {
    unsigned long canId;
    byte len;
    byte buf[8];

    CAN.readMsgBuf(&canId, &len, buf);

    // --- Determine type ---
    if (canId > 0x7FF) Serial.print("EXT ");
    else Serial.print("STD ");

    // --- Print ID ---
    Serial.print("ID: 0x");
    Serial.print(canId, HEX);

    // --- Check for RTR ---
    if (len == 0) Serial.print(" RTR");

    // --- Print DLC ---
    Serial.print("  DLC: "); Serial.print(len);

    // --- Print data bytes ---
    if (len > 0) {
      Serial.print("  Data: ");
      for (byte i = 0; i < len; i++) {
        if (buf[i] < 0x10) Serial.print("0");
        Serial.print(buf[i], HEX);
        Serial.print(" ");
      }
    }

    Serial.println();
  }
}
