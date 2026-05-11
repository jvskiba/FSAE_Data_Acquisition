#include "DataBuffer.h"
#include "VectorNavManager.h"

#define SW_PTT 12

// --- UART 2 - IMU ---
#define HW2_RX 34
#define HW2_TX 25

// Option 1
//VectorNavParser vn(&Serial2);

// Option 2
SharedDataBuffer globalBus;
VectorNavManager vn(HW2_RX, HW2_TX, Serial1);

void setup() {
    Serial.begin(115200);
    delay(1000);

    pinMode(SW_PTT, OUTPUT);
    digitalWrite(SW_PTT, HIGH);
    
    Serial.println("Initializing VectorNav Parsing");
    vn.begin(115200, globalBus);

    vn.getSignalVector();
}

void loop() {
    // RTOS task is doing the work
    popAndPrint(globalBus);

    vTaskDelay(pdMS_TO_TICKS(1));
}

void popAndPrint(SharedDataBuffer &buffer) {
    LogEntry entry;

    if (buffer.pop(entry) && false) {
        Serial.print("Timestamp: ");
        Serial.print(entry.timestamp);

        Serial.print(" | ID: ");
        Serial.print(entry.id);

        Serial.print(" | Value: ");
        Serial.println(entry.value);
    } else {
        //Serial.println("Buffer empty");
    }
}
