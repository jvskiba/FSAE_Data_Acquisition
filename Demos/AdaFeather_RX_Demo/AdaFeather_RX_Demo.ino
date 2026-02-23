#include "SD_MMC.h"

// Your current wiring for the soldered GPIO 2 setup
#define SD_MMC_CLK 14
#define SD_MMC_CMD 15
#define SD_MMC_D0  2   // The pin you just soldered!

void setup() {
  Serial.begin(115200);
  while (!Serial);
  delay(2000);

  Serial.println("\n--- SOLDERED GPIO 2 SD_MMC TEST ---");

  // 1. Assign the pins to the SDMMC hardware
  // Parameters: clk, cmd, d0
  if (!SD_MMC.setPins(SD_MMC_CLK, SD_MMC_CMD, SD_MMC_D0)) {
    Serial.println("Error: Internal GPIO Matrix could not route these pins.");
    return;
  }

  // 2. Mount the card in 1-bit mode
  // begin(mount_point, mode1bit, format_if_failed, freq_khz)
  // Using 20MHz (20000) for a high-speed test
  if (!SD_MMC.begin("/sdcard", true, false, 20000)) {
    Serial.println("Mount Failed!");
    Serial.println("Possible issues:");
    Serial.println("- GPIO 2 needs a 10k pull-up resistor to 3.3V.");
    Serial.println("- The solder joint on GPIO 2 is cold/loose.");
    Serial.println("- Card is not FAT32 formatted.");
    return;
  }

  // 3. Success! Print card info
  Serial.println("MOUNT SUCCESSFUL!");
  
  uint8_t cardType = SD_MMC.cardType();
  String typeStr = (cardType == CARD_MMC) ? "MMC" : (cardType == CARD_SD) ? "SDSC" : (cardType == CARD_SDHC) ? "SDHC" : "Unknown";
  Serial.println("Card Type: " + typeStr);

  uint64_t cardSize = SD_MMC.cardSize() / (1024 * 1024);
  Serial.printf("Card Size: %llu MB\n", cardSize);

  // 4. Perform a quick write test
  File file = SD_MMC.open("/test_mmc.txt", FILE_WRITE);
  if (file) {
    file.println("Logging via hardware SD_MMC on GPIO 2!");
    file.close();
    Serial.println("File write successful.");
  } else {
    Serial.println("File write failed.");
  }
}

void loop() {}