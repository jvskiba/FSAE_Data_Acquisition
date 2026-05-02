#include "VectorNavParser.h"

// Option 1
//VectorNavParser vn(&Serial2);

// Option 2
VectorNavParser vn(34, 25);

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.print("Starting...");
    vn.begin(115200);
}

void loop() {
    // RTOS task is doing the work
    vTaskDelay(pdMS_TO_TICKS(10000));
}
