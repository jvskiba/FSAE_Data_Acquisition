#include "DataLogger.h"
#include "DataBuffer.h"

#define HSPI_SCLK 14 //D14
#define HSPI_MISO 15 //D32
#define HSPI_MOSI 32 //D15

#define SW_PTT 12

SharedDataBuffer globalBus;
DataLogger logger;
SPIClass *hspi = new SPIClass(HSPI);

std::vector<SignalDef> signalNameList;

std::vector<SignalDef> buildSignalNameList() {
    std::vector<SignalDef> list;

    for (uint8_t i = 0; i < 10; i++) {
        list.push_back(SignalDef{i, "Happy"});
    }

    return list;
}

long long now_us() {
    return millis() * 1000 + 999999999; //TODO: Add back RTC and NTP
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);
    Serial.println("ILTM Booting...");
    pinMode(SW_PTT, OUTPUT);
    digitalWrite(SW_PTT, HIGH);

    // Start logger on Core 1, pointing to globalBus
    hspi->begin(HSPI_SCLK, HSPI_MISO, HSPI_MOSI, -1);
    while(1) {
        if (!SD.begin(-1, *hspi, 4000000)) {
            Serial.println("SD Begin Failed");
            delay(100);
            continue;
        }
        break;
    }
    
    Serial.println("SD Working!!!");

    logger.setTimeCallback(now_us);

    signalNameList = buildSignalNameList();
    logger.begin(&globalBus, "/Temp", "data", hspi, &signalNameList);
    
}


void loop() {
    LogEntry data = { (uint32_t)millis(), 1, 8};
    globalBus.push(data);
    data = { (uint32_t)millis(), 2, 16};
    globalBus.push(data);
    data = { (uint32_t)millis(), 3, 32};
    globalBus.push(data);

    vTaskDelay(pdMS_TO_TICKS(1));
}