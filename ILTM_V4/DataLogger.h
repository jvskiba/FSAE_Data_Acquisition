#include <SD.h>
#include <unordered_set>
#include "DataBuffer.h"

struct SignalDef {
    uint8_t id;
    String name;
};

class DataLogger {
private:
    File logFile;
    String basePath;
    String filePrefix;
    int logCount = 0;
    SharedDataBuffer* dataBus;
    std::vector<SignalDef>* signals = nullptr;
    long lastFlush = 0;
    long long (*timeCallback)();
    SPIClass *spi = nullptr;

    volatile bool loggingActive = false; // Atomic flag for Start/Stop
    TaskHandle_t sdTaskHandle = NULL;

    static void sdTaskWrapper(void* pvParameters) {
        ((DataLogger*)pvParameters)->runLogger();
    }

    String generateFilename() {
        time_t now_s = now_us() / 1000000LL;
        struct tm* t = gmtime(&now_s); // use UTC time instead of localtime()

        // --- Build filename ---
        char buf[96];
        snprintf(buf, sizeof(buf),
                "%s/%04d-%02d-%02d_%02d-%02d-%02d_%s%d.bin",
                basePath.c_str(),
                t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
                t->tm_hour, t->tm_min, t->tm_sec,
                filePrefix.c_str(), logCount++);

        return String(buf);
    }

    void detectExistingLogs() {
        // FIX: Ensure you open the directory correctly
        File dir = SD.open(basePath);
        if (!dir || !dir.isDirectory()) {
            Serial.println("Log directory not found.");
            return;
        }

        int maxNum = -1;
        while (true) {
            File file = dir.openNextFile();
            if (!file) break;

            // On ESP32 SD, file.name() might return the full path or just the name
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

void writeHeader(File& file) {
    if (!signals) {
        Serial.println("Signals not initialized!");
        return;
    }
    uint32_t magic = 0xDEADBEEF;
    file.write((uint8_t*)&magic, sizeof(magic));
    //file.write((uint8_t)VERSION, 8);

    uint8_t num_ids = signals->size();
    file.write(&num_ids, 1);

    for (const auto& s : *signals) {
        uint8_t id = s.id;

        const char* name = s.name.c_str();
        uint8_t len = strlen(name);  // force actual C-string length

        file.write(&id, 1);
        file.write(&len, 1);
        file.write((uint8_t*)name, len);
    }
}
public:
    DataLogger() : dataBus(nullptr), timeCallback(nullptr) {}

    bool begin(SharedDataBuffer* bus, const String& path, const String& prefix, SPIClass *i_spi, std::vector<SignalDef>* i_signals) {
        dataBus = bus;
        basePath = path;
        filePrefix = prefix;
        spi = i_spi;
        signals = i_signals;

        if (!SD.begin(-1, *spi, 4000000)) {
            Serial.println("SD Begin Failed");
            return false;
        }
        
        if (!SD.exists(basePath)) SD.mkdir(basePath);
        
        detectExistingLogs();
        
        // Spawn the logger task on Core 1
        loggingActive = true;
        xTaskCreatePinnedToCore(sdTaskWrapper, "SD_Writer", 4096, this, 1, NULL, 1);
        return true;
    }

    // Call these in the future to control the logger via Telemetry/Buttons
    void startLogging() { loggingActive = true; }
    void stopLogging() { loggingActive = false; }

    void runLogger() {
        while (true) {
            if (loggingActive) {
                String filename = generateFilename();
                logFile = SD.open(filename, FILE_WRITE);
                
                const int BLOCK_SIZE = 64;
                LogEntry writeCache[BLOCK_SIZE];
                int cacheIdx = 0;

                Serial.printf("Starting Log File: %s\n", filename.c_str());

                //Write Header - Meta Data
                writeHeader(logFile);

                // Nested loop: continues as long as logging is active
                while (loggingActive) {
                    LogEntry entry;
                    if (dataBus->pop(entry)) {
                        writeCache[cacheIdx++] = entry;
                    }

                    if (cacheIdx >= BLOCK_SIZE || (millis() - lastFlush > 2000 && cacheIdx > 0)) {
                        logFile.write((uint8_t*)writeCache, cacheIdx * sizeof(LogEntry));
                        logFile.flush();
                        cacheIdx = 0;
                        lastFlush = millis();
                    }
                    if (cacheIdx == 0) vTaskDelay(pdMS_TO_TICKS(2));
                }

                // Graceful Exit: Flush any remaining data before closing
                logFile.close();
                logCount++; // Increment for the next file
                Serial.println("Log stopped and file closed safely.");
            }
            
            vTaskDelay(pdMS_TO_TICKS(10)); // Wait while idle
        }
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

    
};