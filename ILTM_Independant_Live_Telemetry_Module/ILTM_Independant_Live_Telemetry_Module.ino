#include <SPI.h>
#include <mcp_can.h>
#include <SD.h>

// --- MCP2515 pins ---
#define CAN_CS   D6
#define CAN_INT  D2
#define CAN_SCK  D3
#define CAN_MISO D5
#define CAN_MOSI D4

MCP_CAN CAN(CAN_CS);

// --- SD card pins ---
#define SD_CS    D7

File logfile;

void setup() {
  Serial.begin(115200);
  delay(1000);

  // --- Init SPI for both devices ---
  SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);

  // --- Init CAN ---
  if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
    Serial.println("MCP2515 Initialized Successfully!");
  } else {
    Serial.println("Error Initializing MCP2515...");
    while (1);
  }
  CAN.setMode(MCP_NORMAL);

  // --- Init SD card ---
  if (!SD.begin(SD_CS)) {
    Serial.println("Card Mount Failed");
    while (1);
  }
  Serial.println("SD card initialized.");

  // Open log file (append mode)
  logfile = SD.open("/canlog.txt", FILE_APPEND);
  if (!logfile) {
    Serial.println("Failed to open log file");
    while (1);
  }
  Serial.println("Logging to /canlog.txt");

  // Init Can Filtering
  CAN.init_Mask(0, 0, 0x7FF);     // Mask 0 (all bits must match)
  CAN.init_Filt(0, 0, 0x100);     // Accept ID 0x100
}

void loop() {
  if (CAN.checkReceive() == CAN_MSGAVAIL) {
    long unsigned int rxId;
    unsigned char len = 0;
    unsigned char rxBuf[8];

    CAN.readMsgBuf(&rxId, &len, rxBuf);

    // Format log line
    String logEntry = String(millis()) + ",ID:0x" + String(rxId, HEX) + ",DLC:" + String(len) + ",Data:";
    for (int i = 0; i < len; i++) {
      if (rxBuf[i] < 0x10) logEntry += "0";
      logEntry += String(rxBuf[i], HEX);
      if (i < len - 1) logEntry += " ";
    }
    logEntry += "\n";

    // Print to Serial
    Serial.print(logEntry);

    // Write to SD
    logfile.print(logEntry);

    // Flush occasionally to avoid data loss
    static unsigned long lastFlush = 0;
    if (millis() - lastFlush > 1000) {
      logfile.flush();
      lastFlush = millis();
    }
  }
}
