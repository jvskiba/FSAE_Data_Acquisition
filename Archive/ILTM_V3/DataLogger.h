#pragma once
#include <Arduino.h>
#include <FS.h>
#include "SD_MMC.h"
#include <time.h>

class DataLogger {
public:
    struct Source {
        String name;
        unsigned long interval;
        unsigned long lastLog;
        String (*callback)();
        String header; // <-- NEW: stores column names for that data type
    };

    DataLogger() : logCount(0), basePath("/logs"), filePrefix("log"), numSources(0), timeCallback(nullptr) {}

    bool begin(const String& path, const String& prefix, uint8_t clkPin, uint8_t CMDPin, uint8_t D0Pin) {
        basePath = path;
        filePrefix = prefix;

        if (!SD_MMC.setPins(clkPin, CMDPin, D0Pin)) {
            Serial.println("Pin configuration failed!");
            return false;
        } 

        if (!initSD(3)) return false;

        // FIX: SD_MMC uses the FS interface. Use SD_MMC directly for these calls.
        if (!SD_MMC.exists(basePath)) {
            if (!SD_MMC.mkdir(basePath)) {
                Serial.println("Failed to create directory!");
                return false;
            }
        }

        detectExistingLogs();
        startNewLog();
        return true; // Return true even if path already existed
    }

    void addSource(const String& name, unsigned long interval, String (*callback)(), const String& header = "data") {
        if (numSources >= MAX_SOURCES) return;
        sources[numSources++] = { name, interval, 0, callback, header };
    }

    void setTimeCallback(long long (*cb)()) {
        timeCallback = cb;
    }

    long long now_us() {
        if (timeCallback) {
            return timeCallback();
        } else {
            return millis();
        }
    }


    void update() {
        unsigned long now = millis();
        for (int i = 0; i < numSources; i++) {
            if (now - sources[i].lastLog >= sources[i].interval) {
                sources[i].lastLog = now;
                writeEntry(sources[i]);
            }
        }
        if (bufferPos >= BUFFER_SIZE - 128) flushBuffer(); // safety margin
    }

    void startNewLog() {
        if (logFile) {
            Serial.print("Log already started");
            return;
        }
        String filename = makeFilename();
        logFile = SD_MMC.open(filename, FILE_WRITE);
        if (!logFile) {
            Serial.println("Failed to open log file!");
            return;
        }

        bufferPos = 0;
        appendToBuffer("time_local,time_global,source\n");
        for (int i = 0; i < numSources; i++) {
            String out = "    ,    ," + sources[i].name + "," + sources[i].header + "\n";
            appendToBuffer(out.c_str());
        }
        flushBuffer();

        Serial.print("Logging to: ");
        Serial.println(filename);
    }

    void endLog() {
        flushBuffer();
        if (logFile) {
            logFile.close();
            Serial.println("Log file closed.");
        }
    }

private:
    // --- Configuration constants ---
    static const int MAX_SOURCES = 10;
    static const size_t BUFFER_SIZE = 2048;
    long long (*timeCallback)();

    // --- Data members ---
    Source sources[MAX_SOURCES];
    int numSources;
    String basePath, filePrefix;
    int logCount;
    File logFile;

    // --- Buffered write members ---
    char buffer[BUFFER_SIZE];
    size_t bufferPos = 0;

    // --- Initialization helpers ---
    bool initSD(int retries = 5) {
        for (int i = 0; i < retries; i++) {
            if (SD_MMC.begin("/sdcard", true)) {
                Serial.println("SD card initialized.");
                return true;
            }
            Serial.println("SD init failed, retrying...");
            delay(500);
        }
        Serial.println("SD init failed after retries.");
        return false;
    }

    

    void detectExistingLogs() {
        // FIX: Ensure you open the directory correctly
        File dir = SD_MMC.open(basePath);
        if (!dir || !dir.isDirectory()) {
            Serial.println("Log directory not found.");
            return;
        }

        int maxNum = -1;
        while (true) {
            File file = dir.openNextFile();
            if (!file) break;

            // On ESP32 SD_MMC, file.name() might return the full path or just the name
            // Depending on the core version. We'll check for the prefix.
            String name = file.name();
            if (name.indexOf(filePrefix) != -1) {
                int idx = name.lastIndexOf(filePrefix) + filePrefix.length();
                int num = name.substring(idx).toInt();
                if (num > maxNum) maxNum = num;
            }
            file.close();
        }
        dir.close();
        logCount = maxNum + 1;
    }


    String makeFilename() {
        time_t now_s = now_us() / 1000000LL;
        struct tm* t = gmtime(&now_s); // use UTC time instead of localtime()

        // --- Build filename ---
        char buf[96];
        snprintf(buf, sizeof(buf),
                "%s/%04d-%02d-%02d_%02d-%02d-%02d_%s%d.csv",
                basePath.c_str(),
                t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
                t->tm_hour, t->tm_min, t->tm_sec,
                filePrefix.c_str(), logCount++);

        return String(buf);
    }

    void writeEntry(const Source& src) {
        String data = src.callback();
        if (data.length() == 0) return;

        char line[256];
        snprintf(line, sizeof(line), "%lu,%.3f,%s,%s\n", (unsigned long)millis(), now_us() / 1000.0, src.name.c_str(), data.c_str());
        appendToBuffer(line);
    }

    void appendToBuffer(const char* str) {
        size_t len = strlen(str);
        if (bufferPos + len >= BUFFER_SIZE)
            flushBuffer();
        memcpy(buffer + bufferPos, str, len);
        bufferPos += len;
    }

    void flushBuffer() {
        if (bufferPos == 0 || !logFile) return;
        //Serial.println(buffer);
        logFile.write((uint8_t*)buffer, bufferPos);
        logFile.flush();
        bufferPos = 0;
    }
};
