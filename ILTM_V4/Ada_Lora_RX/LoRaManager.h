#pragma once
#include <Arduino.h>
#include <SPI.h>
#include <RH_RF95.h>
#include <deque>
#include <vector>
#include <functional>
#include <unordered_map>
#include "ITV.h"

//static bool debug = true;

class LoRaManager {
public:
    using ITVHandler = std::function<void(const ITV::ITVMap&)>;

    // Constructor: Takes SPI bus reference, CS, and INT pins
    LoRaManager(SPIClass& bus, int csPin, int intPin) 
        : _spiBus(bus), _csPin(csPin), _intPin(intPin) {
        // Driver is initialized here but hardware isn't started until begin()
        _rf95 = new RH_RF95(_csPin, _intPin);
    }

    // Pass an external mutex for the SPI bus to prevent CAN/SD conflicts
    void begin(SemaphoreHandle_t busMutex, float freq = 915.0) {
        _busMutex = busMutex;
        _queueMutex = xSemaphoreCreateMutex();
        
        // Initial hardware setup
        if (!_rf95->init()) {
            Serial.println("LoRa (RFM95) Init Failed!");
            return;
        }

        _rf95->setFrequency(freq);
        _rf95->setTxPower(23, false);
        _rf95->setModemConfig(RH_RF95::Bw125Cr45Sf128);

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

private:
    SPIClass& _spiBus;
    RH_RF95* _rf95;
    int _csPin, _intPin;

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
            poll();
            processQueue();
            vTaskDelay(pdMS_TO_TICKS(5));
        }
    }

    void poll() {
        bool packetReceived = false;
        uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
        uint8_t len = sizeof(buf);

        // Lock the SPI bus before checking hardware
        if (xSemaphoreTake(_busMutex, pdMS_TO_TICKS(5))) {
            if (_rf95->available()) {
                if (_rf95->recv(buf, &len)) {
                    packetReceived = true;
                }
            }
            xSemaphoreGive(_busMutex);
        }

        if (packetReceived) {
            //Serial.println("Lora Received");
            handleRX(buf, len);
        }
    }

    static void sendToSerial(const ITV::ITVMap& map) {
        bool first = true;
        Serial.print("DATA:");

        for (const auto& [key, val] : map) {
            if (!first) {
                Serial.print(",");
            }
            first = false;

            Serial.print(key);
            Serial.print(":");

            std::visit([](auto&& arg) {
                using T = std::decay_t<decltype(arg)>;

                if constexpr (std::is_same_v<T, std::string>) {
                    Serial.print(arg.c_str());
                } else if constexpr (std::is_same_v<T, bool>) {
                    Serial.print(arg ? 1 : 0);
                } else {
                    Serial.print(arg);
                }
            }, val);
        }

        Serial.println(); // end of packet
    }

    void handleRX(uint8_t* data, uint8_t len) {
        if (false) {
            Serial.print("RAW: ");
            for (int i = 0; i < len; i++) {
                Serial.print(data[i], HEX);
                Serial.print(" ");
            }
            Serial.println();
        }
        

        ITV::ITVMap decoded;
        // SPI LoRa gives us raw bytes, so we use decode instead of decode_line(hex)
        if (ITV::decode(data, len, decoded)) {
            sendToSerial(decoded);
        } else {
            Serial.println("Decode failed");
            return;
        }
        if (decoded.count(0x01)) {
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
                _rf95->send(pkt.data(), pkt.size());
                _rf95->waitPacketSent();
                xSemaphoreGive(_busMutex);
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