#include <SPI.h>
#include <RH_RF95.h>
#include "FS.h"
#include <SD.h>
#include <SoftwareSerial.h>
#include <mcp2515.h>
#include "RTClib.h"
#include <Wire.h>

// SPI Pin Definitions for Feather V2 (Standard)
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

#define HSPI_SCLK 14
#define HSPI_MISO 32
#define HSPI_MOSI 15
#define HSPI_SS   -1

// Chip Select Pins
#define RFM95_CS 26
#define SD_CS    32
#define RFM95_INT 13
#define CAN_CS 4
#define CAN_INT 37

// I2C
#define I2C_SDA 22
#define I2C_SCL 20

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
MCP2515 mcp2515(CAN_CS);
RTC_DS3231 rtc;
SPIClass *hspi = new SPIClass(HSPI);

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("==== Starting ILTM V4 DEMO === "); 

  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SD_CS);


  if (!rf95.init()) { 
    Serial.println("LoRa Init Failed"); 
  } else {
    rf95.setFrequency(915.0);
    rf95.setTxPower(5, false); // Low power for wire antenna
    rf95.spiWrite(RH_RF95_REG_39_SYNC_WORD, 0x12); // Network ID 18
    rf95.setPreambleLength(8);
    rf95.setModemConfig(RH_RF95::Bw125Cr45Sf128);

    Serial.println("Transmitter Ready!");
  }

  hspi->begin(HSPI_SCLK, HSPI_MISO, HSPI_MOSI, HSPI_SS);
  
  // 2. Initialize SD card on the HSPI bus
  // Format: begin(ss_pin, spi_class_pointer, frequency)
  if (!SD.begin(HSPI_SS, *hspi, 4000000)) { // Start at 4MHz for stability
    Serial.println("SD initialization FAILED on HSPI!");
    return;
  }

  Serial.println("SD initialization SUCCESS on HSPI.");

  // 3. Test Write
  File file = SD.open("/hspi_test.txt", FILE_WRITE);
  if (file) {
    file.println("This data is on a dedicated SPI bus!");
    file.close();
    Serial.println("Write Successful.");
  } else {
    Serial.println("File open failed.");
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
  testPort(softSerial, "SW_UART_1");

  Serial.println("Initializing CAN Bus...");
  mcp2515.reset();
  // Set to 500KBPS (Common for automotive) and 8MHz or 16MHz clock depending on your crystal
  if (mcp2515.setBitrate(CAN_500KBPS, MCP_8MHZ) == MCP2515::ERROR_OK) {
    mcp2515.setNormalMode();
    Serial.println("CAN Initialized Successfully!");
  } else {
    Serial.println("CAN Initialization Failed! Check SPI and CS Pin 4.");
  }
  delay(500);
  testCAN();

  // 1. Initialize I2C and RTC
  Serial.println("Initializing I2C...");
  Wire.begin(I2C_SDA, I2C_SCL);
  delay(500);
  if (!rtc.begin()) {
    Serial.println("Couldn't find RTC");
  } else if (rtc.lostPower()) {
    Serial.println("RTC lost power, setting the time!");
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }

  Serial.println(getTimestamp());
}

String getTimestamp() {
  DateTime now = rtc.now();
  char buf[] = "YYYY-MM-DD hh:mm:ss";
  return String(now.toString(buf));
}

void testPort(Stream &port, String name) {
  Serial.print("Testing [" + name + "]... ");
  port.write("AT\r\n");
  delay(50);
  if (port.available()) {
    Serial.print("[" + name + "]: ");
    while(port.available()) Serial.write(port.read());
    Serial.println();
  } else {
    Serial.println("Failed");
  }
}

// Function to test CAN send
void testCAN() {
  struct can_frame frame;
  frame.can_id  = 0x0F6; // Random ID
  frame.can_dlc = 8;     // Data length
  frame.data[0] = 0xDE;
  frame.data[1] = 0xAD;
  frame.data[2] = 0xBE;
  frame.data[3] = 0xEF;
  
  if (mcp2515.sendMessage(&frame) == MCP2515::ERROR_OK) {
    Serial.println("CAN Message Sent!");
  } else {
    Serial.println("CAN Send Failed.");
  }
}

void loop() {

  Serial.println("Sending AT test to all modules...");
  testPort(Serial1, "HW_UART_1");
  testPort(Serial2, "HW_UART_2");
  testPort(softSerial, "SW_UART_1");

  const char *msg = "HELLO";
  Serial.print("Sending...");
  rf95.send((uint8_t *)msg, strlen(msg));
  rf95.waitPacketSent();
  Serial.println("Done");
  delay(2000); 
  Serial1.end();
  delay(10);
  Serial1.begin(115200, SERIAL_8N1, RS_RX, RS_TX);
  Serial.println("Switched UART1 to new pins.");
  delay(200);
  testPort(Serial1, "HW_UART_1");
  
  delay(2000);
  testPort(Serial1, "HW_UART_1");
  Serial1.end();
  delay(10);
  Serial1.begin(115200, SERIAL_8N1, HW1_RX, HW1_TX);
  Serial.println("Switched UART1 to new pins.");
  delay(20000);

}