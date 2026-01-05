#include <HardwareSerial.h>
#include <Arduino.h>
#include <vector>
#include "TLV.h"
#include "NTP_Client.h"

const bool debug = false;

// ==== GPS CONFIG ====
const int gpsRXPin = D0;
const int gpsTXPin = D1;
const int ppsPin = D2;

// Create NTP client
NTP_Client ntp(send);

HardwareSerial GPSSerial(1);

enum ITV_Command : uint8_t {
    CMD_SYNC_REQ  = 0x01,
    CMD_SYNC_RESP = 0x02,
};

using ITVHandler = std::function<void(const TLVMap&)>;

std::unordered_map<uint8_t, ITVHandler> itvHandlers;




// ---------------------------------------------------------------------------
//  USER SIGNAL TABLE
// ---------------------------------------------------------------------------

struct SignalValue {
    String name;
    uint8_t type;
    float value;
    bool recent;
};

const uint8_t defaultSignalCount_T = 3;
uint8_t signalCount_T = defaultSignalCount_T;

SignalValue signalValues[defaultSignalCount_T] = {
    {"Voltage",     10, 12.34f, true},
    {"Current",     11,  5.67f, true},
    {"Temperature", 12, 22.10f, true}
};

// UART for RYLR998
HardwareSerial RYLR(2);

// ---------------------------------------------------------------------------
// HEX HELPER (unchanged but left here for completeness)
// ---------------------------------------------------------------------------

String bytesToHex(const std::vector<uint8_t>& data) {
    const char* hex = "0123456789ABCDEF";
    String out;
    out.reserve(data.size() * 2);

    for (uint8_t b : data) {
        out += hex[(b >> 4) & 0x0F];
        out += hex[b & 0x0F];
    }
    return out;
}

// ---------------------------------------------------------------------------
// SAFER TLV PACKER: use memcpy (portable, no strict-aliasing issues)
// ---------------------------------------------------------------------------

void packTLV(uint8_t type, float value, std::vector<uint8_t>& out) {
    out.push_back(type);
    out.push_back(4);  // float = 4 bytes

    // portable copy of float bytes
    uint8_t tmp[4];
    memcpy(tmp, &value, sizeof(float));

    // push little-endian order (ESP32/AVR are little endian normally)
    for (int i = 0; i < 4; ++i) out.push_back(tmp[i]);
}

// ---------------------------------------------------------------------------
// SEND HEX PACKET THROUGH RYLR (unchanged)
// ---------------------------------------------------------------------------

void sendHexPayload(const std::vector<uint8_t>& pkt) {
    String hexPayload = bytesToHex(pkt);

    // debug print to USB serial so you can see what we're sending
    if (debug) {
        Serial.print("Sending hex payload: ");
        Serial.println(hexPayload);
    }

    RYLR.print("AT+SEND=2,");
    RYLR.print(hexPayload.length());
    RYLR.print(",");
    RYLR.println(hexPayload);
}

// ---------------------------------------------------------------------------
//  SEND NAME PACKET  (ON STARTUP ONLY) - added debug
// ---------------------------------------------------------------------------

void sendNamePacket() {
    std::vector<uint8_t> pkt;
    pkt.push_back((uint8_t) 1);
    for (int i = 0; i < signalCount_T; i++) {
        uint8_t tid  = signalValues[i].type;
        String  name = signalValues[i].name;

        pkt.push_back(tid);
        pkt.push_back((uint8_t)name.length());

        for (int j = 0; j < name.length(); j++)
            pkt.push_back((uint8_t)name[j]);
    }

    Serial.println("Name packet bytes:");
    for (auto b : pkt) {
        Serial.printf("%02X ", b);
    }
    Serial.println();

    sendHexPayload(pkt);
}

// ---------------------------------------------------------------------------
// SEND VALUE PACKET (EVERY 200ms) with DEBUG prints
// ---------------------------------------------------------------------------

void sendValueTLVPacket() {
    std::vector<uint8_t> pkt;

    // debug: print values before packing
    Serial.println("Preparing TLV packet with values:");
    for (int i = 0; i < defaultSignalCount_T; ++i) {
        Serial.printf("  Type %u (%s) = %.6f\n",
                      signalValues[i].type,
                      signalValues[i].name.c_str(),
                      signalValues[i].value);
        packTLV(signalValues[i].type, signalValues[i].value, pkt);
    }

    // debug: print raw TLV bytes
    //Serial.print("Raw TLV bytes: ");
    //for (auto b : pkt) Serial.printf("%02X ", b);
    //Serial.println();

    // send as hex over RYLR
    sendHexPayload(pkt);
}

// ---------------------------------------------------------------------------
// RYLR COMMAND HELPER
// ---------------------------------------------------------------------------

void sendAT(String cmd, bool print = true, bool wait_resp = true) {
    RYLR.println(cmd);
    if (print) {
        Serial.print(">> "); Serial.println(cmd);
    }

    if (wait_resp) {
        String resp = RYLR.readStringUntil('\n');
        resp.trim();
        if (resp.length()) Serial.println("<< " + resp);
    }
}

// ---- Send function ----
void send(const std::vector<uint8_t>& pkt) {
  sendHexPayload(pkt);
}

void receiveAndDispatch() {
    //if (!udp.parsePacket()) return;

    uint8_t buf[256];
    int len = udp.read(buf, sizeof(buf));
    if (len <= 0) return;

    // Decode TLV / ITV
    TLVMap decoded;
    if (!ITV_Decoder::decode(buf, len, decoded)) {
        Serial.println("ITV decode error");
        return;
    }

    // Must have command ID
    if (!decoded.count(0x01)) {
        Serial.println("ITV packet missing command");
        return;
    }

    uint8_t cmd = std::get<uint8_t>(decoded.at(0x01));

    // Dispatch
    auto it = itvHandlers.find(cmd);
    if (it != itvHandlers.end()) {
        it->second(decoded);
    } else {
        Serial.printf("Unhandled ITV cmd: 0x%02X\n", cmd);
    }
}


// ---------------------------------------------------------------------------
// SETUP
// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
    RYLR.begin(115200, SERIAL_8N1, D10, D9);

    delay(1000);
    Serial.println("Init RYLR998...");

    sendAT("AT"); delay(500);
    sendAT("AT+RESET"); delay(500);

    String resp = RYLR.readStringUntil('\n');
    resp.trim();
    if (resp.length()) Serial.println("<< " + resp);

    sendAT("AT+ADDRESS=1", true, true);
    sendAT("AT+NETWORKID=18", true, true);
    sendAT("AT+BAND=915000000", true, true);
    sendAT("AT+PARAMETER=7,9,1,8", true, true);

    delay(200);

    // Send name packet once, then wait a bit to let it be received
    sendNamePacket();
    delay(500);

    ntp.attachSerial(&GPSSerial, 9600, gpsRXPin, gpsTXPin);
    ntp.begin(ppsPin);
    
    //transport->send(bytes.data(), bytes.size());
    itvHandlers[CMD_SYNC_RESP] = [this](const TLVMap& m) {
    handleSyncResponse(m);
};
}

// ---------------------------------------------------------------------------
// LOOP — SEND VALUES AT 5 Hz
// ---------------------------------------------------------------------------

unsigned long lastSend = 0;

void loop() {
    unsigned long now = millis();
    if (now - lastSend >= 500) {
        lastSend = now;

        std::vector<uint8_t> packet;

        ITV::writeName(0x10, "PIE", packet);
        ITV::writeF32(0x10, 3.14159f, packet);
        ITV::writeU32(0x11, uint32_t(1700000012), packet);
        ITV::writeU8(0x12, uint8_t(1), packet);
        ITV::writeBool(0x13, false, packet);
        ITV::writeString(0x20, "DRIVER_OK", packet);

        // send over LoRa / WiFi / CAN / UDP
        sendHexPayload(packet);
    }
    receiveAndDispatch();
    ntp.run();
}
