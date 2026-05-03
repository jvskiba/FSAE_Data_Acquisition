#include "DataBuffer.h"
#include "VectorNavManager.h"

// Option 1
//VectorNavParser vn(&Serial2);

// Option 2
SharedDataBuffer globalBus;
VectorNavManager vn(34, 25, 1);

void setup() {
    Serial.begin(115200);
    delay(1000);
    
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

    if (buffer.pop(entry)) {
        Serial.print("Timestamp: ");
        Serial.print(entry.timestamp);

        Serial.print(" | ID: ");
        Serial.print(entry.id);

        Serial.print(" | Value: ");
        Serial.println(entry.value);
    } else {
        Serial.println("Buffer empty");
    }
}
