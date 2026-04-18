#include "VectorNavParser.h"

// Option 1
VectorNavParser vn(&Serial2);

// Option 2
// VectorNavParser vn(16, 17);

void setup() {
    Serial.begin(115200);
    vn.begin(115200);
}

void loop() {
    // RTOS task is doing the work
}
