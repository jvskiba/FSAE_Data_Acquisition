#include <RadioLib.h>

// ====== PINS =======
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

// Receiver Pins (Adjust if using RF69 vs RF95)
#define RADIO_CS 26 
#define RADIO_INT 13 

#define DEBUG false

// Initialize radio (Use SX1276 for RF95, or RF69 for RF69)
SX1276 radio = new Module(RADIO_CS, RADIO_INT, -1, -1);

// --- INTERRUPT FLAG ---
// 'volatile' is required for variables modified inside an interrupt
volatile bool receivedFlag = false;

// --- INTERRUPT FUNCTION ---
// This runs the instant the radio receives a packet
// Keep it as short as possible!
#if defined(ESP8266) || defined(ESP32)
  ICACHE_RAM_ATTR
#endif
void setFlag(void) {
  receivedFlag = true;
}

void transmitPacket(uint8_t* data, size_t len) {
  Serial.println(F("[TX] Sending packet..."));

  // Stop receiving before transmit
  radio.standby();

  int state = radio.transmit(data, len);

  if (state == RADIOLIB_ERR_NONE) {
    Serial.println(F("[TX] Success"));
  } else {
    Serial.print(F("[TX] Failed, code "));
    Serial.println(state);
  }

  // Go back to RX mode
  radio.startReceive();
}

void setup() {
  Serial.begin(115200);
  Serial.println(F("[Receiver] Initializing..."));

  // (Include your SPI.begin here if you are using custom SPI pins)
  
  // Use the exact parameters that matched your sender
  int state = radio.beginFSK(915.0, 125.0, 125.0, 250.0, 10, 16);
  // If RF69, use: radio.begin(915.0, 125.0, 125.0, 250.0, 10, 16);

  if (state != RADIOLIB_ERR_NONE) {
    Serial.print(F("Failed, code "));
    Serial.println(state);
    while (true);
  }

  radio.setDataShaping(RADIOLIB_SHAPING_1_0); // GFSK
  
  uint8_t syncWord[] = {0x2D, 0xD4};
  radio.setSyncWord(syncWord, 2);

  // --- SET UP THE INTERRUPT ---
  // Tell RadioLib to call 'setFlag' when DIO0/INT goes HIGH
  radio.setDio0Action(setFlag, RISING);

  // Start listening in the background
  Serial.println(F("[Receiver] Listening for packets..."));
  state = radio.startReceive();
  if (state != RADIOLIB_ERR_NONE) {
    Serial.print(F("startReceive failed, code "));
    Serial.println(state);
  }

}

void loop() {
  // Check if the interrupt fired
  if (receivedFlag) {
    // 1. Reset the flag immediately
    receivedFlag = false;

    // 2. Buffer for the incoming data
    uint8_t data[256];

    // 3. Read the data out of the radio's FIFO buffer
    // (Notice we use readData() now, not receive())
    int state = radio.readData(data, 256);

    if (state == RADIOLIB_ERR_NONE) {
        //Serial.println(F("Packet received!"));

        size_t len = radio.getPacketLength();

        if (DEBUG) {
            for (size_t i = 0; i < len; i++) {
                if (data[i] < 0x10) Serial.print('0'); 
                    Serial.print(data[i], HEX);
                    Serial.print(F(" "));
                }
            Serial.println();
        }

      
      Serial.print("D:");
      //Serial.write(len);
      Serial.write(data, len);
      Serial.write('\n');

    } else if (state == RADIOLIB_ERR_CRC_MISMATCH) {
      Serial.println(F("CRC Error - Data corrupted"));
    } else {
      Serial.print(F("readData failed, code "));
      Serial.println(state);
    }

    // 4. IMPORTANT: Put the radio back into receive mode!
    radio.startReceive();
  }

  // ===== SERIAL TX HANDLING =====
  if (Serial.available() > 0) {
    uint8_t len = Serial.read();

    if (len > 0 && len <= 255) {
      uint8_t buffer[256];

      size_t readBytes = Serial.readBytes(buffer, len);

      if (readBytes == len) {
        transmitPacket(buffer, len);
      } else {
        Serial.println(F("[TX] Incomplete packet"));
      }
    }
  }
}