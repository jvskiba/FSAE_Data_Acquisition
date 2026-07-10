#include <SPI.h>
#include <mcp2515.h>

MCP2515 mcp2515(5);     // CS pin

struct can_frame frame;

void setup() {
    Serial.begin(115200);

    SPI.begin();

    mcp2515.reset();

    // Change these to match your bus
    mcp2515.setBitrate(CAN_500KBPS, MCP_8MHZ);
    // mcp2515.setBitrate(CAN_500KBPS, MCP_16MHZ);

    mcp2515.setNormalMode();

    frame.can_id = 0x5FD;
    frame.can_dlc = 8;

    for (int i = 0; i < 8; i++) {
        frame.data[i] = i;
    }

    Serial.println("Starting CAN flood...");
}

void loop() {
    static uint8_t counter = 0;

    frame.data[0] = counter++;
    frame.data[1] = counter;
    frame.data[2] = millis();
    frame.data[3] = millis() >> 8;

    MCP2515::ERROR err = mcp2515.sendMessage(&frame);

    if (err == MCP2515::ERROR_OK) {
        Serial.println("Frame queued");
    }
    else {
        Serial.printf("Error: %d\n", err);
    }

    Serial.printf(
        "TEC=%u REC=%u\n",
        mcp2515.errorCountTX(),
        mcp2515.errorCountRX()
    );
}