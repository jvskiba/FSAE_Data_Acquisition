#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>
#include <unordered_map>
#include "SD_MMC.h"
#include "config.h"

class ConfigManager {
public:
    struct SystemSettings {
        LoggerConfig logger;
        // Grouped by CAN ID for O(1) lookup performance
        std::unordered_map<uint32_t, std::vector<CanSignal>> canMap;
        std::vector<GPSSignal> gpsSignals;
    } settings;

    ConfigManager() {}

    bool begin(const char* filename = "/config.json") {
        _filename = filename;
        loadDefaults(); // Set hardcoded fallback first

        if (!SD_MMC.exists(_filename)) {
            Serial.println("No config.json found, creating one with defaults...");
            save();
            return true;
        }
        return load();
    }

    bool load() {
        File file = SD_MMC.open(_filename, FILE_READ);
        if (!file) return false;

        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, file);
        file.close();

        if (error) {
            Serial.print("JSON Load Failed: ");
            Serial.println(error.c_str());
            return false;
        }

        // 1. Load Logger Config
        JsonObject log = doc["logger"];
        settings.logger.sampleRateHz = log["sampleRateHz"] | 50;
        settings.logger.telemRateHz = log["telemRateHz"] | 20;
        settings.logger.useNaNForMissing = log["useNaNForMissing"] | false;
        
        // Use String assignment to avoid strdup memory leaks
        settings.logger.ssid = log["ssid"].as<const char*>();
        settings.logger.password = log["password"].as<const char*>();
        settings.logger.host = log["host"].as<const char*>();
        
        settings.logger.udpPort = log["udpPort"] | 5002;
        settings.logger.tcpPort = log["tcpPort"] | 2000;

        // 2. Load Smart CAN Structure
        JsonArray canArr = doc["canSignals"];
        if (!canArr.isNull()) {
            settings.canMap.clear(); // Wipe defaults to load from file
            for (JsonObject s : canArr) {
                CanSignal sig;
                sig.canId       = s["id"];
                sig.startByte   = s["start"];
                sig.length      = s["len"];
                sig.littleEndian = s["le"];
                sig.mult        = s["mult"];
                sig.div         = s["div"];
                sig.name        = s["name"].as<String>();
                sig.is_signed   = s["signed"];

                settings.canMap[sig.canId].push_back(sig);
            }
        }
        return true;
    }

    bool save() {
        File file = SD_MMC.open(_filename, FILE_WRITE);
        if (!file) return false;

        JsonDocument doc;

        // 1. Save Logger Config
        JsonObject log = doc["logger"].to<JsonObject>();
        log["sampleRateHz"] = settings.logger.sampleRateHz;
        log["telemRateHz"]  = settings.logger.telemRateHz;
        log["useNaNForMissing"] = settings.logger.useNaNForMissing;
        log["ssid"]     = settings.logger.ssid;
        log["password"] = settings.logger.password;
        log["host"]     = settings.logger.host;
        log["udpPort"]  = settings.logger.udpPort;
        log["tcpPort"]  = settings.logger.tcpPort;

        // 2. Save CAN Signals from the Map
        JsonArray canArr = doc["canSignals"].to<JsonArray>();
        for (auto const& [id, signals] : settings.canMap) {
            for (const auto& s : signals) {
                JsonObject obj = canArr.add<JsonObject>();
                obj["id"]     = s.canId;
                obj["start"]  = s.startByte;
                obj["len"]    = s.length;
                obj["le"]     = s.littleEndian;
                obj["mult"]   = s.mult;
                obj["div"]    = s.div;
                obj["name"]   = s.name;
                obj["signed"] = s.is_signed;
            }
        }

        bool success = (serializeJsonPretty(doc, file) != 0);
        file.close();
        return success;
    }

private:
    const char* _filename;

    void loadDefaults() {
        // Load logger defaults
        settings.logger = defaultConfig;

        // Load CAN defaults into the Map structure
        settings.canMap.clear();
        for (size_t i = 0; i < defaultSignalCount_Can; i++) {
            uint32_t id = defaultSignals_Can[i].canId;
            settings.canMap[id].push_back(defaultSignals_Can[i]);
        }
    }
};