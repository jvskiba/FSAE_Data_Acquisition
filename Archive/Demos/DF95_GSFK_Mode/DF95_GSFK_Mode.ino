#include <RadioLib.h>
#include <mcp_can.h>

// ====== PINS =======
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

#define CAN_CS 4 //A5
#define CAN_INT 37 //D37

// Receiver Pins (Adjust if using RF69 vs RF95)
#define RADIO_CS 26 
#define RADIO_INT 13 

MCP_CAN CAN(CAN_CS);

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

void init_can_module() {
    byte canStatus = CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ);
    int retry = 0;
    while (canStatus != CAN_OK && retry < 5) {
        delay(100);
        canStatus = CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ);
        retry++;
    }

    if (canStatus == CAN_OK) {
        Serial.println("MCP2515 Initialized!");
        
        // Force a mode set and verify it actually changed
        CAN.setMode(MCP_NORMAL);
        delay(10); 

        CAN.init_Mask(0, 0, 0x000); 
        CAN.init_Filt(0, 0, 0x000);

        //pinMode(CAN_INT, INPUT_PULLUP);
        //attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);
        //can_OK = true;
    } else {
        Serial.print("Error Initializing MCP2515. Error Code: ");
        Serial.println(canStatus);
    }
}

// Helper function to handle the actual hardware transmission
void sendCanFrame(uint32_t id, uint8_t* data, uint8_t len) {
  CAN.sendMsgBuf(id, 0, len, data);
}

// Helper function to write a 16-bit integer (Big Endian) into a byte array
void writeU16BE(uint8_t* buffer, int offset, uint16_t value) {
    buffer[offset] = (value >> 8) & 0xFF;     // High byte
    buffer[offset + 1] = value & 0xFF;        // Low byte
}

void spoofAndTransmitCAN() {
    static uint32_t lastUpdate = 0;
    if (millis() - lastUpdate < 100) return;  // ~10 Hz CAN traffic
    lastUpdate = millis();

    Serial.println("Sending Can");

    uint8_t buf[8];

    // --------------------
    // RPM (0x5F0, bytes 6–7)
    // --------------------
    {
        uint32_t id = 0x5F0;
        memset(buf, 0, sizeof(buf));

        uint16_t rpm = 3000 + (millis() / 10) % 4000; // 3000–7000 RPM
        writeU16BE(buf, 6, rpm);
        
        sendCanFrame(id, buf, 8);
    }

    // --------------------
    // Vehicle Speed (0x61A, bytes 0–1)
    // --------------------
    {
        uint32_t id = 0x61A;
        memset(buf, 0, sizeof(buf));

        uint16_t vss = (millis() / 50) % 2000; // 0–200.0 (scaled by /10)
        writeU16BE(buf, 0, vss);

        sendCanFrame(id, buf, 8);
    }

    // --------------------
    // Coolant Temp CLT1 (0x5F2, bytes 6–7)
    // --------------------
    {
        uint32_t id = 0x5F2;
        memset(buf, 0, sizeof(buf));

        int16_t clt = 850 + (millis() / 200) % 50; // 85.0–90.0 C
        writeU16BE(buf, 6, (uint16_t)clt);

        sendCanFrame(id, buf, 8);
    }

    // --------------------
    // Oil Pressure (0x5FD, bytes 2–3)
    // --------------------
    {
        uint32_t id = 0x5FD;
        memset(buf, 0, sizeof(buf));

        int16_t oilP = 350 + (millis() / 100) % 50; // 35.0–40.0
        writeU16BE(buf, 2, (uint16_t)oilP);

        sendCanFrame(id, buf, 8);
    }
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

  init_can_module();
}

void loop() {
  // Check if the interrupt fired
  if (receivedFlag) {
    // 1. Reset the flag immediately
    receivedFlag = false;

    // 2. Buffer for the incoming data
    uint8_t data[64];

    // 3. Read the data out of the radio's FIFO buffer
    // (Notice we use readData() now, not receive())
    int state = radio.readData(data, 64);

    if (state == RADIOLIB_ERR_NONE) {
      //Serial.println(F("Packet received!"));

      size_t len = radio.getPacketLength();

      /*for (size_t i = 0; i < len; i++) {
        if (data[i] < 0x10) Serial.print('0'); 
        Serial.print(data[i], HEX);
        Serial.print(F(" "));
      }
      Serial.println();
      */
      
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

  //spoofAndTransmitCAN();
  
  // Your code can now do other things here without blocking!
  // e.g., read CAN bus, write to SD card, etc.
}