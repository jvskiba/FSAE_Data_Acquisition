#pragma once
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <Arduino.h>

class NTP_Client {
public:
    // Function types for sending/receiving
    using SendFunction = void(*)(StaticJsonDocument<128>&);
    using ReceiveFunction = bool(*)(StaticJsonDocument<256>&);

    // Constructor
    NTP_Client(SendFunction sendMessage, ReceiveFunction getResponse)
        : sendMessage(sendMessage), getResponse(getResponse) {}

    // ---- Call this in loop() ----
    void run() {
        unsigned long nowMs = millis();

        switch (state) {
            case IDLE:
                if (nowMs - lastSync >= syncIntervalMs) {
                    startSync();
                }
                break;

            case WAITING_RESPONSE:
                checkResponse();
                if (nowMs - requestTime > responseTimeoutMs) {
                    Serial.println("NTP: Response timeout");
                    state = IDLE;
                }
                break;
        }
    }

    // ---- Get corrected microseconds since boot ----
    long long correctedNow_us() const {
        return esp_timer_get_time() + clockOffset_us;
    }

private:
    // ---- Configuration ----
    static constexpr long long MAX_DELAY_US = 50000;     // 50 ms
    static constexpr int N = 30;                          // smoothing window
    static constexpr unsigned long syncIntervalMs = 1000; // sync every 1 s
    static constexpr unsigned long responseTimeoutMs = 200; // wait 200 ms max

    // ---- State ----
    enum State { IDLE, WAITING_RESPONSE };
    State state = IDLE;

    unsigned long lastSync = 0;
    unsigned long requestTime = 0;
    long long t1_sent = 0;

    // ---- Filtering ----
    long long offsets[N] = {0};
    int idx = 0, count = 0;
    long long smoothedOffset = 0;
    long long clockOffset_us = 0;
    long long last_clockOffset_us = 0;
    long long init_clockOffset = 0;

    // ---- Function pointers ----
    SendFunction sendMessage;
    ReceiveFunction getResponse;

    // ---- Step 1: start sync (send message) ----
    void startSync() {
        StaticJsonDocument<128> doc;
        t1_sent = esp_timer_get_time();
        doc["type"] = "SYNC_REQ";
        doc["t1"] = t1_sent;

        sendMessage(doc);
        requestTime = millis();
        state = WAITING_RESPONSE;
        Serial.printf("sent T1: %lld\n", t1_sent);
    }

    // ---- Step 2: check if a response has arrived ----
    void checkResponse() {
        StaticJsonDocument<256> resp;
        if (!getResponse(resp))
            return; // no response yet

        state = IDLE;
        lastSync = millis();

        long long t1 = resp["t1"];
        long long t2 = resp["t2"];
        long long t3 = resp["t3"];
        long long t4 = esp_timer_get_time();

        long long offset_us = ((t2 - t1) + (t3 - t4)) / 2;
        long long delay_us  = (t4 - t1) - (t3 - t2);

        Serial.printf("T1:%lld T2:%lld T3:%lld T4:%lld\n", t1, t2, t3, t4);

        if (init_clockOffset == 0) {
            init_clockOffset = offset_us;
            updateOffset(offset_us);
            Serial.println("Initial offset received");
        }

        if (delay_us < MAX_DELAY_US) {
            updateOffset(offset_us);
            last_clockOffset_us = clockOffset_us;
            Serial.printf("Sync: offset=%lld us (%.3f ms), delay=%.3f ms\n",
                          smoothedOffset, smoothedOffset / 1000.0, delay_us / 1000.0);
        } else {
            Serial.printf("Delay too high: %lld us\n", delay_us);
        }
    }

    // ---- Offset smoothing ----
    void updateOffset(long long newOffset) {
        offsets[idx] = newOffset;
        idx = (idx + 1) % N;
        if (count < N) count++;

        long long sum = 0;
        for (int i = 0; i < count; i++)
            sum += offsets[i];
        smoothedOffset = sum / count;
        clockOffset_us = smoothedOffset;
    }
};
