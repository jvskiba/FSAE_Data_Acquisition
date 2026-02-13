#pragma once
#include <Arduino.h>

struct __attribute__((packed)) LogEntry {
    uint32_t timestamp;
    uint16_t id;
    float value;
};

class SharedDataBuffer {
private:
    static const int SIZE = 1024; // Large buffer in RAM
    LogEntry buffer[SIZE];
    int head = 0;
    int tail = 0;
    SemaphoreHandle_t mutex;

public:
    SharedDataBuffer() { mutex = xSemaphoreCreateMutex(); }

    // Producer (Sensors on Core 0)
    void push(LogEntry entry) {
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(10))) {
            buffer[head] = entry;
            head = (head + 1) % SIZE;
            if (head == tail) tail = (tail + 1) % SIZE; // Overwrite if full
            xSemaphoreGive(mutex);
        }
    }

    // Consumer (SD Logger on Core 1)
    bool pop(LogEntry &entry) {
        bool success = false;
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(10))) {
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
        if (xSemaphoreTake(mutex, pdMS_TO_TICKS(10))) {
            for (int i = 0; i < count; i++) {
                int idx = (head - 1 - i + SIZE) % SIZE;
                out[i] = buffer[idx];
            }
            xSemaphoreGive(mutex);
        }
    }
};