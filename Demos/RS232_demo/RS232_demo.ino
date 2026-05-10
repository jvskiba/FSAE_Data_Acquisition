// ESP32 MAX3232 Loopback Test

HardwareSerial RS232(2);

// UART pins
#define RXD2 36
#define TXD2 33

uint32_t counter = 0;
uint32_t passed = 0;
uint32_t failed = 0;

void setup() {
    Serial.begin(115200);

    // UART2 setup
    RS232.begin(9600, SERIAL_8N1, RXD2, TXD2);

    delay(1000);

    Serial.println();
    Serial.println("MAX3232 Loopback Test Starting...");
}

void loop() {

    // Create test packet
    String tx = "TEST_" + String(counter);

    // Flush old data
    while (RS232.available()) {
        RS232.read();
    }

    // Send packet
    RS232.print(tx);

    delay(50);

    // Read response
    String rx = "";

    while (RS232.available()) {
        char c = RS232.read();
        rx += c;
    }

    // Compare
    if (rx == tx) {
        passed++;
        Serial.printf("[PASS] Sent: %s  Received: %s\n",
                      tx.c_str(),
                      rx.c_str());
    } else {
        failed++;
        Serial.printf("[FAIL] Sent: %s  Received: %s\n",
                      tx.c_str(),
                      rx.c_str());
    }

    Serial.printf("Pass: %lu   Fail: %lu\n\n", passed, failed);

    counter++;

    delay(500);
}