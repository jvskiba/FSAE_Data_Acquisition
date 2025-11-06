#pragma once
#include <Arduino.h>
#include <FS.h>
#include <SD.h>
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

    bool begin(const String& path, const String& prefix, uint8_t csPin = 5) {
        basePath = path;
        filePrefix = prefix;
        if (!initSD(csPin)) {
            Serial.println("SD initialization failed!");
            return false;
        }
        if (!SD.exists(basePath)) SD.mkdir(basePath);
        detectExistingLogs();
        startNewLog();
        return true;
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
        unsigned long now = now_us();
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
        logFile = SD.open(filename, FILE_WRITE);
        if (!logFile) {
            Serial.println("Failed to open log file!");
            return;
        }

        bufferPos = 0;
        appendToBuffer("timestamp,source\n");
        for (int i = 0; i < numSources; i++) {
            String out = "    ," + sources[i].name + "," + sources[i].header + "\n";
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
    bool initSD(uint8_t csPin, int retries = 5) {
        for (int i = 0; i < retries; i++) {
            if (SD.begin(csPin)) {
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
        File dir = SD.open(basePath);
        if (!dir) return;

        int maxNum = -1;
        while (true) {
            File file = dir.openNextFile();
            if (!file) break;

            String name = file.name();
            file.close();
            if (name.indexOf(filePrefix) != -1) {
                int idx = name.lastIndexOf(filePrefix) + filePrefix.length();
                int num = name.substring(idx).toInt();
                if (num > maxNum) maxNum = num;
            }
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
        snprintf(line, sizeof(line), "%.3f,%s,%s\n", now_us() / 1000.0, src.name.c_str(), data.c_str());
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
        logFile.write((uint8_t*)buffer, bufferPos);
        logFile.flush();
        bufferPos = 0;
    }
};
