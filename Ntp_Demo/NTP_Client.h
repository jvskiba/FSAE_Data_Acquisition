#pragma once
#include <ArduinoJson.h>
#include <esp_timer.h>
#include <Arduino.h>
#include <TinyGPSPlus.h>
#include <time.h>

void IRAM_ATTR onPPS_ISR_Stub();


time_t timegm(struct tm *t) {
    time_t local = mktime(t);
    struct tm *gmt = gmtime(&local);
    return local + difftime(local, mktime(gmt));
}

class NTP_Client {
public:
    static NTP_Client* ntpClientPtr;
    // Function types for sending/receiving
    using SendFunction = void(*)(StaticJsonDocument<128>&);

    // Constructor
    NTP_Client(SendFunction sendMessage)
        : sendMessage(sendMessage) {}

    void attachSerial(HardwareSerial* serialPort, uint32_t baud, int rxPin, int txPin) {
        this->serial = serialPort;
        serial->begin(baud, SERIAL_8N1, rxPin, txPin);
    }

    // ---- Call this in loop() ----
    void run() {
        unsigned long nowMs = millis();

        while (serial && serial->available() > 0) {
            gps.encode(serial->read());
        }

        switch (state) {
            case IDLE:
                if (nowMs - lastSync >= syncIntervalMs) {
                    startSync();
                }
                break;

            case WAITING_RESPONSE:
                if (nowMs - requestTime > responseTimeoutMs) {
                    Serial.println("NTP: Response timeout");
                    state = IDLE;
                }
                //printGPSStatus();
                break;
        }

        if (ppsFlag) {
            portENTER_CRITICAL(&mux);
            uint32_t interval = ppsMicros - ppsMicrosLast;
            ppsFlag = false;
            portEXIT_CRITICAL(&mux);
            long long diff = gpsMicrosSinceEpoch() - correctedNow_us();
            Serial.printf("Interval: %lu, GPSMicros: %lld, Diff: %lld\n", interval, gpsMicrosSinceEpoch(), diff);
        } 
        
    }

    void handleMessage(const JsonDocument& msg) {
        String type = msg["type"] | "";
        if (type == "SYNC_RESP") {
            handleSyncResponse(msg);
        }
    }


    void begin(int ppsPin) {
        ntpClientPtr = this;  // register this instance
        pinMode(ppsPin, INPUT);
        attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS_ISR_Stub, RISING);
    }

    void IRAM_ATTR handlePPS_ISR() {
        portENTER_CRITICAL_ISR(&mux);
        ppsMicrosLast = ppsMicros;
        ppsMicros = micros();
        ppsFlag = true;
        portEXIT_CRITICAL_ISR(&mux);
    }

    // ---- Get corrected microseconds since boot ----
    long long correctedNow_us() {
        uint64_t now = esp_timer_get_time();
        uint64_t dt = now - lastMicros;
        lastMicros = now;

        // Gradually adjust offset toward target
        double error = target_Offset_us - cur_Offset_us;
        cur_Offset_us += error * alpha;

        // Apply monotonicity guard (never go backwards)
        double corrected = now + cur_Offset_us;
        if (corrected < lastCorrected) corrected = lastCorrected;
        lastCorrected = corrected;

        return corrected;
    }

private:
    // ---- Configuration ----
    static constexpr long long MAX_DELAY_US = 25000;     // Accept BLANK us max
    static constexpr int N = 30;                          // smoothing window
    static constexpr unsigned long syncIntervalMs = 1000; // sync every 1 s
    static constexpr unsigned long responseTimeoutMs = 50; // wait BLANK ms max
    static constexpr float alpha = 0.1; // Max Adjustment to current offset

    // ---- State ----
    enum State { IDLE, WAITING_RESPONSE };
    State state = IDLE;

    TinyGPSPlus gps;
    HardwareSerial* serial = nullptr;

    unsigned long lastSync = 0;
    unsigned long requestTime = 0;
    unsigned int packetId = 0;

    // ---- Filtering ----
    long long offsets[N] = {0};
    int idx = 0, count = 0;
    long long cur_Offset_us = 0;
    long long target_Offset_us = 0;
    long long lastCorrected = 0;
    long long lastMicros = 0;
    bool first_offset = true;

    volatile uint32_t ppsMicros = 0;
    volatile uint32_t ppsMicrosLast = 0;
    volatile bool ppsFlag = false;

    portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

    // ---- Function pointers ----
    SendFunction sendMessage;

    // ---- Step 1: start sync (send message) ----
    void startSync() {
        StaticJsonDocument<128> doc;
        long long t1_sent = esp_timer_get_time();
        doc["type"] = "SYNC_REQ";
        doc["t1"] = t1_sent;
        doc["id"] = ++packetId;

        sendMessage(doc);
        requestTime = millis();
        state = WAITING_RESPONSE;
    }

    // ---- Step 2: check if a response has arrived ----
    void handleSyncResponse(const JsonDocument& resp) {
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

        if (first_offset) {
            first_offset = false;
            updateOffset(offset_us);
            cur_Offset_us = offset_us;
            Serial.println("Initial offset received");
            return;
        }

        if (delay_us < MAX_DELAY_US) {
            updateOffset(offset_us);
            Serial.printf("Sync: offset=%.3f ms, smoothed=%.3f ms, delay=%.3f ms\n",
                          offset_us / 1000.0, target_Offset_us / 1000.0, delay_us / 1000.0);
        } else {
            Serial.printf("Delay too high: %lld us\n", delay_us);
        }
        //printHumanTime(correctedNow_us());
        //printHumanTime(gpsMicrosSinceEpoch());
        printHumanTime(gpsMicrosSinceEpoch() - correctedNow_us());
    }

    // ---- Offset smoothing ----
    void updateOffset(long long newOffset) {
        offsets[idx] = newOffset;
        idx = (idx + 1) % N;
        if (count < N) count++;

        long long sum = 0;
        for (int i = 0; i < count; i++)
            sum += offsets[i];
        target_Offset_us = sum / count;
    }

    long long gpsMicrosSinceEpoch() {
        if (!gps.time.isValid() || !gps.date.isValid()) return 0;

        struct tm t;
        t.tm_year = gps.date.year() - 1900;
        t.tm_mon  = gps.date.month() - 1;
        t.tm_mday = gps.date.day();
        t.tm_hour = gps.time.hour();
        t.tm_min  = gps.time.minute();
        t.tm_sec  = gps.time.second();
        time_t epochSec = timegm(&t);

        long long microsSincePPS = esp_timer_get_time() - ppsMicros;
        if (microsSincePPS < 0) microsSincePPS = 0;

        return (long long)epochSec * 1000000LL + microsSincePPS;
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

NTP_Client* NTP_Client::ntpClientPtr = nullptr;

void IRAM_ATTR onPPS_ISR_Stub() {
    if (NTP_Client::ntpClientPtr) NTP_Client::ntpClientPtr->handlePPS_ISR();
}
