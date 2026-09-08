#include <Arduino.h>
#include "driver/twai.h"

// Define GPIO pins for CAN transceiver
#define CAN_RX_PIN 37
#define CAN_TX_PIN 4

// Heartbeat payload observed from real ECU log
const uint32_t ECU_HEARTBEAT_ID = 0x02400000;
const uint8_t ECU_HEARTBEAT_DATA[8] = { 0x00, 0xD8, 0x20, 0xD0, 0x20, 0xD0, 0x20, 0xD0 };

// Secondary initialization ID broadcast by FT ECUs
const uint32_t ECU_INIT_ID = 0x02400004;
const uint8_t ECU_INIT_DATA[8] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };

TaskHandle_t heartbeatTaskHandle = NULL;

void ecuHeartbeatTask(void *pvParameters) {
  twai_message_t hb_msg = {};
  hb_msg.identifier = ECU_HEARTBEAT_ID;
  hb_msg.extd = 1;              
  hb_msg.rtr = 0;
  hb_msg.data_length_code = 8;
  memcpy(hb_msg.data, ECU_HEARTBEAT_DATA, 8);

  twai_message_t init_msg = {};
  init_msg.identifier = ECU_INIT_ID;
  init_msg.extd = 1;
  init_msg.rtr = 0;
  init_msg.data_length_code = 8;
  memcpy(init_msg.data, ECU_INIT_DATA, 8);

  TickType_t xLastWakeTime = xTaskGetTickCount();
  const TickType_t xFrequency = pdMS_TO_TICKS(16); // 16ms period (~60 Hz)
  uint8_t init_counter = 0;

  for (;;) {
    // Periodically send initialization frame alongside primary heartbeat
    if (init_counter++ % 10 == 0) {
      twai_transmit(&init_msg, pdMS_TO_TICKS(2));
    }

    twai_transmit(&hb_msg, pdMS_TO_TICKS(2));
    vTaskDelayUntil(&xLastWakeTime, xFrequency);
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 2000);

  Serial.println("\n--- ESP32 FuelTech ECU Standalone Emulator ---");

  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
    (gpio_num_t)CAN_TX_PIN, 
    (gpio_num_t)CAN_RX_PIN, 
    TWAI_MODE_NORMAL
  );
  
  g_config.alerts_enabled = TWAI_ALERT_BUS_OFF;
  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_1MBITS();
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&g_config, &t_config, &f_config) != ESP_OK) {
    Serial.println("Driver install failed!");
    while (1);
  }

  if (twai_start() != ESP_OK) {
    Serial.println("TWAI Start failed!");
    while (1);
  }

  xTaskCreatePinnedToCore(
    ecuHeartbeatTask,
    "ECU_Heartbeat",
    2048,
    NULL,
    2,
    &heartbeatTaskHandle,
    0
  );

  Serial.println("Emulating ECU keep-alive signal...");
}

void loop() {
  // Silent auto-recovery from Bus-Off condition
  uint32_t alerts;
  if (twai_read_alerts(&alerts, 0) == ESP_OK) {
    if (alerts & TWAI_ALERT_BUS_OFF) {
      twai_initiate_recovery();
      vTaskDelay(pdMS_TO_TICKS(10));
      twai_start();
    }
  }

  twai_message_t rx_msg;
  if (twai_receive(&rx_msg, pdMS_TO_TICKS(10)) == ESP_OK) {
    // Ignore echoing back our own heartbeats
    if (rx_msg.identifier == ECU_HEARTBEAT_ID || rx_msg.identifier == ECU_INIT_ID) {
      return;
    }

    // Print received EGT-4 frames
    Serial.printf("[%9lu ms] ID: 0x%08X | DLC: %d | Data: ", 
                  millis(), rx_msg.identifier, rx_msg.data_length_code);
    for (int i = 0; i < rx_msg.data_length_code; i++) {
      Serial.printf("%02X ", rx_msg.data[i]);
    }
    Serial.println();
  }
}