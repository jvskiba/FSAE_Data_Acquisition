#pragma once
#include <Arduino.h>
#include "DataBuffer.h"

#define DEBUG true

#define PAYLOADBUFLEN 256


//TODO: Fix this parser so that it has checksum and proper error handling
// Current theory is that it crashes when a 0xFF group byte gets sent as it overflows the decode array.
//TODO: Still crashes when vecNav disconnected, prob bc trying to read more bytes than exists as the stream stops

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

class VectorNavManager {
public:
    // Constructor using existing Serial
    VectorNavManager(HardwareSerial* serial)
        : _serial(serial), _ownsSerial(false) {}

    // Constructor using RX/TX pins
    VectorNavManager(int rxPin, int txPin, HardwareSerial& serial)
        : _rxPin(rxPin), _txPin(txPin), _serial(&serial), _ownsSerial(true)
    {}

    void begin(uint32_t baud, SharedDataBuffer& bus) {
        if (_ownsSerial) {
            _serial->begin(baud, SERIAL_8N1, _rxPin, _txPin);
        } else {
            _serial->begin(baud);
        }

        globalBus = &bus;

        if (globalBus == nullptr) {
            if (DEBUG) Serial.println("Bus not set");
            return;
        }

        decodePlan.reserve(64);

        xTaskCreatePinnedToCore(
            taskWrapper,
            "VectorNavTask",
            8192,
            this,
            1,
            &_taskHandle,
            1
        );
    }

    std::vector<SignalDef> getSignalVector() const {
        return std::vector<SignalDef>(signals, signals + sizeof(signals) / sizeof(signals[0]));
    }

    void disable() {
        enable_task = false;
    }

    void enable() {
        enable_task = true;
    }

private:
    HardwareSerial* _serial;
    bool _ownsSerial = false;
    bool enable_task = true;

    int _rxPin = -1;
    int _txPin = -1;
    int _uartNum = 1;

    TaskHandle_t _taskHandle = nullptr;
    SharedDataBuffer* globalBus = nullptr;

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
    uint8_t payloadBuffer[PAYLOADBUFLEN];

    SignalDef signals[15] = {
    {101, "AccelX"},
    {102, "AccelY"},
    {103, "AccelZ"},
    {104, "Yaw"},
    {105, "Pitch"},
    {106, "Roll"},
    {107, "VelNorth"},
    {108, "VelEast"},
    {109, "VelDown"},
    {110, "PosLat"},
    {111, "PosLong"},
    {112, "PosAlt"},
    {113, "GyroX"},
    {114, "GyroY"},
    {115, "GyroZ"},
    };

    // ===== Task =====
    static void taskWrapper(void* param) {
        VectorNavManager* instance = static_cast<VectorNavManager*>(param);
        instance->taskLoop();
    }

    void printHexBytes(const uint8_t* data, size_t length) {
        for (size_t i = 0; i < length; i++) {
            printf("%02X ", data[i]);
        }
        printf("\n");
    }

    void taskLoop() {
        while (true) {
            while (_serial->available()) {
                if (!enable_task) {
                    vTaskDelay(pdMS_TO_TICKS(50));
                    continue;
                }

                uint8_t byte = _serial->read();
                if (!check_sync_byte(byte)) {
                    continue;
                }
                if (readHeader(curHeader) == -1) return;

                if (payloadLength > PAYLOADBUFLEN) return;
                if (_serial->available() < payloadLength) return;
                _serial->readBytes(payloadBuffer, payloadLength);

                if (headerChanged(curHeader, cachedHeader)) {
                    cachedHeader = curHeader;
                    buildDecodePlan(curHeader.groupByte, curHeader.groupFields);
                }

                for (auto& f : decodePlan) {
                    const uint8_t* fieldPtr = payloadBuffer + f.offset;

                    //printf("G %d, F %d,  offset %d (len %d): ", f.group, f.field, f.offset, f.length);
                    //printHexBytes(fieldPtr, f.length);
                    parseField(fieldPtr, f);
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

    void parseField(const uint8_t* data, const FieldDescriptor& f) {
        switch (f.group) {
            case 0:
                switch (f.field) {
                    case 3:
                        parseYPR(data);
                        break;
                    case 5:
                        parseAngularRate(data);
                        break;
                    case 6:
                        parsePosLla(data);
                        break;
                    case 7:
                        parseVelNed(data);
                        break;
                    case 8:
                        parseAccel(data);
                        break;
                    default:
                        if (DEBUG) printf("Unhandled Group 0 Field %d\n", f.field);
                        break;
                }
                break;

            // future groups go here

            default:
                if (DEBUG) printf("Unhandled Group %d Field %d\n", f.group, f.field);
                break;
        }
    }

    void parseYPR(const uint8_t* data_raw) {
        float data[3];

        // memcpy avoids alignment/aliasing issues (don’t get clever here)
        memcpy(data, data_raw, 3 * sizeof(float));
        LogEntry entry;

        if (DEBUG) printf("YPR -> Yaw: %.3f, Pitch: %.3f, Roll: %.3f\n", data[0], data[1], data[2]);
        entry = { (uint32_t)millis(), 104, data[0] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 105, data[1] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 106, data[2] };
        globalBus->push(entry);
    }

    void parsePosLla(const uint8_t* data_raw) {
        double data[3];

        // memcpy avoids alignment/aliasing issues (don’t get clever here)
        memcpy(data, data_raw, 3 * sizeof(double));
        LogEntry entry;

        if (DEBUG) printf("PosLla -> PosLat: %f, PosLon: %f, PosAlt: %f\n", data[0], data[1], data[2]);
        entry = { (uint32_t)millis(), 110, data[0] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 111, data[1] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 112, data[2] };
        globalBus->push(entry);
    }

    void parseVelNed(const uint8_t* data_raw) {
        float data[3];

        // memcpy avoids alignment/aliasing issues (don’t get clever here)
        memcpy(data, data_raw, 3 * sizeof(float));
        LogEntry entry;

        if (DEBUG) printf("VelNed -> VelN: %.3f, VelE: %.3f, VelD: %.3f\n", data[0], data[1], data[2]);
        entry = { (uint32_t)millis(), 107, data[0] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 108, data[1] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 109, data[2] };
        globalBus->push(entry);
    }

    void parseAccel(const uint8_t* data_raw) {
        float data[3];

        // memcpy avoids alignment/aliasing issues (don’t get clever here)
        memcpy(data, data_raw, 3 * sizeof(float));
        LogEntry entry;

        if (DEBUG) printf("Accel -> AccelX: %.3f, AccelY: %.3f, AccelZ: %.3f\n", data[0], data[1], data[2]);
        entry = { (uint32_t)millis(), 101, data[0] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 102, data[1] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 103, data[2] };
        globalBus->push(entry);
    }

    void parseAngularRate(const uint8_t* data_raw) {
        float data[3];

        // memcpy avoids alignment/aliasing issues (don’t get clever here)
        memcpy(data, data_raw, 3 * sizeof(float));
        LogEntry entry;

        if (DEBUG) printf("AngularRate -> GyroX: %.3f, GyroY: %.3f, GyroZ: %.3f\n", data[0], data[1], data[2]);
        entry = { (uint32_t)millis(), 113, data[0] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 114, data[1] };
        globalBus->push(entry);
        entry = { (uint32_t)millis(), 115, data[2] };
        globalBus->push(entry);
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
        if (_serial->available() < 1) return -1;
        header.groupByte = _serial->read();

        if (header.groupByte != 0x01) return -1; //TODO: Really shit fix, This is a giant bandaid

        // Count active groups
        header.groupCount = 0;
        for (uint8_t g = 0; g < 6; g++) {
            if (header.groupByte & (1 << g)) {
                header.groupCount++;
            }
        }
        if (DEBUG) printHexBytes(&header.groupByte, 1);

        // Read group fields
        for (uint8_t i = 0; i < header.groupCount; i++) {
            if (_serial->available() < 2) return -1;
            uint8_t low = _serial->read();
            uint8_t high = _serial->read();
            header.groupFields[i] = (high << 8) | low;
            //printHexBytes(reinterpret_cast<uint8_t*>(&header.groupFields[i]), 2);
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