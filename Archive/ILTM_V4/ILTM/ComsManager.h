#pragma once

#include <Arduino.h>
#include <SoftwareSerial.h>

#define DEBUG true

class ComsManager {
public:
    ComsManager(uint8_t rxPin, uint8_t txPin, uint8_t pttPin)
        : _serial(rxPin, txPin), _pttPin(pttPin) {}

    void begin() {
        _serial.begin(9600);  // Datasheet default

        pinMode(_pttPin, OUTPUT);
        digitalWrite(_pttPin, HIGH); // default to RX mode

        delay(100);
    }

    void pttOn() {
        if (ptt_enable) digitalWrite(_pttPin, LOW); // TX mode
        if (DEBUG) Serial.println("[PTT] TX ENABLED");
    }

    void pttOff() {
        digitalWrite(_pttPin, HIGH); // RX mode
        if (DEBUG) Serial.println("[PTT] TX DISABLED");
    }

    // Basic send command
    void sendCommand(const String& cmd) {
        String fullCmd = cmd + "\r\n";

        if (DEBUG) {
            Serial.print("[TX] ");
            Serial.println(fullCmd);
        }

        _serial.print(fullCmd);
    }

    // Read response (blocking with timeout)
    String readResponse(uint32_t timeout = 100) {
        String response = "";
        uint32_t start = millis();

        while (millis() - start < timeout) {
            while (_serial.available()) {
                char c = _serial.read();
                response += c;
            }

            // crude but effective: stop when newline received
            if (response.endsWith("\r\n")) {
                break;
            }
        }

        if (DEBUG && response.length()) {
            Serial.print("[RX] ");
            Serial.println(response);
        }

        return response;
    }

    // Handshake
    bool connect() {
        sendCommand("AT+DMOCONNECT");
        String resp = readResponse();

        return resp.indexOf("+DMOCONNECT:0") != -1;
    }

    // Set group (core config)
    bool setGroup(
        int bw,
        float txFreq,
        float rxFreq,
        const String& txCxcss,
        int squelch,
        const String& rxCxcss
    ) {
        String cmd = "AT+DMOSETGROUP=" +
                     String(bw) + "," +
                     String(txFreq, 4) + "," +
                     String(rxFreq, 4) + "," +
                     txCxcss + "," +
                     String(squelch) + "," +
                     rxCxcss;

        sendCommand(cmd);
        String resp = readResponse();

        return resp.indexOf("+DMOSETGROUP:0") != -1;
    }

    // Set volume (1–8)
    bool setVolume(int level) {
        String cmd = "AT+DMOSETVOLUME=" + String(level);
        sendCommand(cmd);
        String resp = readResponse();

        return resp.indexOf("+DMOSETVOLUME:0") != -1;
    }

    // Read RSSI
    int getRSSI() {
        sendCommand("RSSI?");
        String resp = readResponse();

        int idx = resp.indexOf("RSSI:");
        if (idx != -1) {
            return resp.substring(idx + 5).toInt();
        }

        return -1;
    }

    void pttDisable() {
        ptt_enable = false;
    }

    void pttEnable() {
        ptt_enable = true;
    }

private:
    SoftwareSerial _serial;
    uint8_t _pttPin;
    bool ptt_enable = true;
};