#include "FS.h"
#include "SD_MMC.h"

void setup() {
  Serial.begin(115200);
  delay(4000);

  // For Nano ESP32, we explicitly set the pins for the S3 SDMMC peripheral
  // 1-bit mode: CLK = 39, CMD = 38, D0 = 40
  if (!SD_MMC.setPins(D3, D2, D4)) {
    Serial.println("Pin configuration failed!");
    return;
  }

  // Initialize SD_MMC in 1-bit mode (true = 1-bit mode)
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("Card Mount Failed. Check wiring and pull-ups.");
    return;
  }

  uint8_t cardType = SD_MMC.cardType();
  if (cardType == CARD_NONE) {
    Serial.println("No SD card attached");
    return;
  }

  File file = SD_MMC.open("/test.txt", FILE_WRITE);
  if (file) {
    file.println("Hello from Nano ESP32 SDMMC!");
    file.close();
    Serial.println("Write successful.");
  } else {
    Serial.println("Failed to open file for writing.");
  }
}

void loop() {}