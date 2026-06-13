#include <RadioLib.h>

// ====== PINS =======
// SPI
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

#define HSPI_SCLK 14 //D14
#define HSPI_MISO 15 //D32
#define HSPI_MOSI 32 //D15

// Chip Select Pins
// (Renamed from RFM95 to RF69 for clarity, keep pins the same if using the same board)
#define RF69_CS 26 //A0
#define RF69_INT 13 //LED
#define CAN_CS 4 //A5
#define CAN_INT 37 //D37

// Instantiate the RF69 module instead of SX1276
// Pins: CS, DIO0/IRQ, RST, DIO1
RF69 radio = new Module(RF69_CS, RF69_INT, -1, -1);

void setup() {
  Serial.begin(115200);
  Serial.println(F("[RF69] Initializing..."));

  // Initialize custom SPI bus
  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN);

  // For RF69, begin() naturally initializes in FSK mode.
  // Parameters:
  // Frequency: 915.0 MHz
  // Bit Rate: 125.0 kbps
  // Freq Dev: 125.0 kHz
  // RX Bandwidth: 250.0 kHz
  // Power: 10 dBm
  // Preamble: 16 bits
  int state = radio.begin(915.0, 125.0, 125.0, 250.0, 10, 16);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("Initialization successful!"));
  } else {
    Serial.print(F("Failed, code "));
    Serial.println(state);
    while (true);
  }

  // Set Data Shaping to GFSK (Gaussian Filter)
  // RADIOLIB_SHAPING_1_0 is the macro for BT = 1.0
  radio.setDataShaping(RADIOLIB_SHAPING_1_0);

  // Set Sync Word (Must match the Receiver!)
  // Using the common RF69 default: 0x2D 0xD4
  uint8_t syncWord[] = {0x2D, 0xD4};
  radio.setSyncWord(syncWord, 2);
}

void loop() {
  Serial.print(F("[RF69] Sending binary data... "));

  // Example: 8 bytes of raw CAN-style binary data
  uint8_t canData[] = {0x12, 0x34, 0x56, 0x78, 0xAB, 0xCD, 0xEF, 0x00};

  // radio.transmit() sends the raw buffer
  int state = radio.transmit(canData, 8);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("Success!"));
  } else if (state == RADIOLIB_ERR_PACKET_TOO_LONG) {
    Serial.println(F("Error: Packet too long"));
  } else {
    Serial.print(F("Error: "));
    Serial.println(state);
  }

  // Wait 1 second before next transmission
  delay(1000);
}