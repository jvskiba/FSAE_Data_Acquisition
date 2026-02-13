#pragma once
#include <Arduino.h>
#include <HardwareSerial.h>
#include <deque>
#include <vector>
#include <functional>
#include <unordered_map>
#include "ITV.h"

class LoRaManager {
public:
    using ITVHandler = std::function<void(const ITV::ITVMap&)>;

    LoRaManager(HardwareSerial& serial) : _serial(serial) {}

    void begin(int rxPin, int txPin, uint32_t baud = 115200) {
        _serial.begin(baud, SERIAL_8N1, rxPin, txPin);
        _txMutex = xSemaphoreCreateMutex();
        
        // Initialize RYLR settings
        sendAT("AT+RESET");
        delay(500);
        sendAT("AT+ADDRESS=1");
        sendAT("AT+NETWORKID=18");
        sendAT("AT+BAND=915000000");
        sendAT("AT+PARAMETER=7,9,1,8");

        // Start background task
        xTaskCreatePinnedToCore(taskWrapper, "LoRaTask", 4096, this, 3, &_taskHandle, 1);
    }

    void send(const std::vector<uint8_t>& pkt) {
        constexpr size_t LORA_MAX = 96;
        std::vector<std::vector<uint8_t>> splitPkts;
        ITV::splitOnTLVBoundaries(pkt, LORA_MAX, splitPkts);

        if (xSemaphoreTake(_txMutex, pdMS_TO_TICKS(10))) {
            for (const auto& p : splitPkts) {
                _txQueue.push_back(p);
            }
            xSemaphoreGive(_txMutex);
        }
    }

    void setHandler(uint8_t cmd, ITVHandler handler) {
        _handlers[cmd] = handler;
    }

    void sendAT(String cmd, bool debugPrint = true) {
        _serial.println(cmd);
        if (debugPrint) Serial.println(">> " + cmd);
        // We don't block for response in the main thread to prevent hangs
    }

private:
    HardwareSerial& _serial;
    std::deque<std::vector<uint8_t>> _txQueue;
    std::unordered_map<uint8_t, ITVHandler> _handlers;
    
    SemaphoreHandle_t _txMutex;
    TaskHandle_t _taskHandle;

    unsigned long _lastTxTime = 0;
    bool _txBusy = false;
    const unsigned long TX_GUARD_MS = 100;

    static void taskWrapper(void* pvParameters) {
        ((LoRaManager*)pvParameters)->run();
    }

    void run() {
        while (true) {
            poll();
            processQueue();
            vTaskDelay(pdMS_TO_TICKS(20)); // Match your TASK_DELAY_LoRa
        }
    }

    void poll() {
        static char line[256];
        static size_t idx = 0;

        while (_serial.available()) {
            char c = _serial.read();
            if (c == '\n') {
                line[idx] = 0;
                idx = 0;
                handleLine(line);
            } else if (idx < sizeof(line) - 1) {
                line[idx++] = c;
            }
        }
    }

    void handleLine(const char* line) {
        if (strncmp(line, "+RCV=", 5) == 0) {
            handleRX(line);
        } else if (strncmp(line, "+ERR=", 5) == 0) {
            _txBusy = false; // Recovery
        }
    }

    void handleRX(const char* line) {
        char tmp[256];
        strncpy(tmp, line, sizeof(tmp));
        strtok(tmp + 5, ","); // src
        strtok(nullptr, ","); // len
        char* hex = strtok(nullptr, ",");

        if (!hex) return;

        ITV::ITVMap decoded;
        if (ITV::decode_line(hex, decoded) && decoded.count(0x01)) {
            uint8_t cmd = std::get<uint8_t>(decoded.at(0x01));
            if (_handlers.count(cmd)) {
                _handlers[cmd](decoded);
            }
        }
    }

    void processQueue() {
        if (_txBusy && millis() - _lastTxTime > TX_GUARD_MS) {
            _txBusy = false;
        }

        if (_txBusy || _txQueue.empty()) return;

        if (xSemaphoreTake(_txMutex, 0)) {
            const auto& pkt = _txQueue.front();
            String hex = ITV::bytesToHex(pkt);

            _serial.print("AT+SEND=2,");
            _serial.print(pkt.size() * 2);
            _serial.print(",");
            _serial.println(hex);

            _txBusy = true;
            _lastTxTime = millis();
            _txQueue.pop_front();
            xSemaphoreGive(_txMutex);
        }
    }
};