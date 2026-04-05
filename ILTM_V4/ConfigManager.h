#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>
#include <unordered_map>
#include "SD.h"
#include "config.h"

class ConfigManager {
public:
    struct SystemSettings {
        MainConfig main;
        // Grouped by CAN ID for O(1) lookup performance
        std::unordered_map<uint32_t, std::vector<CanSignal>> canMap;
        std::unordered_map<uint32_t, std::vector<SIMSignal>> simMap;
        std::unordered_map<uint32_t, std::vector<IMUSignal>> imuMap;
        std::vector<SIMSignal> SIMSignals;
    } settings;

    ConfigManager() {}

    bool begin(const char* filename = "/config.json") {
        _filename = filename;
        loadDefaults(); // Set hardcoded fallback first

        if (!SD.exists(_filename)) {
            Serial.println("No config.json found, creating one with defaults...");
            save();
            return true;
        }
        return load();
    }

    bool load() {
        File file = SD.open(_filename, FILE_READ);
        if (!file) return false;

        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, file);
        file.close();

        if (error) {
            Serial.print("JSON Load Failed: ");
            Serial.println(error.c_str());
            return false;
        }

        // 1. Load main Config
        JsonObject log = doc["main"];
        settings.main.telemRateHz_Lora = log["telemRateHz_Lora"] | 5; //Cannot be 0
        settings.main.telemRateHz_Wifi = log["telemRateHz_Wifi"] | 20; //Cannot be 0
        settings.main.useNaNForMissing = log["useNaNForMissing"] | false;
        
        // Use String assignment to avoid strdup memory leaks
        settings.main.ssid = log["ssid"].as<const char*>();
        settings.main.password = log["password"].as<const char*>();
        settings.main.host = log["host"].as<const char*>();
        
        settings.main.udpPort = log["udpPort"] | 5002;
        settings.main.tcpPort = log["tcpPort"] | 2000;

        settings.main.lora_address = log["lora_address"].as<const char*>();
        settings.main.lora_netId = log["lora_netId"].as<const char*>();
        settings.main.lora_band = log["lora_band"].as<const char*>();
        settings.main.lora_param = log["lora_param"].as<const char*>();

        // 2. Load Smart CAN Structure
        JsonArray canArr = doc["canSignals"];
        if (!canArr.isNull()) {
            settings.canMap.clear(); // Wipe defaults to load from file
            for (JsonObject s : canArr) {
                CanSignal sig;
                sig.id       = s["id"];
                sig.name        = s["name"].as<String>();
                sig.canId       = s["canId"];
                sig.startByte   = s["start"];
                sig.length      = s["len"];
                sig.littleEndian = s["le"];
                sig.mult        = s["mult"];
                sig.div         = s["div"];
                sig.is_signed   = s["signed"];

                settings.canMap[sig.canId].push_back(sig);
            }
        }

        JsonArray simArr = doc["SIMSignals"];
        if (!simArr.isNull()) {
            settings.simMap.clear(); // Wipe defaults to load from file
            for (JsonObject s : simArr) {
                SIMSignal sig;
                sig.id       = s["id"];
                sig.name        = s["name"].as<String>();

                settings.simMap[sig.id].push_back(sig);
            }
        }

        JsonArray imuArr = doc["IMUSignals"];
        if (!imuArr.isNull()) {
            settings.imuMap.clear(); // Wipe defaults to load from file
            for (JsonObject s : imuArr) {
                IMUSignal sig;
                sig.id       = s["id"];
                sig.name        = s["name"].as<String>();

                settings.imuMap[sig.id].push_back(sig);
            }
        }
        return true;
    }

    bool save() {
        SD.remove(_filename); //Ensure overwite
        File file = SD.open(_filename, FILE_WRITE);
        if (!file) {
            Serial.println("Failed to open file for writing");
            return false;
        }

        JsonDocument doc;

        // 1. Save main Config
        JsonObject log = doc["main"].to<JsonObject>();
        log["telemRateHz_Lora"] = settings.main.telemRateHz_Lora;
        log["telemRateHz_Wifi"]  = settings.main.telemRateHz_Wifi;
        log["useNaNForMissing"] = settings.main.useNaNForMissing;
        log["ssid"]     = settings.main.ssid;
        log["password"] = settings.main.password;
        log["host"]     = settings.main.host;
        log["udpPort"]  = settings.main.udpPort;
        log["tcpPort"]  = settings.main.tcpPort;
        log["lora_address"]  = settings.main.lora_address;
        log["lora_netId"]  = settings.main.lora_netId;
        log["lora_band"]  = settings.main.lora_band;
        log["lora_param"]  = settings.main.lora_param;

        // 2. Save CAN Signals from the Map
        JsonArray canArr = doc["canSignals"].to<JsonArray>();
        for (auto const& [canId, signals] : settings.canMap) {
            for (const auto& s : signals) {
                JsonObject obj = canArr.add<JsonObject>();
                obj["id"]   = s.id;
                obj["name"]   = s.name;
                obj["canId"]     = s.canId;
                obj["start"]  = s.startByte;
                obj["len"]    = s.length;
                obj["le"]     = s.littleEndian;
                obj["mult"]   = s.mult;
                obj["div"]    = s.div;
                obj["signed"] = s.is_signed;
            }
        }

        JsonArray simArr = doc["SIMSignals"].to<JsonArray>();
        for (auto const& [canId, signals] : settings.simMap) {
            for (const auto& s : signals) {
                JsonObject obj = simArr.add<JsonObject>();
                obj["id"]   = s.id;
                obj["name"]   = s.name;
            }
        }

        JsonArray imuArr = doc["IMUSignals"].to<JsonArray>();
        for (auto const& [canId, signals] : settings.imuMap) {
            for (const auto& s : signals) {
                JsonObject obj = imuArr.add<JsonObject>();
                obj["id"]   = s.id;
                obj["name"]   = s.name;
            }
        }

        if (serializeJsonPretty(doc, file) == 0) {
            Serial.println("JSON Write Failed");
            file.flush();
            return false;
        }
        file.flush();
        file.close();
        Serial.println("Config Saved");
        return true;
    }

private:
    const char* _filename;

    void loadDefaults() {
        // Load main defaults
        settings.main = defaultConfig;

        // Load CAN defaults into the Map structure
        size_t defaultSignalCount_Can = sizeof(defaultSignals_Can) / sizeof(defaultSignals_Can[0]);
        settings.canMap.clear();
        for (size_t i = 0; i < defaultSignalCount_Can; i++) {
            uint32_t id = defaultSignals_Can[i].canId;
            settings.canMap[id].push_back(defaultSignals_Can[i]);
        }

        size_t defaultSignalCount_SIM = sizeof(defaultSignals_SIM) / sizeof(defaultSignals_SIM[0]);
        settings.simMap.clear();
        for (size_t i = 0; i < defaultSignalCount_SIM; i++) {
            uint32_t id = defaultSignals_SIM[i].id;
            settings.simMap[id].push_back(defaultSignals_SIM[i]);
        }

        size_t defaultSignalCount_IMU = sizeof(defaultSignals_IMU) / sizeof(defaultSignals_IMU[0]);
        settings.imuMap.clear();
        for (size_t i = 0; i < defaultSignalCount_IMU; i++) {
            uint32_t id = defaultSignals_IMU[i].id;
            settings.imuMap[id].push_back(defaultSignals_IMU[i]);
        }
    }
};