#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>
#include "SD_MMC.h"
#include "config.h"

class ConfigManager {
public:
    // This mirrors your config.h structures but in a single container
    struct SystemSettings {
        LoggerConfig logger;
        std::vector<CanSignal> canSignals;
        std::vector<GPSSignal> gpsSignals;
    } settings;

    ConfigManager() {}

    bool begin(const char* filename = "/config.json") {
        _filename = filename;
        
        // Load defaults first so we have a fallback
        loadDefaults();

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

        // Allocate a buffer based on expected complexity
        // For ~20 signals, 8KB is usually plenty for ESP32
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
        settings.logger.ssid = strdup(log["ssid"] | "FBI_Safehouse");
        settings.logger.password = strdup(log["password"] | "icanttellyou");
        settings.logger.host = strdup(log["host"] | "192.168.2.206");
        settings.logger.udpPort = log["udpPort"] | 5002;
        settings.logger.tcpPort = log["tcpPort"] | 2000;

        // 2. Load CAN Signals (Clear defaults if JSON has signals)
        JsonArray canArr = doc["canSignals"];
        if (!canArr.isNull()) {
            settings.canSignals.clear();
            for (JsonObject s : canArr) {
                CanSignal sig;
                sig.canId = s["id"];
                sig.startByte = s["start"];
                sig.length = s["len"];
                sig.littleEndian = s["le"];
                sig.mult = s["mult"];
                sig.div = s["div"];
                sig.name = s["name"].as<String>();
                sig.is_signed = s["signed"];
                settings.canSignals.push_back(sig);
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
        log["telemRateHz"] = settings.logger.telemRateHz;
        log["useNaNForMissing"] = settings.logger.useNaNForMissing;
        log["ssid"] = settings.logger.ssid;
        log["password"] = settings.logger.password;
        log["host"] = settings.logger.host;
        log["udpPort"] = settings.logger.udpPort;
        log["tcpPort"] = settings.logger.tcpPort;

        // 2. Save CAN Signals
        JsonArray canArr = doc["canSignals"].to<JsonArray>();
        for (const auto& s : settings.canSignals) {
            JsonObject obj = canArr.add<JsonObject>();
            obj["id"] = s.canId;
            obj["start"] = s.startByte;
            obj["len"] = s.length;
            obj["le"] = s.littleEndian;
            obj["mult"] = s.mult;
            obj["div"] = s.div;
            obj["name"] = s.name;
            obj["signed"] = s.is_signed;
        }

        if (serializeJsonPretty(doc, file) == 0) {
            file.close();
            return false;
        }

        file.close();
        return true;
    }

private:
    const char* _filename;

    void loadDefaults() {
        // Load logger defaults
        settings.logger = defaultConfig;

        // Load CAN defaults from config.h
        settings.canSignals.clear();
        for(size_t i=0; i < defaultSignalCount_Can; i++) {
            settings.canSignals.push_back(defaultSignals_Can[i]);
        }
    }
};