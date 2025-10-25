#pragma once
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <Arduino.h>
#include <TinyGPSPlus.h>
#include <time.h>

class NTP_Client {
public:
    // Function types for sending/receiving
    using SendFunction = void(*)(StaticJsonDocument<128>&);
    using ReceiveFunction = bool(*)(StaticJsonDocument<256>&);

    // Constructor
    NTP_Client(SendFunction sendMessage, ReceiveFunction getResponse, TinyGPSPlus gps_arg)
        : sendMessage(sendMessage), getResponse(getResponse) {
            gps = gps_arg;
        }

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
                printGPSStatus();
                break;
        }

        if (ppsFlag && gps.time.isUpdated()) {
            portENTER_CRITICAL(&mux);
            uint32_t interval = ppsMicros - ppsMicrosLast;
            ppsFlag = false;
            portEXIT_CRITICAL(&mux);
            Serial.printf("%lu  \n", interval);
        } 
        
    }

    void begin(int ppsPin) {
        attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS, RISING);
    }

    // ---- Get corrected microseconds since boot ----
    long long correctedNow_us() const {
        return esp_timer_get_time() + clockOffset_us;
    }

private:
    // ---- Configuration ----
    static constexpr long long MAX_DELAY_US = 25000;     // Accept BLANK us max
    static constexpr int N = 30;                          // smoothing window
    static constexpr unsigned long syncIntervalMs = 1000; // sync every 5 s
    static constexpr unsigned long responseTimeoutMs = 50; // wait BLANK ms max

    // ---- State ----
    enum State { IDLE, WAITING_RESPONSE };
    State state = IDLE;

    TinyGPSPlus gps;

    unsigned long lastSync = 0;
    unsigned long requestTime = 0;
    long long t1_sent = 0;
    unsigned int packetId = 0;

    // ---- Filtering ----
    long long offsets[N] = {0};
    int idx = 0, count = 0;
    long long smoothedOffset = 0;
    long long clockOffset_us = 0;
    long long last_clockOffset_us = 0;
    long long init_clockOffset = 0;

    volatile uint32_t ppsMicros = 0;
    volatile uint32_t ppsMicrosLast = 0;
    volatile bool ppsFlag = false;

    portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

    // ---- Function pointers ----
    SendFunction sendMessage;
    ReceiveFunction getResponse;

    void IRAM_ATTR onPPS() {
        portENTER_CRITICAL_ISR(&mux);
        ppsMicrosLast = ppsMicros;
        ppsMicros = micros();
        ppsFlag = true;
        portEXIT_CRITICAL_ISR(&mux);
    }

    // ---- Step 1: start sync (send message) ----
    void startSync() {
        StaticJsonDocument<128> doc;
        t1_sent = esp_timer_get_time();
        doc["type"] = "SYNC_REQ";
        doc["t1"] = t1_sent;
        doc["id"] = ++packetId;

        sendMessage(doc);
        requestTime = millis();
        state = WAITING_RESPONSE;
    }

    // ---- Step 2: check if a response has arrived ----
    void checkResponse() {
        StaticJsonDocument<256> resp;
        if (!getResponse(resp))
            return; // no response yet
        if (resp["id"].as<int>() != packetId)
            return;  // ignore stale packet

        state = IDLE;
        lastSync = millis();

        long long t1 = resp["t1"];
        long long t2 = resp["t2"];
        long long t3 = resp["t3"];
        long long t4 = esp_timer_get_time();

        long long offset_us = ((t2 - t1) + (t3 - t4)) / 2;
        long long delay_us  = (t4 - t1) - (t3 - t2);

        //Serial.printf("T1:%lld T2:%lld T3:%lld T4:%lld\n", t1, t2, t3, t4);

        if (init_clockOffset == 0) {
            init_clockOffset = offset_us;
            updateOffset(offset_us);
            Serial.println("Initial offset received");
        }

        if (delay_us < MAX_DELAY_US) {
            updateOffset(offset_us);
            long long offset_diff = last_clockOffset_us - offset_us;
            last_clockOffset_us = clockOffset_us;
            Serial.printf("Sync: offset=%.3f ms, smoothed=%.3f ms, delay=%.3f ms\n",
                          offset_us / 1000.0, smoothedOffset / 1000.0, delay_us / 1000.0);
            Serial.printf("Offset Diff: %lld\n", offset_diff);
        } else {
            Serial.printf("Delay too high: %lld us\n", delay_us);
        }
        printHumanTime(correctedNow_us());
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

    uint64_t gpsUnixMicroseconds() {
        if (!gps.date.isValid() || !gps.time.isValid())
            return 0; // invalid reading

        
        struct tm t = {0};
        t.tm_year = gps.date.year() - 1900;
        t.tm_mon  = gps.date.month() - 1;
        t.tm_mday = gps.date.day();
        t.tm_hour = gps.time.hour();
        t.tm_min  = gps.time.minute();
        t.tm_sec  = gps.time.second();
        int64_t now = esp_timer_get_time();
        int64_t pps_micros = now - ppsMicros;

        time_t epochSeconds = mktime(&t);  // convert to seconds since epoch (UTC)

        // TinyGPS++ gives hundredths of a second precision (centiseconds)
        int64_t micros = (int64_t)epochSeconds * 1000000ULL
                        + gps.time.centisecond() * 10000ULL;

        return micros;
    }


    void printHumanTime(long long microsSinceEpoch) {
        time_t seconds = microsSinceEpoch / 1000000;  // convert µs → seconds
        struct tm timeinfo;
        gmtime_r(&seconds, &timeinfo);  // convert to UTC (use localtime_r for local time)

        int microseconds = microsSinceEpoch % 1000000;  // fractional part

        // Format: YYYY-MM-DD HH:MM:SS.UUUUUU
        char buffer[40];
        snprintf(buffer, sizeof(buffer),
                "%04d-%02d-%02d %02d:%02d:%02d.%06d UTC",
                timeinfo.tm_year + 1900,
                timeinfo.tm_mon + 1,
                timeinfo.tm_mday,
                timeinfo.tm_hour,
                timeinfo.tm_min,
                timeinfo.tm_sec,
                microseconds);

        Serial.println(buffer);
    }

    void printGPSStatus() {
        Serial.println("----- GPS Status -----");

        if (gps.location.isValid()) {
            Serial.printf("Lat: %.6f, Lon: %.6f\n", gps.location.lat(), gps.location.lng());
        } else {
            Serial.println("Location: INVALID");
        }

        if (gps.date.isValid() && gps.time.isValid()) {
            Serial.printf("UTC Time: %02d:%02d:%02d\n", gps.time.hour(), gps.time.minute(), gps.time.second());
        } else {
            Serial.println("Time: INVALID");
        }

        if (gps.satellites.isValid()) {
            Serial.printf("Satellites: %d\n", gps.satellites.value());
        } else {
            Serial.println("Satellites: INVALID");
        }

        if (gps.hdop.isValid()) {
            Serial.printf("HDOP: %.1f\n", gps.hdop.hdop());
        }

        Serial.println("-----------------------\n");
    }
};
