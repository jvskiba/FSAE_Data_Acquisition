#include <HardwareSerial.h>
#include <Arduino.h>
#include <vector>
#include <functional>
#include <unordered_map>
#include <deque>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <mcp_can.h>
#include "freertos/ringbuf.h"

#include "config.h"
#include "ITV.h"
#include "NTP_Client.h"
#include "DataLogger.h"
#include "DataBuffer.h"

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D6
#define CAN_SCK  D13
#define CAN_MISO D12
#define CAN_MOSI D11

#define RTC_SDA A4
#define RTC_SCK A5

#define RS232_RX D4
#define RS232_TX D5

#define gpsRXPin D0
#define gpsTXPin D1
#define ppsPin D2

#define sd_clk D3
#define sd_cmd D2
#define sd_d0 D4

// FreeRTOS Delays
#define TASK_DELAY_Main_Loop 10
#define TASK_DELAY_LoRa 20
#define TASK_DELAY_NTP 30
#define TASK_DELAY_LOGGER 10
#define TASK_DELAY_CAN 10

// === DEBUG ===
const bool debug = true;
const bool simulateCan = false;

SharedDataBuffer globalBus;
DataLogger logger;
LoggerConfig config = defaultConfig;
MCP_CAN CAN(CAN_CS);
// SemaphoreHandle_t spiMutex = xSemaphoreCreateMutex(); // Use if sharing SPI

long long now_us() {
    return millis() * 1000 + 999999999000000009;
}

// -------------------------
// FreeRTOS Tasks
// -------------------------

TaskHandle_t canTaskHandle = nullptr;
void canTask(void* pvParameters) {
    Serial.println("CAN Interrupt Task Started");
    
    for (;;) {
        if (simulateCan) { 
            spoofCAN(); 
            vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_LOGGER));
        } else {
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        }

        //Serial.println("CAN Task Run");
        while (CAN.checkReceive() == CAN_MSGAVAIL) {
            unsigned long rxId;
            byte len = 0;
            byte rxBuf[8];
            
            if (xSemaphoreTake(spi1_Mutex, pdMS_TO_TICKS(5))) {
                if (CAN.readMsgBuf(&rxId, &len, rxBuf) == CAN_OK) {
                    updateSignalsFromFrame(rxId, rxBuf, len);
                }
                xSemaphoreGive(spi1_Mutex);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Can Signal Helpers
// ---------------------------------------------------------------------------

// Decode raw bytes from a CAN payload per CanSignal
float decodeCanSignal(CanSignal sig, const uint8_t* data) {
    uint32_t raw = 0;

    // Extract raw value (endian-aware)
    if (sig.littleEndian) {
        for (int i = 0; i < sig.length; i++) {
            raw |= (data[sig.startByte + i] << (8 * i));
        }
    } else {
        for (int i = 0; i < sig.length; i++) {
            raw = (raw << 8) | data[sig.startByte + i];
        }
    }

    // Handle signed vs unsigned
    int32_t signed_val = 0;
    if (sig.is_signed) {
        switch (sig.length) {
            case 1:
                signed_val = (int8_t) raw;
                break;
            case 2:
                signed_val = (int16_t) raw;
                break;
            case 4:
                signed_val = (int32_t) raw;
                break;
            default:
                signed_val = (int32_t) raw;
        }
        return (signed_val * sig.mult) / sig.div;
    } else {
        return (raw * sig.mult) / sig.div;
    }
}

// Apply an incoming frame to the signals table
void updateSignalsFromFrame(uint32_t rxId, const uint8_t* rxBuf, uint8_t rxLen) {
    for (size_t i = 0; i < SignalsCount_Can; ++i) {
    const CanSignal& s = Signals_Can[i];
    if (s.canId != rxId) continue;

    // bounds check: skip if the bytes we need aren't in this frame
    if ((int)s.startByte + (int)s.length > rxLen) continue;

    LogEntry data = { millis(), i, decodeCanSignal(s, rxBuf) };
    globalBus.push(data);
  }
}

// This function runs the moment the CAN_INT pin goes LOW
void IRAM_ATTR canISR() {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    // Notify the CAN task to wake up
    vTaskNotifyGiveFromISR(canTaskHandle, &xHigherPriorityTaskWoken);
    // If the CAN task is higher priority than what's running, switch immediately
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR();
    }
}

void init_can_module() {
    SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);
    // --- Init CAN ---
    if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
        Serial.println("MCP2515 Initialized Successfully!");
        can_OK = true;
        CAN.setMode(MCP_NORMAL);

        CAN.init_Mask(0, 0, 0x000);  // 0x000 mask = accept all IDs
        CAN.init_Filt(0, 0, 0x000);  // doesn't matter
    } else {
        Serial.println("Error Initializing MCP2515...");
    }
}

// ---------------------------------------------------------------------------
// DEBUG - Can Spoofing
// ---------------------------------------------------------------------------


void writeU16BE(uint8_t* buf, uint8_t startByte, uint16_t value) {
    buf[startByte]     = (value >> 8) & 0xFF;
    buf[startByte + 1] = value & 0xFF;
}

void spoofCAN() {
    static uint32_t lastUpdate = 0;
    if (millis() - lastUpdate < 10) return;  // ~100 Hz CAN traffic
    lastUpdate = millis();

    uint8_t buf[8] = {0};

    // --------------------
    // RPM (0x5F0, bytes 6–7)
    // --------------------
    {
        unsigned long id = 0x5F0;
        memset(buf, 0, sizeof(buf));

        uint16_t rpm = 3000 + (millis() / 10) % 4000; // 3000–7000 RPM
        writeU16BE(buf, 6, rpm);
        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Vehicle Speed (0x61A, bytes 0–1)
    // --------------------
    {
        unsigned long id = 0x61A;
        memset(buf, 0, sizeof(buf));

        uint16_t vss = (millis() / 50) % 2000; // 0–200.0 (scaled by /10)
        writeU16BE(buf, 0, vss);

        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Coolant Temp CLT1 (0x5F2, bytes 6–7)
    // --------------------
    {
        unsigned long id = 0x5F2;
        memset(buf, 0, sizeof(buf));

        int16_t clt = 850 + (millis() / 200) % 50; // 85.0–90.0 C
        writeU16BE(buf, 6, (uint16_t)clt);

        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Oil Pressure (0x5FD, bytes 2–3)
    // --------------------
    {
        unsigned long id = 0x5FD;
        memset(buf, 0, sizeof(buf));

        int16_t oilP = 350 + (millis() / 100) % 50; // 35.0–40.0
        writeU16BE(buf, 2, (uint16_t)oilP);

        updateSignalsFromFrame(id, buf, 8);
    }
}


void setup() {
    Serial.begin(115200);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);

    pinMode(CAN_INT, INPUT_PULLUP); // The MCP2515 pulls this LOW on data
    init_can_module();

    // Start logger on Core 1, pointing to globalBus
    logger.setTimeCallback(now_us);
    logger.begin(&globalBus, "/logs", "data", sd_clk, sd_cmd, sd_d0);

    xTaskCreatePinnedToCore(
        canTask, "canTask", 4096, nullptr,  5, &canTaskHandle,  1 );

    Serial.println("=== Setup Done ===");
}

void loop() {
    // 1. SENSOR SIDE (Core 0)
    LogEntry sensorData = { millis(), 0x01, analogRead(A0) };
    globalBus.push(sensorData);

    // 2. TELEMETRY SIDE (Core 0)
    LogEntry recent[5];
    globalBus.peekRecent(recent, 5);
    // sendWireless(recent);

    delay(10); 
}