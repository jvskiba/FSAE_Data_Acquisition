#pragma once

#include <Wire.h>
#include <RTClib.h>
#include "esp_timer.h"

class RTCClock {
private:
    RTC_DS3231 rtc;

    bool rtc_ok = false;

    // Offset between ESP monotonic timer and RTC time
    // rtc_time_us = esp_timer_get_time() + offset_us
    int64_t offset_us = 0;

public:

    // -----------------------------
    // Initialize RTC
    // -----------------------------
    bool begin(int sda, int scl) {

        Wire.begin(sda, scl);

        if (!rtc.begin()) {
            Serial.println("RTC not found");
            rtc_ok = false;
            return false;
        }

        rtc_ok = true;

        if (rtc.lostPower()) {
            Serial.println("RTC lost power!");

            // Optional:
            // Set RTC to compile time
            rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
        }

        sync();

        return true;
    }

    // -----------------------------
    // Sync ESP timer to RTC
    // -----------------------------
    void sync() {

        if (!rtc_ok) {
            return;
        }

        DateTime now = rtc.now();

        int64_t rtc_us =
            ((int64_t)now.unixtime() * 1000000LL);

        int64_t esp_us = esp_timer_get_time();

        offset_us = rtc_us - esp_us;

        Serial.print("RTC Synced: ");
        Serial.println(rtc_us);
    }

    // -----------------------------
    // Get current time in us
    // -----------------------------
    int64_t now_us() const {

        return esp_timer_get_time() + offset_us;
    }

    // -----------------------------
    // Get current time in seconds
    // -----------------------------
    uint32_t now_s() const {

        return now_us() / 1000000ULL;
    }

    // -----------------------------
    // Print readable timestamp
    // -----------------------------
    void printTime() const {

        int64_t us = now_us();

        time_t sec = us / 1000000ULL;

        struct tm *tm_info = gmtime(&sec);

        char buffer[32];

        strftime(buffer, sizeof(buffer),
                 "%Y-%m-%d %H:%M:%S",
                 tm_info);

        Serial.print(buffer);

        Serial.print(".");

        Serial.println((uint32_t)(us % 1000000ULL));
    }

    // -----------------------------
    // RTC status
    // -----------------------------
    bool isValid() const {
        return rtc_ok;
    }
};