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

// ====== PINS =======
// SPI
#define SCK_PIN  5
#define MOSI_PIN 19
#define MISO_PIN 21

#define HSPI_SCLK 14
#define HSPI_MISO 32
#define HSPI_MOSI 15

// Chip Select Pins
#define RFM95_CS 26
#define SD_CS    32
#define RFM95_INT 13
#define CAN_CS 4
#define CAN_INT 37

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

// FreeRTOS Delays
#define TASK_DELAY_Main_Loop 10
#define TASK_DELAY_LoRa 20
#define TASK_DELAY_NTP 30
#define TASK_DELAY_LOGGER 10
#define TASK_DELAY_CAN 10

#define DEBUG true

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

bool wifi_enable = false;

// === Globals for Wi-Fi state tracking ===
unsigned long lastWifiAttempt = 0;
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
SPIClass *hspi = new SPIClass(HSPI);

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
    CMD_SENDCAN_FRAME = 0x09
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
            // Use the signal's internal id (1-14) for the ITV name map
            // We use s.id directly as it is the unique index for that sensor name
            ITV::writeName(s.id, s.name, pkt);
        }
    }

    // Use your lora manager to send the packet
    lora.send(pkt); 

    if (debug) {
        Serial.println("Name packet bytes:");
        for (auto b : pkt) {
            Serial.printf("%02X ", b);
        }   
        Serial.println();
    }
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
        } else {
            // Wait for ISR notification
            // pdTRUE means clear the notification count to 0 on exit
            ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        }

        // Drain the MCP2515 buffer entirely
        //Serial.println("Interupt!!!");
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
    Serial.println("Telemetry Task Started");
    
    for (;;) {

        /*LogEntry recent[1];
        globalBus.peekRecent(recent, 1);
        std::vector<uint8_t> packet;
        ITV::writeF32(recent[0].id, recent[0].value, packet);
        lora.send(packet); // New class method
        */

        std::vector<uint8_t> packet;
        std::unordered_map<uint8_t, float> snapshot = globalBus.getLatestSnapshot(100);  
        for (auto const& [id, val] : snapshot) {
            ITV::writeF32(id, val, packet);
        }
        //if (debug) {Serial.println("Send Packet");}
        lora.send(packet);
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

TaskHandle_t wifiTaskHandle = nullptr;
void wifiTask(void* pvParameters) {
    for (;;) {
        if (wifi_enable) {
            update_Wireless_Con();
        } else {
            WiFi.disconnect();
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
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
        
        // Force a mode set and verify it actually changed
        CAN.setMode(MCP_NORMAL);
        delay(10); 

        CAN.init_Mask(0, 0, 0x000); 
        CAN.init_Filt(0, 0, 0x000);

        //pinMode(CAN_INT, INPUT_PULLUP);
        attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);
        can_OK = true;
    } else {
        Serial.println("Error Initializing MCP2515...");
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
  //udp.begin(config.settings.main.udpPort); 
  Serial.println("UDP socket opened");
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


void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);
    Serial.println("ILTM Booting...");

    vspiMutex = xSemaphoreCreateMutex();
    hspiMutex = xSemaphoreCreateMutex();

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN);

    lora.setHandler(CMD_SYNC_RESP, [](const ITV::ITVMap& m) {
        ntp.handleMessage(m);
    });
    lora.setHandler(CMD_NAME_SYNC_REQ, [](const ITV::ITVMap& m) {
        sendNamePacket();
    });
    lora.setHandler(CMD_LOGGING_EN, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: LOGGING");
        if (!m.count(0x02)) return;
         int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            rs232Bridge.enable();
        } else {
            Serial.println("Disable");
            rs232Bridge.disable();
        }
        
    });
    lora.setHandler(CMD_RS232_EN, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: RS232");
        if (!m.count(0x02)) return;
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            wifi_enable = true;
            rs232Bridge.enable();
        } else {
            Serial.println("Disable");
            wifi_enable = false;
            rs232Bridge.disable();
        }
        
    });
    lora.setHandler(CMD_FILESERV_EN, [](const ITV::ITVMap& m) {
        Serial.println("CMD RECV: FILESERV");
        if (!m.count(0x02)) return;
        int state = std::get<uint8_t>(m.at(0x02));
        if (state == 1) {
            Serial.println("Enable");
            //TODO: ADD
        } else {
            Serial.println("Disable");
            
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

    // Start logger on Core 1, pointing to globalBus
    hspi->begin(HSPI_SCLK, HSPI_MISO, HSPI_MOSI, -1);
    logger.setTimeCallback(now_us);
    logger.begin(&globalBus, "/logs", "data", hspi);

    // SD_MMC.begin must happen first - Handled with logger.begin
    if (config.begin("/config.json")) {
        Serial.println("Configuration Loaded.");
    }

    lora.begin(vspiMutex, 915.0);
    init_can_module();
    // function, name, stack size, params, priority 1=low, handle, core
    xTaskCreatePinnedToCore(canTask, "canTask", 4096, nullptr,  2, &canTaskHandle,  1 );
    xTaskCreatePinnedToCore(telemTask, "telemTask", 4096, nullptr,  3, &telemTaskHandle,  1 );
    xTaskCreatePinnedToCore(wifiTask, "wifiTask", 4096, nullptr,  5, &wifiTaskHandle,  1 );
    
    Serial.println("=== Setup Done ===");

    //enterConfigMode();
    sendNamePacket();

    init_Wireless_Con();
    init_Sockets();

    //ntp.begin(I2C_SDA, I2C_SCL);

    rs232Bridge.begin(RS_RX, RS_TX, 115200, config.settings.main.tcpPort, 256,  2000);
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(portMAX_DELAY));
}