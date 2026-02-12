#include <HardwareSerial.h>
#include <Arduino.h>
#include <vector>
#include <functional>
#include <unordered_map>
#include <deque>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <mcp_can.h>

#include "config.h"
#include "ITV.h"
#include "NTP_Client.h"
#include "DataLogger.h"

// --- PINS ---
#define CAN_CS   D7
#define SD_CS    D8

#define CAN_INT  D6
#define CAN_SCK  D13
#define CAN_MISO D12
#define CAN_MOSI D11

#define RTC_SDA A4
#define RTC_SCK A5

#define RS232_RX D4
#define RS232_TX D5

#define gpsRXPin D0
#define gpsTXPin D1
#define ppsPin D2

// FreeRTOS Delays
#define TASK_DELAY_Main_Loop 10
#define TASK_DELAY_LoRa 20
#define TASK_DELAY_NTP 30
#define TASK_DELAY_LOGGER 10
#define TASK_DELAY_CAN 10

WiFiUDP udp;
LoggerConfig config = defaultConfig;
DataLogger logger;

// === DEBUG ===
const bool debug = true;
const bool simulateCan = false;

// === Status Keepers ===
bool wireless_OK = false;
bool can_OK = false;
bool sd_OK = false;
bool logfile_OK = false;
bool loraBusy = false;
bool txBusy = false;

NTP_Client ntp(send);

HardwareSerial RYLR(2); // UART for RYLR998
WiFiServer server(config.tcpPort);
WiFiClient client;

MCP_CAN CAN(CAN_CS);

using ITVHandler = std::function<void(const ITV::ITVMap&)>;
std::unordered_map<uint8_t, ITVHandler> itvHandlers;

const int allocated_ids = 10;
enum ITV_Command : uint8_t {
    CMD_SYNC_REQ  = 0x01,
    CMD_SYNC_RESP = 0x02,
    CMD_NAME_SYNC_REQ = 0x03,
    CMD_SWITCH_STATE = 0x04
};

std::deque<std::vector<uint8_t>> txQueue;

unsigned long lastTxTime = 0;
unsigned long lastSend = 0;

// Conservative guard time for LoRa airtime
const unsigned long TX_GUARD_MS = 100;
unsigned long rxQuietUntil = 0;

// === Globals for Wi-Fi state tracking ===
unsigned long lastWifiAttempt = 0;
const unsigned long WIFI_RETRY_INTERVAL = 5000; // ms
bool wifiConnecting = false;
bool wifiReportedConnected = false;

// ---------------------------------------------------------------------------
//  USER SIGNAL TABLE
// ---------------------------------------------------------------------------

struct SignalValue {
    std::string name;
    uint8_t type;
    float value;
    bool recent;
    bool recent_telem;
};

enum SystemState {
  STATE_INIT,
  STATE_TX_ONLY,
  STATE_TX_RX
};

SystemState state = STATE_INIT;


SignalValue signalValues[defaultSignalCount_T];

// ---- snapshot logging helpers ----
unsigned long lastSampleMs = 0;
const unsigned long sampleIntervalMs = 1000UL / config.sampleRateHz;
unsigned long lastTelemMs = 0;
const unsigned long telemIntervalMs = 1000UL / config.telemRateHz;
static unsigned long lastFlush = 0;
const unsigned long flushIntervalMS = 1000;

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
SemaphoreHandle_t lora_Tx_Mutex;
SemaphoreHandle_t spi1_Mutex;
SemaphoreHandle_t signal_Mutex;

TaskHandle_t loraTaskHandle = nullptr;

void send(const std::vector<uint8_t>& pkt) {
    queuePacket(pkt);
}

void handleRX(const char* line) {
    char tmp[256];
    strncpy(tmp, line, sizeof(tmp));
    tmp[sizeof(tmp) - 1] = '\0';

    // Skip "+RCV="
    strtok(tmp + 5, ","); // src
    strtok(nullptr, ","); // len
    char* hex = strtok(nullptr, ",");

    if (!hex) return;

    ITV::ITVMap decoded;
    if (!ITV::decode_line(hex, decoded)) {
        Serial.println("ITV decode failed");
        return;
    }
    

    if (!decoded.count(0x01)) return;

    uint8_t cmd = std::get<uint8_t>(decoded.at(0x01));

    if (itvHandlers.count(cmd)) {
        itvHandlers[cmd](decoded);
    } else {
        Serial.printf("Unhandled ITV cmd: 0x%02X\n", cmd);
    }
}

void queuePacket(const std::vector<uint8_t>& pkt) {
    constexpr size_t LORA_MAX = 96;

    std::vector<std::vector<uint8_t>> splitPkts;
    ITV::splitOnTLVBoundaries(pkt, LORA_MAX, splitPkts);

    if (xSemaphoreTake(lora_Tx_Mutex, 0)) {               
        for (const auto& p : splitPkts) {
            txQueue.push_back(p);

            if (debug) {
                Serial.print("TX Queued TLV-safe pkt, bytes=");
                Serial.println(p.size());
            }
        }
        xSemaphoreGive(lora_Tx_Mutex);
    }
}


void processTxQueue() {
    // Clear busy flag by time
    if (txBusy && millis() - lastTxTime > TX_GUARD_MS) {
        txBusy = false;
    }

    // If still busy or nothing to send, return
    if (txBusy || txQueue.empty()) return;

    const auto& pkt = txQueue.front();

    String hex = ITV::bytesToHex(pkt);

    RYLR.print("AT+SEND=2,");
    RYLR.print(pkt.size()*2);
    RYLR.print(",");
    RYLR.println(hex);

    // Mark busy
    txBusy = true;
    lastTxTime = millis();

    // Remove packet from queue
    txQueue.pop_front();

    if (debug) {
        Serial.print("TX Sent, bytes=");
        Serial.println(pkt.size());
    }
}

void pollRYLR() {
    static char line[256];
    static size_t idx = 0;

    while (RYLR.available()) {
        char c = RYLR.read();

        if (c == '\n') {
            line[idx] = 0;
            idx = 0;
            handleRYLRLine(line);
        } else if (idx < sizeof(line) - 1) {
            line[idx++] = c;
        }
    }
}

void handleRYLRLine(const char* line) {
    if (strncmp(line, "+RCV=", 5) == 0) {
        rxQuietUntil = millis() + 10;
        handleRX(line);
    }
    else if (strncmp(line, "+ERR=", 5) == 0) {
        Serial.println(line);

        // Recover from TX error
        txBusy = false;
    }
    // +OK is ignored — unreliable
}


// FreeRTOS Tasks
void loraTask(void* pvParameters) {
    for (;;) {
        // RX path
        pollRYLR();

        // TX path
        if (xSemaphoreTake(lora_Tx_Mutex, 0)) {
            processTxQueue();
            xSemaphoreGive(lora_Tx_Mutex);
        }

        // Don’t hog the CPU
        vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_LoRa));
    }
}

TaskHandle_t ntpTaskHandle = nullptr;
void ntpTask(void* pvParameters) {
    for (;;) {
        ntp.run();
        vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_NTP));
    }
}

TaskHandle_t loggerTaskHandle = nullptr;
void loggerTask(void* pvParameters) {
    for (;;) {
        //Serial.println("Logger Task Run");
        logger.update();
        vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_LOGGER));
    }
}
TaskHandle_t canTaskHandle = nullptr;
void canTask(void* pvParameters) {
    Serial.println("CAN Interrupt Task Started");
    
    for (;;) {
        if (simulateCan) { 
            spoofCAN(); 
            vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_LOGGER));
        } else {
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        }

        //Serial.println("CAN Task Run");
        while (CAN.checkReceive() == CAN_MSGAVAIL) {
            unsigned long rxId;
            byte len = 0;
            byte rxBuf[8];
            
            if (xSemaphoreTake(spi1_Mutex, pdMS_TO_TICKS(5))) {
                if (CAN.readMsgBuf(&rxId, &len, rxBuf) == CAN_OK) {
                    updateSignalsFromFrame(rxId, rxBuf, len);
                }
                xSemaphoreGive(spi1_Mutex);
            }
        }
    }
}
TaskHandle_t uartSenseTaskHandle = nullptr;
void uartSenseTask(void* pvParameters) {
    for (;;) {
        
        vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_CAN));
    }
}

// ---------------------------------------------------------------------------
// Can Signal Helpers
// ---------------------------------------------------------------------------

long long now_us() {
    return ntp.now_us();
}

// Decode raw bytes from a CAN payload per CanSignal
float decodeCanSignal(CanSignal sig, const uint8_t* data) {
    uint32_t raw = 0;

    // Extract raw value (endian-aware)
    if (sig.littleEndian) {
        for (int i = 0; i < sig.length; i++) {
            raw |= (data[sig.startByte + i] << (8 * i));
        }
    } else {
        for (int i = 0; i < sig.length; i++) {
            raw = (raw << 8) | data[sig.startByte + i];
        }
    }

    // Handle signed vs unsigned
    int32_t signed_val = 0;
    if (sig.is_signed) {
        switch (sig.length) {
            case 1:
                signed_val = (int8_t) raw;
                break;
            case 2:
                signed_val = (int16_t) raw;
                break;
            case 4:
                signed_val = (int32_t) raw;
                break;
            default:
                signed_val = (int32_t) raw;
        }
        return (signed_val * sig.mult) / sig.div;
    } else {
        return (raw * sig.mult) / sig.div;
    }
}

// Apply an incoming frame to the signals table
void updateSignalsFromFrame(uint32_t rxId, const uint8_t* rxBuf, uint8_t rxLen) {
  for (size_t i = 0; i < defaultSignalCount_Can; ++i) {
    const CanSignal& s = defaultSignals_Can[i];
    if (s.canId != rxId) continue;

    // bounds check: skip if the bytes we need aren't in this frame
    if ((int)s.startByte + (int)s.length > rxLen) continue;

    const float v = decodeCanSignal(s, rxBuf);
    signalValues[i].value = v;
    signalValues[i].recent = true;
    signalValues[i].recent_telem = true;
  }
}

// This function runs the moment the CAN_INT pin goes LOW
void IRAM_ATTR canISR() {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    // Notify the CAN task to wake up
    vTaskNotifyGiveFromISR(canTaskHandle, &xHigherPriorityTaskWoken);
    // If the CAN task is higher priority than what's running, switch immediately
    if (xHigherPriorityTaskWoken) {
        portYIELD_FROM_ISR();
    }
}

void init_can_module() {
    SPI.begin(CAN_SCK, CAN_MISO, CAN_MOSI);
    // --- Init CAN ---
    if (CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) == CAN_OK) {
        Serial.println("MCP2515 Initialized Successfully!");
        can_OK = true;
        CAN.setMode(MCP_NORMAL);

        CAN.init_Mask(0, 0, 0x000);  // 0x000 mask = accept all IDs
        CAN.init_Filt(0, 0, 0x000);  // doesn't matter
    } else {
        Serial.println("Error Initializing MCP2515...");
    }
}

// ---------------------------------------------------------------------------
// Wifi Helpers
// ---------------------------------------------------------------------------

void init_Wireless_Con() {
  Serial.println("Starting Wi-Fi connection...");
  WiFi.begin(config.ssid, config.password);
  wifiConnecting = true;
  wifiReportedConnected = false;
  lastWifiAttempt = millis();
}

// Returns true if connected, false otherwise
bool update_Wireless_Con() {
  wl_status_t status = WiFi.status();

  if (status == WL_CONNECTED) {
    if (!wifiReportedConnected) {
      Serial.println("\nWi-Fi connected!");
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
      wifiReportedConnected = true;
    }
    return true;  // safe to transmit
  }

  // If not connected, reset flag and retry every interval
  wifiReportedConnected = false;

  if (millis() - lastWifiAttempt >= WIFI_RETRY_INTERVAL) {
    Serial.println("Wi-Fi disconnected, retrying...");
    WiFi.disconnect();
    WiFi.begin(config.ssid, config.password);
    lastWifiAttempt = millis();
  }

  return false; // not connected yet
}

void init_Sockets() {
  udp.begin(config.udpPort); 
  Serial.println("UDP socket opened");
}

// ---------------------------------------------------------------------------
// Telem Signal Helpers
// ---------------------------------------------------------------------------

void initSignalValues() {
  // ----- CAN Signals -----
  for (size_t i = 0; i < defaultSignalCount_Can; ++i) {
    signalValues[i].name  = std::string(defaultSignals_Can[i].name.c_str());
    signalValues[i].value = NAN;
    signalValues[i].recent = false;
    signalValues[i].recent_telem = false;
  }

  // ----- GPS Signals -----
  for (size_t i = 0; i < defaultSignalCount_GPS; ++i) {
    size_t idx = defaultSignalCount_Can + i;
    signalValues[idx].name  = std::string(defaultSignals_GPS[i].name.c_str());
    signalValues[idx].value = NAN;
    signalValues[idx].recent = false;
    signalValues[idx].recent_telem = false;
  }
}

void transmit_telem() {
    std::vector<uint8_t> packet;

    for (size_t i = 0; i < defaultSignalCount_T; ++i) {
        if (signalValues[i].recent_telem) {
            ITV::writeF32(i + allocated_ids, signalValues[i].value, packet);
        }
    }

    queuePacket(packet);
}

void sendNamePacket() {
    Serial.println("Sending Name Packet");
    std::vector<uint8_t> pkt;
    for (int i = 0; i < defaultSignalCount_T; i++) {
        ITV::writeName(i + allocated_ids, signalValues[i].name, pkt);
    }
    queuePacket(pkt);

    if (debug) {
        Serial.println("Name packet bytes:");
        for (auto b : pkt) {
            Serial.printf("%02X ", b);
        }   
        Serial.println();
    }
}

// ---------------------------------------------------------------------------
// SD Card Logging Helpers
// ---------------------------------------------------------------------------

String buildCSV(size_t startIndex, size_t count) {
    char buffer[256]; // Pre-allocate a scratchpad on the stack
    size_t offset = 0;
    
    // Protect the array while reading
    if (xSemaphoreTake(signal_Mutex, pdMS_TO_TICKS(5))) {
        for (size_t i = 0; i < count; ++i) {
            float value = signalValues[startIndex + i].value;
            signalValues[startIndex + i].recent = false;

            // Handle NaN values gracefully
            if (isnan(value)) {
                offset += snprintf(buffer + offset, sizeof(buffer) - offset, "0.000");
            } else {
                // Write the float with 3 decimal places into the buffer
                offset += snprintf(buffer + offset, sizeof(buffer) - offset, "%.3f", value);
            }

            // Add comma if not the last element
            if (i < count - 1 && offset < sizeof(buffer) - 1) {
                buffer[offset++] = ',';
            }
        }
        xSemaphoreGive(signal_Mutex);
    }
    
    buffer[offset] = '\0'; // Null-terminate the string
    return String(buffer); // Convert to String once at the very end
}

String getCANData() {
    return buildCSV(0, defaultSignalCount_Can);
}

template <typename T>
String makeHeaderFromSignals(const T* signals, size_t count) {
    String header = "";
    for (size_t i = 0; i < count; i++) {
        header += signals[i].name;
        if (i < count - 1) header += ",";
    }
    return header;
}

// ---------------------------------------------------------------------------
// DEBUG - Can Spoofing
// ---------------------------------------------------------------------------


void writeU16BE(uint8_t* buf, uint8_t startByte, uint16_t value) {
    buf[startByte]     = (value >> 8) & 0xFF;
    buf[startByte + 1] = value & 0xFF;
}

void spoofCAN() {
    static uint32_t lastUpdate = 0;
    if (millis() - lastUpdate < 10) return;  // ~100 Hz CAN traffic
    lastUpdate = millis();

    uint8_t buf[8] = {0};

    // --------------------
    // RPM (0x5F0, bytes 6–7)
    // --------------------
    {
        unsigned long id = 0x5F0;
        memset(buf, 0, sizeof(buf));

        uint16_t rpm = 3000 + (millis() / 10) % 4000; // 3000–7000 RPM
        writeU16BE(buf, 6, rpm);
        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Vehicle Speed (0x61A, bytes 0–1)
    // --------------------
    {
        unsigned long id = 0x61A;
        memset(buf, 0, sizeof(buf));

        uint16_t vss = (millis() / 50) % 2000; // 0–200.0 (scaled by /10)
        writeU16BE(buf, 0, vss);

        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Coolant Temp CLT1 (0x5F2, bytes 6–7)
    // --------------------
    {
        unsigned long id = 0x5F2;
        memset(buf, 0, sizeof(buf));

        int16_t clt = 850 + (millis() / 200) % 50; // 85.0–90.0 C
        writeU16BE(buf, 6, (uint16_t)clt);

        updateSignalsFromFrame(id, buf, 8);
    }

    // --------------------
    // Oil Pressure (0x5FD, bytes 2–3)
    // --------------------
    {
        unsigned long id = 0x5FD;
        memset(buf, 0, sizeof(buf));

        int16_t oilP = 350 + (millis() / 100) % 50; // 35.0–40.0
        writeU16BE(buf, 2, (uint16_t)oilP);

        updateSignalsFromFrame(id, buf, 8);
    }
}

// ---------------------------------------------------------------------------
// SETUP
// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);
    Serial.println("Init RYLR998...");
    RYLR.begin(115200, SERIAL_8N1, D10, D9);
    delay(1000);
    

    sendAT("AT"); delay(500);
    sendAT("AT+RESET"); delay(500);

    String resp = RYLR.readStringUntil('\n');
    resp.trim();
    if (resp.length()) Serial.println("<< " + resp);

    sendAT("AT+ADDRESS=1", true, true);
    sendAT("AT+NETWORKID=18", true, true);
    sendAT("AT+BAND=915000000", true, true);
    sendAT("AT+PARAMETER=7,9,1,8", true, true);

    ntp.begin(ppsPin, RTC_SDA, RTC_SCK);

    itvHandlers[CMD_SYNC_RESP] = [](const ITV::ITVMap& m) {
        ntp.handleMessage(m);
    };

    itvHandlers[CMD_NAME_SYNC_REQ] = [](const ITV::ITVMap& m) {
        sendNamePacket();
    };

    itvHandlers[CMD_SWITCH_STATE] = [](const ITV::ITVMap& m) {
        state = STATE_TX_ONLY;
        Serial.println("Switched to TX Only state");
    };

    pinMode(CAN_INT, INPUT_PULLUP); // The MCP2515 pulls this LOW on data
    init_can_module();

    // === Logging Setup ===
    String canHeader = makeHeaderFromSignals(defaultSignals_Can, defaultSignalCount_Can);

    logger.setTimeCallback(now_us);
    logger.addSource("CAN", 1, getCANData, canHeader);
    logger.begin("/logs", "data", D3, D2, D4); // Needs to be LAST
  
    init_Wireless_Con();
    init_Sockets();

    initSignalValues();

    lora_Tx_Mutex = xSemaphoreCreateMutex();
    spi1_Mutex = xSemaphoreCreateMutex();
    signal_Mutex = xSemaphoreCreateMutex();
    xTaskCreatePinnedToCore(
        loraTask,           // function
        "LoRaTask",         // name
        4096,               // stack size
        nullptr,            // params
        3,                  // priority (higher = more important)
        &loraTaskHandle,    // handle
        1                   // core 
    );

    xTaskCreatePinnedToCore(
        ntpTask, "ntpTask", 4096, nullptr,  4, &ntpTaskHandle,  1 );
    xTaskCreatePinnedToCore(loggerTask, "loggerTask", 12288, nullptr,  2, &loggerTaskHandle,  1 );
    xTaskCreatePinnedToCore(
        canTask, "canTask", 4096, nullptr,  5, &canTaskHandle,  1 );
    //xTaskCreatePinnedToCore(uartSenseTask, "uartSenseTask", 4096, nullptr,  4, &uartSenseTaskHandle,  1 );
    

    attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);

    sendNamePacket();
}

void loop() {
    unsigned long now = millis();      
    //wireless_OK = update_Wireless_Con();
    
    // Local Logging
    switch (state) {
        case STATE_INIT:
            // Initialize state machine here
            state = STATE_TX_RX; // Transition to TX/RX state
            break;
        case STATE_TX_ONLY:
            if (now - lastSend >= 200) { 
                lastSend = now;
                transmit_telem();
            }
            break;
        case STATE_TX_RX:
            if (now - lastSend >= 550) { // Timing interval needs to be tuned to allow for server side tx
                lastSend = now;
                transmit_telem();
            }
            break;
    }
    vTaskDelay(pdMS_TO_TICKS(TASK_DELAY_Main_Loop));
}


/*
        std::vector<uint8_t> packet;

        ITV::writeName(0x10, "PIE", packet);
        ITV::writeF32(0x10, 3.14159f, packet);
        ITV::writeU32(0x11, uint32_t(1700000012), packet);
        ITV::writeU8(0x12, uint8_t(1), packet);
        ITV::writeBool(0x13, false, packet);
        ITV::writeString(0x20, "DRIVER_OK", packet);

        queuePacket(packet);
        */