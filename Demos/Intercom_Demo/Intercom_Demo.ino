#include "ComsManager.h"

ComsManager radio(39, 27, 26); // RX, TX, PTT

void setup() {
    Serial.begin(115200);
    radio.begin();

    if (radio.connect()) {
        Serial.println("Radio connected");
    } else {
        Serial.println("Radio NOT responding");
    }

    radio.setVolume(4);

    radio.setGroup(
        0,          // 12.5kHz
        435.7250,
        435.7250,
        "0000",
        4,
        "0000"
    );
}

void loop() {
    int rssi = radio.getRSSI();
    Serial.println(rssi);
    delay(1000);

    radio.pttOn();   // start talking
    delay(2000);

    radio.pttOff();  // go back to listening
    delay(2000);
}