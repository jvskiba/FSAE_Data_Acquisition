#pragma once
#include <WiFi.h>

class SerialTcpBridge {
public:
    SerialTcpBridge(HardwareSerial& serialPort) : serial(serialPort) {}

    ~SerialTcpBridge() {
        if (taskHandle) vTaskDelete(taskHandle);
        if (uartBuffer) delete[] uartBuffer;
        if (tcpBuffer)  delete[] tcpBuffer;
    }

    void begin(int rxPin, int txPin, uint32_t baud, uint16_t port, 
               size_t bufferSize = 512, uint32_t flushIntervalUs = 2000) 
    {
        RX = rxPin; TX = txPin; BAUD = baud;
        server = new WiFiServer(port);
        server->begin();
        BUFFER_SIZE = bufferSize;
        FLUSH_INTERVAL_US = flushIntervalUs;

        if (!uartBuffer) uartBuffer = new uint8_t[BUFFER_SIZE];
        if (!tcpBuffer)  tcpBuffer  = new uint8_t[BUFFER_SIZE];

        serial.begin(BAUD, SERIAL_8N1, RX, TX);
        lastFlushUs = micros();

        // Start the FreeRTOS task on Core 0 (Wireless/Protocol core)
        xTaskCreatePinnedToCore(
            this->taskWrapper, "TcpBridgeTask", 4096, this, 1, &taskHandle, 0
        );
    }

    // Static wrapper needed for FreeRTOS
    static void taskWrapper(void* pvParameters) {
        SerialTcpBridge* instance = (SerialTcpBridge*)pvParameters;
        for (;;) {
            instance->process();
            vTaskDelay(pdMS_TO_TICKS(1)); // Yield to allow WiFi stack to breathe
        }
    }

    void process() {
        if (!en) { 
            vTaskDelay(pdMS_TO_TICKS(10)); // sleep 10ms, almost zero CPU usage
            return;
        }

        if (!client.connected()) {
            WiFiClient newClient = server->available();
            if (!newClient) {
                return;
            }
            Serial.println("New Client");
            client = newClient; // copy over only if a client exists
            uartPos = tcpPos = 0; // reset buffers
        }
        
        if (!client || !client.connected() || !uartBuffer || !tcpBuffer) return;

        while (serial.available() && uartPos < BUFFER_SIZE) {
            uartBuffer[uartPos++] = serial.read();
            //Serial.println("RS232 Data Received");
        }

        while (client.available() && tcpPos < BUFFER_SIZE) {
            tcpBuffer[tcpPos++] = client.read();
            //Serial.println("TCP Data Received");
        }

        unsigned long nowUs = micros();
        if (uartPos >= BUFFER_SIZE || tcpPos >= BUFFER_SIZE || (nowUs - lastFlushUs) > FLUSH_INTERVAL_US) {
            if (uartPos > 0) { client.write(uartBuffer, uartPos); uartPos = 0; }
            if (tcpPos > 0) { serial.write(tcpBuffer, tcpPos); tcpPos = 0; }
            lastFlushUs = nowUs;
        }
    }

    void enable() {
        en = true;
    }
    void disable() {
        en = false;
        if (client && client.connected()) client.stop();
    }

private:
    HardwareSerial& serial;
    WiFiServer* server = nullptr; //TODO: TCP Port Hardcoded
    WiFiClient client;
    TaskHandle_t taskHandle = nullptr;

    int RX = -1, TX = -1;
    uint32_t BAUD = 115200;
    size_t BUFFER_SIZE = 0;
    uint32_t FLUSH_INTERVAL_US = 0;
    uint8_t* uartBuffer = nullptr;
    uint8_t* tcpBuffer = nullptr;
    size_t uartPos = 0, tcpPos = 0;
    unsigned long lastFlushUs = 0;
    bool en = false;
};