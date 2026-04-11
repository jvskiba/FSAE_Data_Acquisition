#pragma once
#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <deque>
#include <vector>
#include <functional>
#include <unordered_map>
#include "ITV.h"

#define DEBUG true

volatile bool receivedFlag = false;

#if defined(ESP8266) || defined(ESP32)
  ICACHE_RAM_ATTR
#endif
void setFlag(void) {
  receivedFlag = true;
}

class LoRaManager {
public:
    using ITVHandler = std::function<void(const ITV::ITVMap&)>;

    // Constructor: Takes SPI bus reference, CS, and INT pins
    LoRaManager(SPIClass& bus, int csPin, int intPin) 
        : _spiBus(bus), _csPin(csPin), _intPin(intPin) {
        // Driver is initialized here but hardware isn't started until begin()
        mod = new Module(csPin, intPin, -1, -1);
        radio = new RF69(mod);
    }

    // Pass an external mutex for the SPI bus to prevent CAN/SD conflicts
    void begin(SemaphoreHandle_t busMutex, float freq = 915.0) {
        _busMutex = busMutex;
        _queueMutex = xSemaphoreCreateMutex();
        enable_lora = true;
        
        int state = radio->begin(915.0, 125.0, 125.0, 250.0, 10, 16);
        // Initial hardware setup
        if (state == RADIOLIB_ERR_NONE) {
            Serial.println(F("Initialization successful!"));
        } else {
            Serial.print(F("RF69 Init Failed, code: "));
            Serial.println(state);
            return;
        }

        // Set Data Shaping to GFSK (Gaussian Filter)
        // RADIOLIB_SHAPING_1_0 is the macro for BT = 1.0
        radio->setDataShaping(RADIOLIB_SHAPING_1_0);

        // Set Sync Word (Must match the Receiver!)
        // Using the common RF69 default: 0x2D 0xD4
        uint8_t syncWord[] = {0x2D, 0xD4};
        radio->setSyncWord(syncWord, 2);

        // --- SET UP THE INTERRUPT ---
        // Tell RadioLib to call 'setFlag' when DIO0/INT goes HIGH
        radio->setDio0Action(setFlag);

        Serial.println(F("[Receiver] Listening for packets..."));
        state = radio->startReceive();
        if (state != RADIOLIB_ERR_NONE) {
            Serial.print(F("startReceive failed, code "));
            Serial.println(state);
        }

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
    Module* mod;
    RF69* radio;
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
        if (receivedFlag) {
            // 1. Reset the flag immediately
            receivedFlag = false;

            // 2. Buffer for the incoming data
            uint8_t buf[256];

            // 3. Read the data out of the radio's FIFO buffer
            // (Notice we use readData() now, not receive())
            // Lock the SPI bus before checking hardware
            int state = RADIOLIB_ERR_UNKNOWN;
            if (xSemaphoreTake(_busMutex, pdMS_TO_TICKS(5))) {
                state = radio->readData(buf, 256);
                xSemaphoreGive(_busMutex);
            }

            if (state == RADIOLIB_ERR_NONE) {
                size_t len = radio->getPacketLength();
                handleRX(buf, len);
            } else if (state == RADIOLIB_ERR_CRC_MISMATCH) {
            Serial.println(F("CRC Error - Data corrupted"));
            } else {
            Serial.print(F("readData failed, code "));
            Serial.println(state);
            }

            // 4. IMPORTANT: Put the radio back into receive mode!
            radio->startReceive();
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
                int state = radio->transmit(pkt.data(), pkt.size());
                //_rf69->waitPacketSent(); //Removed, causing blocking behavior on bus if interrupt is not received
                //TODO: Maybe put back into the code with timeout feature
                xSemaphoreGive(_busMutex);

                if (state == RADIOLIB_ERR_NONE) {
                    //Serial.println(F("Success!"));
                } else if (state == RADIOLIB_ERR_PACKET_TOO_LONG) {
                    Serial.println(F("Error: Packet too long"));
                } else {
                    Serial.print(F("Error: "));
                    Serial.println(state);
                }
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