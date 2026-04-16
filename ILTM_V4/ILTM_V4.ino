#include <HardwareSerial.h>
#include <Arduino.h>
#include <vector>
#include <functional>
#include <unordered_map>
#include <deque>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <mcp_can.h>
#include "freertos/ringbuf.h"

#include "ITV.h"
#include "NTP_Client.h"
#include "DataLogger.h"
#include "DataBuffer.h"
#include "LoRaManager.h"
#include "ConfigManager.h"
#include "SerialTcpBridge.h"
#include "FileServer.h"
#include "ComsManager.h"

// ====== PINS =======
// SPI
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

#define HSPI_SCLK 14 //D14
#define HSPI_MISO 15 //D32
#define HSPI_MOSI 32 //D15

// Chip Select Pins
#define RFM95_CS 26 //A0
#define RFM95_INT 13 //LED
#define CAN_CS 4 //A5
#define CAN_INT 37 //D37

// I2C
#define I2C_SDA 22
#define I2C_SCL 20

// --- UART 1 - SIM ---
#define HW1_RX 7
#define HW1_TX 8

// --- UART 2 - IMU ---
#define HW2_RX 34
#define HW2_TX 25

// --- UART 3 - RS232 ---
#define RS_RX 36
#define RS_TX 33

// --- UART 4 - COMS ---
#define SW_RX 39
#define SW_TX 27
#define SW_PTT 12

#define DEBUG true

// === DEBUG ===
const bool debug = true;
const bool simulateCan = true;

// === Status Keepers ===
bool wireless_OK = false;
bool can_OK = false;
bool sd_OK = false;
bool logfile_OK = false;
bool loraBusy = false;
bool txBusy = false;

bool wifi_enable = true;
bool wifi_telem_en = false;
bool lora_telem_en = true;
uint16_t telemDelay_Lora = portMAX_DELAY;
uint16_t telemDelay_Wifi = 1000;

// === Globals for Wi-Fi state tracking ===
unsigned long lastWifiAttempt = 0;
unsigned long lastNamepktSend_wifi = 0;
const unsigned long WIFI_RETRY_INTERVAL = 5000; // ms
bool wifiConnecting = false;
bool wifiReportedConnected = false;

SemaphoreHandle_t vspiMutex = NULL;
SemaphoreHandle_t hspiMutex = NULL;

SharedDataBuffer globalBus;
DataLogger logger;
ConfigManager config;
MCP_CAN CAN(CAN_CS);
SerialTcpBridge rs232Bridge(Serial2);
NTP_Client ntp(send);
LoRaManager lora(SPI, RFM95_CS, RFM95_INT);
FileServer fileServer;
SPIClass *hspi = new SPIClass(HSPI);
IPAddress broadcastIP(255, 255, 255, 255);
WiFiUDP udp;
ComsManager radio(SW_RX, SW_TX, SW_PTT); // RX, TX, PTT

std::vector<SignalDef> signalNameList;

//WiFiClient rs232Client;

using ITVHandler = std::function<void(const ITV::ITVMap&)>;
std::unordered_map<uint8_t, ITVHandler> itvHandlers;

const int allocated_ids = 10;
enum ITV_Command : uint8_t {
    CMD_SYNC_REQ  = 0x01,
    CMD_SYNC_RESP = 0x02,
    CMD_NAME_SYNC_REQ = 0x03,
    CMD_LOGGING_EN = 0x04,
    CMD_RS232_EN = 0x05,
    CMD_FILESERV_EN = 0x06,
    CMD_COMSATCMD_SEND = 0x07,
    CMD_PTT_STATE = 0x08,
    CMD_SENDCAN_FRAME = 0x09,
    SET_DEVICE_STATE = 0x0A
};

long long now_us() {
    return millis() * 1000 + 999999999000000009; //TODO: Add back RTC and NTP
}

void sendNamePacket() {
    Serial.println("Sending Name Packet");
    std::vector<uint8_t> pkt;

    // Iterate through the map of CAN IDs
    for (auto const& [canId, signals] : config.settings.canMap) {
        // Iterate through each signal associated with that ID
        for (const auto& s : signals) {
            ITV::writeName(s.id, s.name, pkt);
        }
    }

    lora.send(pkt); 

    if (debug) {
        Serial.println("Name packet bytes:");
        for (auto b : pkt) {
            Serial.printf("%02X ", b);
        }   
        Serial.println();
    }
}

void sendNamePacket_wifi() {
    std::vector<uint8_t> packet;

    // Iterate through the map of CAN IDs
    for (auto const& [canId, signals] : config.settings.canMap) {
        // Iterate through each signal associated with that ID
        for (const auto& s : signals) {
            // Use the signal's internal id (1-14) for the ITV name map
            // We use s.id directly as it is the unique index for that sensor name
            ITV::writeName(s.id, s.name, packet);
        }
    }

    udp.beginPacket(broadcastIP, config.settings.main.udpPort);
    udp.write(packet.data(), packet.size());
    udp.endPacket();
}

std::vector<SignalDef> buildSignalNameList() {
    std::vector<SignalDef> list;
    std::unordered_set<uint8_t> seen;

    for (auto const& [canId, signals] : config.settings.canMap) {
        for (const auto& s : signals) {
            //if (seen.insert(s.id).second) {
                list.push_back(SignalDef{s.id, s.name});
            //}
        }
    }

    return list;
}

void send(const std::vector<uint8_t>& pkt) {
    lora.send(pkt);
}

// -------------------------
// FreeRTOS Tasks
// -------------------------

TaskHandle_t canTaskHandle = nullptr;
void canTask(void* pvParameters) {
    Serial.println("CAN Task Started");

    
    for (;;) {
        if (simulateCan) { 
            spoofCAN(); 
            vTaskDelay(pdMS_TO_TICKS(10)); // Slow down spoofing to 100Hz
            continue;
        }

        // Wait for ISR notification
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // Drain the MCP2515 buffer entirely
        Serial.println("Interupt!!!");
        while (xSemaphoreTake(vspiMutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            if (CAN.checkReceive() == CAN_MSGAVAIL) {
                unsigned long rxId;
                byte len = 0;
                byte rxBuf[8];
                
                if (CAN.readMsgBuf(&rxId, &len, rxBuf) == CAN_OK) {
                    xSemaphoreGive(vspiMutex); // Give it back before processing
                    updateSignalsFromFrame(rxId, rxBuf, len);
                } else {
                    xSemaphoreGive(vspiMutex);
                }
            } else {
                xSemaphoreGive(vspiMutex);
                break; // No more messages available
            }
        }
    }
}
TaskHandle_t telemTaskHandle = nullptr;
void telemTask(void* pvParameters) {
    Serial.println("Lora Telemetry Task Started");
    telemDelay_Lora = 1000/config.settings.main.telemRateHz_Lora;
    
    for (;;) {
        if (!lora_telem_en) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        std::vector<uint8_t> packet;
        std::unordered_map<uint8_t, float> snapshot = globalBus.getLatestSnapshot(100);  
        for (auto const& [id, val] : snapshot) {
            ITV::writeF32(id, val, packet);
        }
        //if (debug) {Serial.println("Send Packet");}
        
        lora.send(packet);
        vTaskDelay(pdMS_TO_TICKS(telemDelay_Lora));
    }
}

TaskHandle_t wifiTaskHandle = nullptr;
void wifiTask(void* pvParameters) {
    Serial.println("Wifi Telemetry Task Started");
    telemDelay_Wifi = 1000/config.settings.main.telemRateHz_Wifi;

    for (;;) {
        if (wifi_enable) {
            wireless_OK = update_Wireless_Con();

            if (wireless_OK && wifi_telem_en) {
                transmit_telem_wifi();
                unsigned long now = millis();
                if (now - lastNamepktSend_wifi > 1000) {
                    lastNamepktSend_wifi = now;
                    sendNamePacket_wifi();
                }
            }  
        } else {
            WiFi.disconnect();
        }
        vTaskDelay(pdMS_TO_TICKS(telemDelay_Wifi));
    }
}

// ---------------------------------------------------------------------------
// Can Signal Helpers
// ---------------------------------------------------------------------------

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

// Apply an incoming frame to the signals buffer
void updateSignalsFromFrame(uint32_t rxId, const uint8_t* rxBuf, uint8_t rxLen) {
    // Look up the ID in the map
    auto it = config.settings.canMap.find(rxId);
    //Serial.println(rxId);
    
    // Ignore if not in map
    if (it == config.settings.canMap.end()) return;

    // Iterate only through the signals associated with this ID
    for (const CanSignal& s : it->second) {
        if ((int)s.startByte + (int)s.length > rxLen) continue;

        float val = decodeCanSignal(s, rxBuf);
        
        // Save value
        LogEntry data = { (uint32_t)millis(), s.id, val };
        globalBus.push(data);
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
    byte canStatus = CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ);
    int retry = 0;
    while (canStatus != CAN_OK && retry < 5) {
        delay(100);
        canStatus = CAN.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ);
        retry++;
    }

    if (canStatus == CAN_OK) {
        Serial.println("MCP2515 Initialized!");

        //CAN.init_Mask(0, 0, 0x000); 
        //CAN.init_Filt(0, 0, 0x000);

        CAN.setMode(MCP_NORMAL);
        delay(10); 

        //pinMode(CAN_INT, INPUT_PULLUP);
        attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);
        can_OK = true;
    } else {
        Serial.print("Error Initializing MCP2515. Error Code: ");
        Serial.println(canStatus);
    }
}

// ---------------------------------------------------------------------------
// Wifi Helpers
// ---------------------------------------------------------------------------

void init_Wireless_Con() {
  Serial.println("Starting Wi-Fi connection...");
  WiFi.begin(config.settings.main.ssid, config.settings.main.password);
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
    WiFi.begin(config.settings.main.ssid, config.settings.main.password);
    lastWifiAttempt = millis();
  }

  return false; // not connected yet
}

void init_Sockets() {
  udp.begin(config.settings.main.udpPort); 
  // Enable broadcast
  //WiFi.enableBroadcast(true);
  Serial.println("UDP socket opened");
}

void transmit_telem_wifi() {
    std::vector<uint8_t> packet;
    std::unordered_map<uint8_t, float> snapshot = globalBus.getLatestSnapshot(100);  
    for (auto const& [id, val] : snapshot) {
        ITV::writeF32(id, val, packet);
    }
    udp.beginPacket(broadcastIP, config.settings.main.udpPort);
    Serial.println(packet.size());
    udp.write(packet.data(), packet.size());
    udp.endPacket();
}

void init_Coms() {
    radio.begin();

    if (radio.connect()) {
        Serial.println("Radio connected");
    } else {
        Serial.println("Radio NOT responding");
    }

    radio.setVolume(4);

    radio.setGroup(
        0,          // 12.5kHz
        435.7250,
        435.7250,
        "0000",
        4,
        "0000"
    );
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

void init_Lora_Commands() {
    Serial.println("Initializing Lora Commands");
    lora.setHandler(CMD_SYNC_RESP, [](const ITV::ITVMap& m) {
        ntp.handleMessage(m);
    });
    lora.setHandler(CMD_NAME_SYNC_REQ, [](const ITV::ITVMap& m) {
        sendNamePacket();
    });
    lora.setHandler(CMD_LOGGING_EN, [](const ITV::ITVMap& m) {
        Serial.print("CMD RECV: LOGGING -- ");
        if (!m.count(0x02)) return;
         int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            logger.startLogging();
        } else {
            Serial.println("Disable");
            logger.stopLogging();
        }
        
    });
    lora.setHandler(CMD_RS232_EN, [](const ITV::ITVMap& m) {
        Serial.print("CMD RECV: RS232 -- ");
        if (!m.count(0x02)) return;
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            wifi_enable = true;
            rs232Bridge.enable();
        } else {
            Serial.println("Disable");
            wifi_enable = false; //TODO: Will cause issues if another service is using wifi
            rs232Bridge.disable();
        }
        
    });
    lora.setHandler(CMD_FILESERV_EN, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: FILESERV");
        if (!m.count(0x02)) return;
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            wifi_enable = true;
            fileServer.begin();
        } else {
            Serial.println("Disable");
            wifi_enable = false;
            fileServer.stop();
        }
    });
    lora.setHandler(CMD_COMSATCMD_SEND, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: COMS AT CMD");
    });
    lora.setHandler(CMD_PTT_STATE, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV");
        if (!m.count(0x02)) {
            Serial.println("No Val");
            return;
        }
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 0) {
            Serial.println("Disable");
        } else if (state == 1) {
            Serial.println("Enable");
        } else if (state == 2) {
            Serial.println("On");
        }
    });
    lora.setHandler(CMD_SENDCAN_FRAME, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: Send CAN Frame");
    });
    lora.setHandler(SET_DEVICE_STATE, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: Set Device State");
        if (!m.count(0x02)) {
            Serial.println("No Val");
            return;
        }
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 0) {
            Serial.println("Driving");
            wifi_enable = true;
            logger.startLogging();
            fileServer.stop();
            rs232Bridge.disable();
            wifi_telem_en = true;
        } else if (state == 1) {
            Serial.println("Pit Lane");
            wifi_enable = true;
            logger.startLogging();
            fileServer.stop();
            rs232Bridge.enable();
        } else if (state == 2) {
            Serial.println("Download Files");
            wifi_enable = true;
            logger.stopLogging();
            rs232Bridge.disable();
            fileServer.begin();
        } else if (state == 3) {
            Serial.println("Drivig, Lora only");
            wifi_enable = false;
            logger.startLogging();
            fileServer.stop();
            rs232Bridge.disable();
            wifi_telem_en = false;
        }
    });
}


void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);
    Serial.println("ILTM Booting...");

    init_Coms();

    vspiMutex = xSemaphoreCreateMutex();
    hspiMutex = xSemaphoreCreateMutex();

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN);

    init_Lora_Commands();

    // Start logger on Core 1, pointing to globalBus
    hspi->begin(HSPI_SCLK, HSPI_MISO, HSPI_MOSI, -1);
    if (!SD.begin(-1, *hspi, 4000000)) {
        Serial.println("SD Begin Failed");
    }
    logger.setTimeCallback(now_us);

    if (config.begin("/config.json")) {
        Serial.println("Configuration Loaded.");
    }

    Serial.println("Initializing Lora Module");
    lora.begin(vspiMutex, 915.0);
    Serial.println("Initializing CAN Module");
    init_can_module();

    // function, name, stack size, params, priority 1=low, handle, core
    xTaskCreatePinnedToCore(canTask, "canTask", 4096, nullptr,  2, &canTaskHandle,  1 );
    xTaskCreatePinnedToCore(telemTask, "telemTask", 4096, nullptr,  3, &telemTaskHandle,  1 );
    xTaskCreatePinnedToCore(wifiTask, "wifiTask", 4096, nullptr,  5, &wifiTaskHandle,  1 );
    
    Serial.println("=== Setup Done ===");

    //enterConfigMode();
    sendNamePacket();

    //wifi_enable = true;
    init_Wireless_Con();
    init_Sockets();

    ntp.begin(I2C_SDA, I2C_SCL);

    rs232Bridge.begin(RS_RX, RS_TX, 115200, config.settings.main.tcpPort, 256,  2000);

    signalNameList = buildSignalNameList();
    logger.begin(&globalBus, "/logs", "data", hspi, &signalNameList);
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(portMAX_DELAY));
}