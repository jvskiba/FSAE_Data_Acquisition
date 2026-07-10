#pragma once
#include <Arduino.h>
#include <deque>
#include <vector>
#include <functional>
#include <unordered_map>
#include "driver/twai.h"
#include <cstring>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "config.h"
#include "DataBuffer.h"


#define DEBUG false

#define TaskCoreNum 1
#define TaskPriorityLevel 3

struct CANFrame {
    uint32_t id;
    bool extended;
    bool rtr;
    std::vector<uint8_t> data;
};

class CanManager {
public:
    using CANFrameHandler = std::function<void(uint32_t id, const uint8_t* data, uint8_t len)>;

    CanManager(int rxPin, int txPin) 
        : _rxPin(rxPin), _txPin(txPin) {}

    void begin(std::unordered_map<uint32_t, std::vector<CanSignal>>& map, SharedDataBuffer& bus) {
        _queueMutex = xSemaphoreCreateMutex();
        _enable = true;
        canMap = &map;
        globalBus = &bus;

        if (canMap == nullptr) {
            if (DEBUG) Serial.println("CAN map not set");
            return;
        }

        if (globalBus == nullptr) {
            if (DEBUG) Serial.println("Bus not set");
            return;
        }
        
        twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
            (gpio_num_t)_txPin, 
            (gpio_num_t)_rxPin,
            TWAI_MODE_NORMAL
        );

        //twai_timing_config_t t_config = TWAI_TIMING_CONFIG_1MBITS();
        twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
        twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

        esp_err_t err = twai_driver_install(&g_config, &t_config, &f_config);
        if (err != ESP_OK) {
            Serial.print("Driver install failed: ");
            Serial.println(err);
            return;
        }

        if (twai_start() != ESP_OK) {
            Serial.println("Start failed");
            return;
        }

        Serial.println("TWAI started");

        xTaskCreatePinnedToCore(taskWrapper, "CanTask", 4096, this, TaskPriorityLevel, &_taskHandle, TaskCoreNum);
    }

    void send(uint32_t id, const std::vector<uint8_t>& pkt, bool extended, bool rtr) {
        if (xSemaphoreTake(_queueMutex, pdMS_TO_TICKS(10))) {

            CANFrame frame;
            frame.id = id;
            frame.extended = extended;
            frame.rtr = rtr;
            frame.data = pkt;

            _txQueue.push_back(frame);

            xSemaphoreGive(_queueMutex);
        }
    }

    void setHandler(uint32_t id, CANFrameHandler handler) {
        _handlers[id] = handler;
    }

    void disable() {
        _enable = false;
    }

    void enable() {
        _enable = true;
    }

    void simulateCan() {
        simCan = true;
    }

    // Decode raw bytes from a CAN payload per CanSignal
    float decodeCanSignal(const CanSignal& sig, const uint8_t* data) {
        uint32_t raw = 0;

        if (sig.littleEndian) {
            for (int i = 0; i < sig.length; i++) {
                raw |= ((uint32_t)data[sig.startByte + i]) << (8 * i);
            }
        } else {
            for (int i = 0; i < sig.length; i++) {
                raw = (raw << 8) | data[sig.startByte + i];
            }
        }

        int32_t value;

        if (sig.is_signed) {
            // Generic sign extension
            uint8_t bits = sig.length * 8;

            if (raw & (1UL << (bits - 1))) {
                raw |= (~0UL << bits);
            }

            value = (int32_t)raw;

        } else {
            value = (int32_t)raw;
        }

        return ((float)value * sig.mult) / sig.div + sig.add;
    }

    // Apply an incoming frame to the signals buffer
    void updateSignalsFromFrame(uint32_t rxId, const uint8_t* rxBuf, uint8_t rxLen) {
        auto it = canMap->find(rxId);

        if (it == canMap->end()) {
            return;
        }

        for (const CanSignal& s : it->second) {

            // Bounds check
            if ((int)s.startByte + (int)s.length > rxLen) {
                if (DEBUG) {
                    Serial.println("Signal out of bounds");
                }
                continue;
            }

            float val = decodeCanSignal(s, rxBuf);

            // Debug print (you will thank yourself later)
            if (DEBUG) {
                Serial.print("Signal ID ");
                Serial.print(s.id);
                Serial.print(" = ");
                Serial.println(val);
            }

            // Push to your bus/logger
            LogEntry data = { (uint32_t)millis(), s.id, val };
            globalBus->push(data);
        }
    }

private:

    int _rxPin, _txPin;
    bool _enable;
    bool simCan = false;

    std::deque<CANFrame> _txQueue;
    std::unordered_map<uint32_t, CANFrameHandler> _handlers;
    
    SemaphoreHandle_t _queueMutex; // Protects the txQueue deque
    TaskHandle_t _taskHandle;
    std::unordered_map<uint32_t, std::vector<CanSignal>>* canMap = nullptr;
    SharedDataBuffer* globalBus = nullptr;

    static void taskWrapper(void* pvParameters) {
        ((CanManager*)pvParameters)->run();
    }

    void run() {
        if (DEBUG) Serial.println("CAN Task Started");
    
        while (true) {
            if (!_enable) {
                vTaskDelay(pdMS_TO_TICKS(50));
                continue;
            }

            if (simCan) { 
                spoofCAN(); 
                vTaskDelay(pdMS_TO_TICKS(10)); // Slow down spoofing to 100Hz
                continue;
            }

            processQueue();

            twai_message_t msg;
            if (twai_receive(&msg, pdMS_TO_TICKS(10)) == ESP_OK) {

                if (DEBUG) {
                    Serial.print("RX ID: 0x");
                    Serial.print(msg.identifier, HEX);
                    Serial.print(" Data: ");
                    for (int i = 0; i < msg.data_length_code; i++) {
                        Serial.print(msg.data[i], HEX);
                        Serial.print(" ");
                    }
                    Serial.println();
                }

                updateSignalsFromFrame(msg.identifier, msg.data, msg.data_length_code);

                auto it = _handlers.find(msg.identifier);

                if (it != _handlers.end()) {
                    it->second(
                        msg.identifier,
                        msg.data,
                        msg.data_length_code
                    );
                }
            }

            taskYIELD();
        }
    }

    void processQueue() {
        if (_txQueue.empty()) return;

        CANFrame frame;
        
        // Grab the next packet from the queue
        if (xSemaphoreTake(_queueMutex, 0)) {
            frame = _txQueue.front();
            _txQueue.pop_front();
            xSemaphoreGive(_queueMutex);
        }

        if (!frame.data.empty() || frame.rtr) {
            twai_message_t msg = {};

            msg.identifier = frame.id;
            msg.extd = frame.extended;
            msg.rtr = frame.rtr;

            msg.data_length_code = frame.data.size();

            memcpy(msg.data, frame.data.data(), frame.data.size());

            if (twai_transmit(&msg, pdMS_TO_TICKS(10)) != ESP_OK) {
                if (DEBUG) Serial.println("TWAI TX failed");
            }
        }
    }

    void writeU16BE(uint8_t* buf, uint8_t startByte, uint16_t value) {
        buf[startByte]     = (value >> 8) & 0xFF;
        buf[startByte + 1] = value & 0xFF;
    }

    void spoofCAN() {
        static uint32_t lastUpdate = 0;
        if (millis() - lastUpdate < 1) return;  // ~100 Hz CAN traffic
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
};