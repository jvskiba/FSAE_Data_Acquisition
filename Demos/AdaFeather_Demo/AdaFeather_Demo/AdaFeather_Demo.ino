#include <SPI.h>
#include <RH_RF95.h>
#include "FS.h"
#include <SD.h>
#include <SoftwareSerial.h>

// SPI Pin Definitions for Feather V2 (Standard)
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

// Chip Select Pins
#define RFM95_CS 26
#define SD_CS    32
#define RFM95_INT 13

// --- UART 1 - SIM ---
#define HW1_RX 7
#define HW1_TX 8

// --- UART 2 - IMU ---
#define HW2_RX 34
#define HW2_TX 25

// --- UART 3 - RS232 ---
#define RS_RX 36
#define RS_TX 33

// --- UART 4 - COMS ---
#define SW_RX 39
#define SW_TX 27

RH_RF95 rf95(RFM95_CS, RFM95_INT);
SoftwareSerial softSerial;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SD_CS);


  if (!rf95.init()) { Serial.println("Init Failed"); while (1); }

  rf95.setFrequency(915.0);
  rf95.setTxPower(5, false); // Low power for wire antenna
  rf95.spiWrite(RH_RF95_REG_39_SYNC_WORD, 0x12); // Network ID 18
  rf95.setPreambleLength(8);
  rf95.setModemConfig(RH_RF95::Bw125Cr45Sf128);

  Serial.println("Transmitter Ready!");

  Serial.println("Mounting SD Card...");
  // 3. Initialize SD Card first
  // Standard SD.begin uses the default SPI bus
  if (!SD.begin(SD_CS, SPI)) {
    Serial.println("SD initialization failed!");
    // We don't halt here, so the radio can still try to work
  } else {
    Serial.println("SD Card OK.");
  }

  // --- Write Test ---
  File file = SD.open("/lora_log.txt", FILE_WRITE);
  if (!file) {
    Serial.println("Failed to open file for writing");
    return;
  }
  
  if (file.println("LoRa Data Received: Hello from Feather!")) {
    Serial.println("File written");
  } else {
    Serial.println("Write failed");
  }
  file.close();

  // --- Read Test ---
  file = SD.open("/lora_log.txt");
  if (file) {
    Serial.print("Read from file: ");
    while (file.available()) {
      Serial.write(file.read());
    }
    file.close();
  }

  Serial.println("\n--- Triple Hardware + Single Software UART Test ---");

  // 2. Hardware UART 1 (RYLR Module 1)
  // On ESP32 V2, we can assign pins during begin
  Serial1.begin(115200, SERIAL_8N1, HW1_RX, HW1_TX);
  Serial.println("UART1 Initialized on 25(RX)/26(TX)");

  // 3. Hardware UART 2 (RYLR Module 2)
  Serial2.begin(115200, SERIAL_8N1, HW2_RX, HW2_TX);
  Serial.println("UART2 Initialized on 12(RX)/27(TX)");

  // 4. Software Serial (RYLR Module 3)
  softSerial.begin(115200, SWSERIAL_8N1, SW_RX, SW_TX);
  Serial.println("SoftwareSerial Initialized on 33(RX)/15(TX)");

  delay(1000);
  
  // Test Command to RYLRs
  Serial.println("Sending AT test to all modules...");
  testPort(Serial1, "HW_UART_1");
  testPort(Serial2, "HW_UART_2");
}

void testPort(Stream &port, String name) {
  if (port.available()) {
    Serial.print("[" + name + "]: ");
    while(port.available()) Serial.write(port.read());
    Serial.println();
  } else {
    Serial.println("Failed");
  }
}

void loop() {

  Serial.println("Sending AT test to all modules...");
  testPort(Serial1, "HW_UART_1");
  testPort(Serial2, "HW_UART_2");

  const char *msg = "HELLO";
  Serial.print("Sending...");
  rf95.send((uint8_t *)msg, strlen(msg));
  rf95.waitPacketSent();
  Serial.println("Done");
  delay(2000); 

}