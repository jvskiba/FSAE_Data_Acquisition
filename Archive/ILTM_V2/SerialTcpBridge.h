#pragma once
#include <WiFi.h>

class SerialTcpBridge {
public:
    SerialTcpBridge(HardwareSerial& serialPort,
                    int rxPin,
                    int txPin,
                    uint32_t baud,
                    WiFiClient* clientPtr,
                    size_t bufferSize = 512,
                    uint32_t flushIntervalUs = 2000)
        : serial(serialPort),
          RX(rxPin),
          TX(txPin),
          BAUD(baud),
          client(clientPtr),
          BUFFER_SIZE(bufferSize),
          FLUSH_INTERVAL_US(flushIntervalUs)
    {
        uartBuffer = new uint8_t[BUFFER_SIZE];
        tcpBuffer  = new uint8_t[BUFFER_SIZE];
    }

    void begin() {
        serial.begin(BAUD, SERIAL_8N1, RX, TX);

        uartPos = 0;
        tcpPos  = 0;
        lastFlushUs = micros();
    }

    void process() {
        if (!client || !client->connected()) {
            return;  // No connection, do nothing
        }

        // === Serial → TCP ===
        while (serial.available() && uartPos < BUFFER_SIZE) {
            uartBuffer[uartPos++] = serial.read();
        }

        // === TCP → Serial ===
        while (client->available() && tcpPos < BUFFER_SIZE) {
            tcpBuffer[tcpPos++] = client->read();
        }

        unsigned long nowUs = micros();

        // === Flush ===
        if (uartPos >= BUFFER_SIZE || tcpPos >= BUFFER_SIZE ||
            (nowUs - lastFlushUs) > FLUSH_INTERVAL_US)
        {
            if (uartPos > 0) {
                client->write(uartBuffer, uartPos);
                uartPos = 0;
            }

            if (tcpPos > 0) {
                serial.write(tcpBuffer, tcpPos);
                tcpPos = 0;
            }

            lastFlushUs = nowUs;
        }
    }

private:
    HardwareSerial& serial;
    WiFiClient* client;

    const int RX, TX;
    const uint32_t BAUD;
    const size_t BUFFER_SIZE;
    const uint32_t FLUSH_INTERVAL_US;

    uint8_t* uartBuffer;
    uint8_t* tcpBuffer;
    size_t uartPos = 0;
    size_t tcpPos = 0;

    unsigned long lastFlushUs = 0;
};
