#include <SD.h>
#include <unordered_set>
#include "esp_crc.h"
#include "DataBuffer.h"

#define VERSION 1

#define TaskCoreNum 1
#define TaskPriorityLevel 5

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
    long logStart_t = 0;
    long max_log_ms_t = 600000; // Default to 10min
    long long (*timeCallback)();
    SPIClass *spi = nullptr;

    volatile bool loggingActive = false; // Atomic flag for Start/Stop
    TaskHandle_t sdTaskHandle = NULL;

    static void sdTaskWrapper(void* pvParameters) {
        ((DataLogger*)pvParameters)->runLogger();
    }

    String generateFilename() {
        time_t now_s = now_us() / 1000000LL;
        struct tm* t = gmtime(&now_s); // use UTC time instead of localtime() //TODO: Change to local time

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
        file.write((uint8_t)VERSION);  // writes 1 byte

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

        if (!SD.begin(-1, *spi, 16000000)) {
            Serial.println("SD Begin Failed");
            return false;
        }
        
        if (!SD.exists(basePath)) SD.mkdir(basePath);
        
        detectExistingLogs();
        
        loggingActive = true; // Default log on startup
        xTaskCreatePinnedToCore(sdTaskWrapper, "SD_Writer", 8192, this, TaskPriorityLevel, NULL, TaskCoreNum);
        return true;
    }

    void setMaxLogSeconds(uint32_t sec) {
        max_log_ms_t = sec * 1000;
    }

    void startLogging() { loggingActive = true; }
    void stopLogging() { loggingActive = false; }

 // Writes a byte to the COBS buffer and updates the COBS state machine in-place
inline void addByteToCobs(uint8_t b, uint8_t *dst, size_t &write_idx, size_t &code_idx, uint8_t &code) {
    if (b == 0) {
        dst[code_idx] = code;
        code_idx = write_idx++;
        code = 1;
    } else {
        dst[write_idx++] = b;
        code++;
        if (code == 0xFF) { // Max chunk without 0x00
            dst[code_idx] = code;
            code_idx = write_idx++;
            code = 1;
        }
    }
}

// Stream bytes of a structure directly into the COBS frame
inline void addBlockToCobs(const uint8_t *src, size_t len, uint8_t *dst, size_t &write_idx, size_t &code_idx, uint8_t &code) {
    for (size_t i = 0; i < len; i++) {
        addByteToCobs(src[i], dst, write_idx, code_idx, code);
    }
}

void runLogger() {
    const int ENTRIES_PER_BLOCK = 56;
    
    // Allocate the output buffer ONCE in static RAM or stack (not re-allocated each flush)
    // 56 entries * 9B + 4B CRC = 508B raw -> ~512B COBS encoded max
    const size_t MAX_COBS_FRAME_SIZE = 520; 
    uint8_t cobsFrame[MAX_COBS_FRAME_SIZE];

    while (true) {
        if (loggingActive) {
            String filename = generateFilename();
            logFile = SD.open(filename, FILE_WRITE);
            Serial.printf("Starting Log File: %s\n", filename.c_str());

            writeHeader(logFile);

            logStart_t = millis();
            lastFlush = millis();

            // COBS Frame State variables
            size_t write_idx = 1;  // Start at 1 (0 is reserved for first COBS overhead byte)
            size_t code_idx = 0;
            uint8_t code = 1;
            
            int entriesInBlock = 0;
            uint32_t runningCRC = 0xFFFFFFFF; // Hardware CRC Seed

            while (loggingActive) {
                LogEntry entry;

                // 1. POP & PROCESS: Stream directly from dataBus into COBS Frame Buffer
                while (entriesInBlock < ENTRIES_PER_BLOCK && dataBus->pop(entry)) {
                    // Update running HW CRC over raw entry bytes (Incremental)
                    runningCRC = esp_crc32_le(runningCRC, (uint8_t*)&entry, sizeof(LogEntry));

                    // Stream raw entry directly into COBS frame buffer
                    addBlockToCobs((uint8_t*)&entry, sizeof(LogEntry), cobsFrame, write_idx, code_idx, code);
                    entriesInBlock++;
                }

                // 2. FLUSH CONDITION: Block is full
                if (entriesInBlock >= ENTRIES_PER_BLOCK) {
                    // Finalize hardware CRC
                    uint32_t finalCRC = runningCRC ^ 0xFFFFFFFF;

                    // Stream 4-byte CRC directly into COBS buffer
                    addBlockToCobs((uint8_t*)&finalCRC, sizeof(uint32_t), cobsFrame, write_idx, code_idx, code);

                    // Terminate COBS state & append 0x00 frame delimiter
                    cobsFrame[code_idx] = code;
                    cobsFrame[write_idx++] = 0x00; 

                    // ZERO-COPY WRITE: Send entire COBS frame directly to SD driver
                    logFile.write(cobsFrame, write_idx);

                    // Reset State for Next Block
                    write_idx = 1;
                    code_idx = 0;
                    code = 1;
                    entriesInBlock = 0;
                    runningCRC = 0xFFFFFFFF;
                    lastFlush = millis();
                }

                // 3. INACTIVITY TIMEOUT: Partial flush if no data coming in
                // TODO: I dont think this does what I want it to
                if (millis() - lastFlush > 5000) {
                    if (entriesInBlock > 0) {
                        uint32_t finalCRC = runningCRC ^ 0xFFFFFFFF;
                        addBlockToCobs((uint8_t*)&finalCRC, sizeof(uint32_t), cobsFrame, write_idx, code_idx, code);
                        
                        cobsFrame[code_idx] = code;
                        cobsFrame[write_idx++] = 0x00;

                        logFile.write(cobsFrame, write_idx);

                        // Reset
                        write_idx = 1;
                        code_idx = 0;
                        code = 1;
                        entriesInBlock = 0;
                        runningCRC = 0xFFFFFFFF;
                    }
                    logFile.flush();
                    lastFlush = millis();
                }

                // Break log file if max duration reached and buffer is clear
                if (millis() - logStart_t > max_log_ms_t && entriesInBlock == 0) {
                    break;
                }

                // Yield briefly to RTOS watchdog if queue was empty
                if (entriesInBlock == 0) {
                    vTaskDelay(pdMS_TO_TICKS(2));
                }
            }

            // GRACEFUL EXIT: Flush any remaining items in frame
            if (entriesInBlock > 0) {
                uint32_t finalCRC = runningCRC ^ 0xFFFFFFFF;
                addBlockToCobs((uint8_t*)&finalCRC, sizeof(uint32_t), cobsFrame, write_idx, code_idx, code);
                
                cobsFrame[code_idx] = code;
                cobsFrame[write_idx++] = 0x00;

                logFile.write(cobsFrame, write_idx);
            }

            logFile.flush();
            logFile.close();
            logCount++;
            Serial.println("Log stopped and file closed safely.");
        }
        
        vTaskDelay(pdMS_TO_TICKS(10)); // Idle delay
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