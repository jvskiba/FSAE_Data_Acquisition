#pragma once
#include <Arduino.h>

#define DEBUG true
#define MAXSIGNALS 256
struct __attribute__((packed)) LogEntry {
    uint32_t timestamp;
    uint8_t id;
    float value;
};
struct LatestValue {
    float value;
    uint32_t timestamp;
};

class SharedDataBuffer {
private:
    static const int SIZE = 1024; // Large buffer in RAM
    LogEntry buffer[SIZE];
    LatestValue liveTable[MAXSIGNALS];  // indexed by id
    bool valid[MAXSIGNALS] = {false};
    int head = 0;
    int tail = 0;
    SemaphoreHandle_t mutex;

public:
    SharedDataBuffer() { mutex = xSemaphoreCreateMutex(); }

    // Producer
    void push(LogEntry entry) {
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(1))) {
            buffer[head] = entry;
            head = (head + 1) % SIZE;
            if (head == tail) {
                tail = (tail + 1) % SIZE; // Overwrite if full
                if (DEBUG) Serial.println("Ring Buffer Overflow");
            }
            xSemaphoreGive(mutex);
            liveTable[entry.id] = {entry.value, entry.timestamp};
            valid[entry.id] = true;
        }
    }

    // Consumer (SD Logger on Core 1)
    bool pop(LogEntry &entry) {
        bool success = false;
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(1))) {
            if (head != tail) {
                entry = buffer[tail];
                tail = (tail + 1) % SIZE;
                success = true;
            }
            xSemaphoreGive(mutex);
        }
        return success;
    }

    // Telemetry (Core 0/1: Peek latest N samples without moving tail)
    void peekRecent(LogEntry* out, int count) {
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(1))) {
            for (int i = 0; i < count; i++) {
                int idx = (head - 1 - i + SIZE) % SIZE;
                out[i] = buffer[idx];
            }
            xSemaphoreGive(mutex);
        }
    }

    // Returns all signals updated within the last 'maxAge' ms
    std::unordered_map<uint8_t, float> getLatestSnapshot(uint32_t maxAge) {
        std::unordered_map<uint8_t, float> snapshot;
        uint32_t now = millis();
        for (int i = 0; i < MAXSIGNALS; i++) {
            if (valid[i] && (now - liveTable[i].timestamp < maxAge)) {
                snapshot[i] = liveTable[i].value;
            }
        }
        return snapshot;
    }
};