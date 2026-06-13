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
#include "LoRaManager.h"
#include "NTP_Client.h"

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

// === DEBUG ===
const bool debug = false;
const bool simulateCan = true;

// === Status Keepers ===
bool wireless_OK = false;
bool can_OK = false;
bool sd_OK = false;
bool logfile_OK = false;
bool loraBusy = false;
bool txBusy = false;

SemaphoreHandle_t vspiMutex = NULL;
SemaphoreHandle_t hspiMutex = NULL;

NTP_Client ntp(send);
LoRaManager lora(SPI, RFM95_CS, RFM95_INT);
SPIClass *hspi = new SPIClass(HSPI);

WiFiClient rs232Client;

using ITVHandler = std::function<void(const ITV::ITVMap&)>;
std::unordered_map<uint8_t, ITVHandler> itvHandlers;

const int allocated_ids = 10;
enum ITV_Command : uint8_t {
    CMD_SYNC_REQ  = 0x01,
    CMD_SYNC_RESP = 0x02,
    CMD_NAME_SYNC_REQ = 0x03,
    CMD_SWITCH_STATE = 0x04
};

long long now_us() {
    return millis() * 1000 + 999999999000000009; //TODO: Add back RTC and NTP
}

void sendNamePacket() {
    Serial.println("Sending Name Packet");
}

void send(const std::vector<uint8_t>& pkt) {
    lora.send(pkt);
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("Boot reason: " + String(esp_reset_reason()));
    delay(1000);
    Serial.println("ILTM Booting...");

    vspiMutex = xSemaphoreCreateMutex();

    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN);

    //lora.setHandler(CMD_SYNC_RESP, [](const ITV::ITVMap& m) {
    //    ntp.handleMessage(m);
    //});

    lora.setHandler(CMD_NAME_SYNC_REQ, [](const ITV::ITVMap& m) {
        sendNamePacket();
    });

    lora.begin(vspiMutex, 915.0);

    Serial.println("=== Setup Done ===");
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(portMAX_DELAY));
}