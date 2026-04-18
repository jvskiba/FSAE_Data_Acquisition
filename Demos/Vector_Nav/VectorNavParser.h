#pragma once
#include <Arduino.h>

struct FieldDescriptor {
    uint8_t group;     // 0–5
    uint8_t field;     // 0–15
    uint16_t offset;   // byte offset in payload
    uint8_t length;    // from groupLen
};

struct VNHeader {
    uint8_t groupByte;
    uint8_t groupCount;
    uint16_t groupFields[6]; // max 6 groups
};

class VectorNavParser {
public:
    // Constructor using existing Serial
    VectorNavParser(HardwareSerial* serial)
        : _serial(serial), _ownsSerial(false) {}

    // Constructor using RX/TX pins
    VectorNavParser(int rxPin, int txPin, int uartNum = 1)
        : _rxPin(rxPin), _txPin(txPin), _uartNum(uartNum), _ownsSerial(true)
    {
        _serial = new HardwareSerial(uartNum);
    }

    void begin(uint32_t baud = 115200) {
        if (_ownsSerial) {
            _serial->begin(baud, SERIAL_8N1, _rxPin, _txPin);
        } else {
            _serial->begin(baud);
        }

        xTaskCreatePinnedToCore(
            taskWrapper,
            "VectorNavTask",
            4096,
            this,
            1,
            &_taskHandle,
            1
        );
    }

private:
    HardwareSerial* _serial;
    bool _ownsSerial = false;

    int _rxPin = -1;
    int _txPin = -1;
    int _uartNum = 1;

    TaskHandle_t _taskHandle = nullptr;

    VNHeader curHeader;
    VNHeader cachedHeader;

    // ===== Decode plan =====
    std::vector<FieldDescriptor> decodePlan;
    uint16_t payloadLength = 0;

    // ===== Cached header =====
    uint8_t cachedGroupByte = 0;
    uint16_t cachedGroupFields[6];
    uint8_t cachedGroupCount = 0;

    // ===== Buffers =====
    uint8_t payloadBuffer[256];

    // ===== Task =====
    static void taskWrapper(void* param) {
        VectorNavParser* instance = static_cast<VectorNavParser*>(param);
        instance->taskLoop();
    }

    void taskLoop() {
        while (true) {
            while (_serial->available()) {
                uint8_t byte = _serial->read();
                if (!check_sync_byte(byte)) {
                    continue;
                }
                readHeader(curHeader);

                _serial->readBytes(payloadBuffer, payloadLength);

                if (headerChanged(curHeader, cachedHeader)) {
                    cachedHeader = curHeader;
                    buildDecodePlan(curHeader.groupByte, curHeader.groupFields);
                }

                for (auto& f : decodePlan) {
                    //parseField(payloadBuffer + f.offset, f);
                }
            }

            vTaskDelay(pdMS_TO_TICKS(10));
        }
    }

    bool check_sync_byte(uint8_t byte) {
        if (byte == 0xFA) {
            return true;
        }
        return false;
    }

    bool headerChanged(const VNHeader& a, const VNHeader& b) {
        if (a.groupByte != b.groupByte) return true;
        if (a.groupCount != b.groupCount) return true;

        for (uint8_t i = 0; i < a.groupCount; i++) {
            if (a.groupFields[i] != b.groupFields[i]) return true;
        }

        return false;
    }

    void parseField() {

    }

    void buildDecodePlan(uint8_t groupByte, uint16_t* groupFields) {
        decodePlan.clear();
        uint16_t offset = 0;
        uint8_t groupIdx = 0;

        for (uint8_t g = 0; g < 6; g++) {
            if (groupByte & (1 << g)) {
                uint16_t mask = groupFields[groupIdx++];

                for (uint8_t bit = 0; bit < 16; bit++) {
                    if (mask & (1 << bit)) {
                        uint8_t len = groupLen[g][bit];

                        FieldDescriptor f;
                        f.group = g;
                        f.field = bit;
                        f.offset = offset;
                        f.length = len;

                        decodePlan.push_back(f);

                        offset += len;
                    }
                }
            }
        }

        payloadLength = offset;
    }


    static constexpr uint8_t groupLen[6][16] = {
        {8, 8, 8, 12, 16, 12, 24, 12, 12, 24, 20, 28, 2, 4, 8, 0},
        {8, 8, 8, 2, 8, 8, 8, 4, 0, 0, 0, 0, 0, 0, 0, 0},
        {2, 12, 12, 12, 4, 4, 16, 12, 12, 12, 12, 2, 40, 0, 0, 0},
        {8, 8, 2, 1, 1, 24, 24, 12, 12, 12, 4, 4, 32, 0, 0, 0},
        {2, 12, 16, 36, 12, 12, 12, 12, 12, 12, 28, 24, 0, 0, 0, 0},
        {2, 24, 24, 12, 12, 12, 12, 12, 12, 4, 4, 68, 64, 0, 0, 0}
    };

    uint16_t readHeader(VNHeader& header) {
        uint16_t payloadLength = 0;

        // Read group byte
        header.groupByte = _serial->read();

        // Count active groups
        header.groupCount = 0;
        for (uint8_t g = 0; g < 6; g++) {
            if (header.groupByte & (1 << g)) {
                header.groupCount++;
            }
        }

        // Read group fields
        for (uint8_t i = 0; i < header.groupCount; i++) {
            uint8_t low = _serial->read();
            uint8_t high = _serial->read();
            header.groupFields[i] = (high << 8) | low;
        }

        // Compute payload
        uint8_t groupIndex = 0;
        for (uint8_t g = 0; g < 6; g++) {
            if (header.groupByte & (1 << g)) {
                uint16_t mask = header.groupFields[groupIndex++];

                for (uint8_t bit = 0; bit < 16; bit++) {
                    if (mask & (1 << bit)) {
                        payloadLength += groupLen[g][bit];
                    }
                }
            }
        }

        uint16_t headerLength = 1 + (header.groupCount * 2);

        return 2 + headerLength + payloadLength + 2;
    }
};