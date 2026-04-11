#pragma once
#include <Arduino.h>
#include <SPI.h>
#include <RH_RF69.h>
#include <deque>
#include <vector>
#include <functional>
#include <unordered_map>
#include "ITV.h"

#define DEBUG true

class LoRaManager {
public:
    using ITVHandler = std::function<void(const ITV::ITVMap&)>;

    // Constructor: Takes SPI bus reference, CS, and INT pins
    LoRaManager(SPIClass& bus, int csPin, int intPin) 
        : _spiBus(bus), _csPin(csPin), _intPin(intPin) {
        // Driver is initialized here but hardware isn't started until begin()
        _rf69 = new RH_RF69(_csPin, _intPin);
    }

    // Pass an external mutex for the SPI bus to prevent CAN/SD conflicts
    void begin(SemaphoreHandle_t busMutex, float freq = 915.0) {
        _busMutex = busMutex;
        _queueMutex = xSemaphoreCreateMutex();
        enable_lora = true;
        
        // Initial hardware setup
        if (!_rf69->init()) {
            Serial.println("LoRa (RFM95) Init Failed!");
            return;
        }

        _rf69->setFrequency(freq);
        _rf69->setTxPower(23, false);
        _rf69->setModemConfig(RH_RF69::FSK_Rb250Fd250);

        // Start background task on Core 1 (Core 0 is usually WiFi/Radio)
        xTaskCreatePinnedToCore(taskWrapper, "LoRaTask", 4096, this, 3, &_taskHandle, 1);
    }

    void send(const std::vector<uint8_t>& pkt) {
        constexpr size_t LORA_MAX = 200; // RFM95 can handle more than RYLR
        std::vector<std::vector<uint8_t>> splitPkts;
        ITV::splitOnTLVBoundaries(pkt, LORA_MAX, splitPkts);

        if (xSemaphoreTake(_queueMutex, pdMS_TO_TICKS(10))) {
            for (const auto& p : splitPkts) {
                _txQueue.push_back(p);
            }
            xSemaphoreGive(_queueMutex);
        }
    }

    void setHandler(uint8_t cmd, ITVHandler handler) {
        _handlers[cmd] = handler;
    }

    void disable() {
        enable_lora = false;
    }

    void enable() {
        enable_lora = true;
    }

private:
    SPIClass& _spiBus;
    RH_RF69* _rf69;
    int _csPin, _intPin;
    bool enable_lora;

    std::deque<std::vector<uint8_t>> _txQueue;
    std::unordered_map<uint8_t, ITVHandler> _handlers;
    
    SemaphoreHandle_t _queueMutex; // Protects the txQueue deque
    SemaphoreHandle_t _busMutex;   // Protects physical SPI bus sharing
    TaskHandle_t _taskHandle;

    static void taskWrapper(void* pvParameters) {
        ((LoRaManager*)pvParameters)->run();
    }

    void run() {
        while (true) {
            if (!enable_lora) {
                vTaskDelay(pdMS_TO_TICKS(100));
                continue;
            }
            poll();
            processQueue();
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }

    void poll() {
        bool packetReceived = false;
        uint8_t buf[RH_RF69_MAX_MESSAGE_LEN];
        uint8_t len = sizeof(buf);

        // Lock the SPI bus before checking hardware
        if (xSemaphoreTake(_busMutex, pdMS_TO_TICKS(5))) {
            if (_rf69->available()) {
                if (_rf69->recv(buf, &len)) {
                    packetReceived = true;
                }
            }
            xSemaphoreGive(_busMutex);
        }

        if (packetReceived) {
            handleRX(buf, len);
        }
    }

    void handleRX(uint8_t* data, uint8_t len) {
        ITV::ITVMap decoded;

        if (ITV::decode(data, len, decoded) && decoded.count(0x01)) {
            uint8_t cmd = std::get<uint8_t>(decoded.at(0x01));
            if (_handlers.count(cmd)) {
                _handlers[cmd](decoded);
            }
        }
    }

    void processQueue() {
        if (_txQueue.empty()) return;

        std::vector<uint8_t> pkt;
        
        // Grab the next packet from the queue
        if (xSemaphoreTake(_queueMutex, 0)) {
            pkt = _txQueue.front();
            _txQueue.pop_front();
            xSemaphoreGive(_queueMutex);
        }

        // Lock SPI bus to transmit
        if (!pkt.empty()) {
            if (xSemaphoreTake(_busMutex, pdMS_TO_TICKS(100))) {
                _rf69->send(pkt.data(), pkt.size());
                //_rf69->waitPacketSent(); //Removed, causing blocking behavior on bus if interrupt is not received
                //TODO: Maybe put back into the code with timeout feature
                xSemaphoreGive(_busMutex);
                Serial.println("Lora Send");
            } else {
                // If we couldn't get the bus, put it back at the front to try again
                if (xSemaphoreTake(_queueMutex, pdMS_TO_TICKS(10))) {
                    _txQueue.push_front(pkt);
                    xSemaphoreGive(_queueMutex);
                }
            }
        }
    }
};