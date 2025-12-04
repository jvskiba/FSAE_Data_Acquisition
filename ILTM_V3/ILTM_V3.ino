#include <HardwareSerial.h>
#include <Arduino.h>
#include <vector>

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
    Serial.print("Sending hex payload: ");
    Serial.println(hexPayload);

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

void sendAT(String cmd, bool print = true) {
    RYLR.println(cmd);
    if (print) {
        Serial.print(">> "); Serial.println(cmd);
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

    sendAT("AT+ADDRESS=1");
    sendAT("AT+NETWORKID=18");
    sendAT("AT+BAND=915000000");
    sendAT("AT+PARAMETER=7,9,1,8");

    delay(200);

    // Send name packet once, then wait a bit to let it be received
    sendNamePacket();
    delay(500);
}

// ---------------------------------------------------------------------------
// LOOP — SEND VALUES AT 5 Hz
// ---------------------------------------------------------------------------

unsigned long lastSend = 0;

void loop() {
    unsigned long now = millis();
    if (now - lastSend >= 200) {
        lastSend = now;
        sendValueTLVPacket();

        // SIGNAL SIMULATION (optional)
        signalValues[0].value += 0.01f; // voltage
        signalValues[1].value += 0.02f; // current
        signalValues[2].value += 0.05f; // temp
    }
}
