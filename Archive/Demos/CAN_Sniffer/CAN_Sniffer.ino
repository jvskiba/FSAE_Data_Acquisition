#include <Arduino.h>
#include "driver/twai.h"

// Define GPIO pins for CAN transceiver
#define CAN_RX_PIN 37
#define CAN_TX_PIN 4

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 2000);

  Serial.println("\n--- ESP32 TWAI CAN Bus Sniffer ---");

  // 1. General Configuration (normal mode using designated TX/RX pins)
  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
    (gpio_num_t)CAN_TX_PIN, 
    (gpio_num_t)CAN_RX_PIN, 
    TWAI_MODE_NORMAL
  );

  // 2. Timing Configuration (500 Kbps - update to TWAI_TIMING_CONFIG_1MBITS() if needed)
  //twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_1MBITS();

  // 3. Acceptance Filter Configuration (accept all CAN IDs)
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  // Install TWAI driver
  esp_err_t err = twai_driver_install(&g_config, &t_config, &f_config);
  if (err != ESP_OK) {
    Serial.printf("Driver install failed with error: 0x%X\n", err);
    while (1);
  }

  // Start TWAI driver
  if (twai_start() != ESP_OK) {
    Serial.println("Failed to start TWAI driver");
    while (1);
  }

  Serial.println("TWAI Driver running. Listening for frames...\n");
}

void loop() {
  twai_message_t rx_msg;

  // Non-blocking / short timeout check for incoming CAN frames (10ms timeout)
  if (twai_receive(&rx_msg, pdMS_TO_TICKS(10)) == ESP_OK) {
    
    // Print Timestamp (ms)
    Serial.printf("[%9lu ms] ", millis());

    // Print CAN Identifier
    if (rx_msg.extd) {
      Serial.printf("ID: 0x%08X (EXT) ", rx_msg.identifier);
    } else {
      Serial.printf("ID: 0x%03X (STD) ", rx_msg.identifier);
    }

    // Print RTR Flag or DLC + Hex Bytes
    if (rx_msg.rtr) {
      Serial.print("| Remote Frame Request (RTR)");
    } else {
      Serial.printf("| DLC: %d | Data: ", rx_msg.data_length_code);
      for (int i = 0; i < rx_msg.data_length_code; i++) {
        Serial.printf("%02X ", rx_msg.data[i]);
      }
    }

    Serial.println();
  }
}