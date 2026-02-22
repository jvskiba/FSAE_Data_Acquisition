#include <SPI.h>
#include <RH_RF95.h>

#define RFM95_CS    26
#define RFM95_RST   32
#define RFM95_INT   13

RH_RF95 rf95(RFM95_CS, RFM95_INT);

void setup() {
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
  Serial.begin(115200);
  while (!Serial);

  digitalWrite(RFM95_RST, LOW); delay(10);
  digitalWrite(RFM95_RST, HIGH); delay(10);

  if (!rf95.init()) { Serial.println("Init Failed"); while (1); }

  rf95.setFrequency(915.0);
  rf95.spiWrite(RH_RF95_REG_39_SYNC_WORD, 0x12); // Network ID 18
  rf95.setPreambleLength(8);
  rf95.setModemConfig(RH_RF95::Bw125Cr45Sf128);

  Serial.println("Receiver Ready! Waiting for packets...");
}

void loop() {
  if (rf95.available()) {
    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf);

    if (rf95.recv(buf, &len)) {
      Serial.print("Received [");
      Serial.print(len);
      Serial.print(" bytes]: ");
      Serial.println((char*)buf);
      
      // Print RSSI (Signal Strength)
      Serial.print("RSSI: ");
      Serial.println(rf95.lastRssi(), DEC);
    } else {
      Serial.println("Receive failed");
    }
  }
}