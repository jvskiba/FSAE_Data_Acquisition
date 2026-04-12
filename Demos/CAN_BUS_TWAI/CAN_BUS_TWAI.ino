#include "driver/twai.h"

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("TWAI Send/Receive Test");

  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
      (gpio_num_t)4,   // TX
      (gpio_num_t)37,   // RX (valid pin)
      TWAI_MODE_NORMAL // IMPORTANT: real CAN communication
  );

  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&g_config, &t_config, &f_config) != ESP_OK) {
    Serial.println("Driver install failed");
    return;
  }

  if (twai_start() != ESP_OK) {
    Serial.println("Start failed");
    return;
  }

  Serial.println("TWAI started");
}

void loop() {
  static unsigned long lastSend = 0;

  // 🔼 SEND every 1 second
  if (millis() - lastSend > 1000) {
    lastSend = millis();

    twai_message_t tx_msg = {};
    tx_msg.identifier = 0x345;
    tx_msg.extd = 0;
    tx_msg.rtr = 0;
    tx_msg.data_length_code = 8;

    for (int i = 0; i < 8; i++) {
      tx_msg.data[i] = i;
    }

    esp_err_t tx = twai_transmit(&tx_msg, pdMS_TO_TICKS(1000));

    if (tx == ESP_OK) {
      Serial.println("TX: Sent ID 0x345");
    } else {
      Serial.printf("TX FAILED: %d. Resetting...\n", tx);
      twai_stop();
      twai_initiate_recovery();
      delay(100); // Give it a moment
      twai_start();
    }
  }

  // 🔽 RECEIVE (non-blocking)
  twai_message_t rx_msg;

  if (twai_receive(&rx_msg, pdMS_TO_TICKS(10)) == ESP_OK) {
    Serial.print("RX ID: 0x");
    Serial.println(rx_msg.identifier, HEX);

    Serial.print("Data: ");
    for (int i = 0; i < rx_msg.data_length_code; i++) {
      Serial.print(rx_msg.data[i]);
      Serial.print(" ");
    }
    Serial.println("\n---");
  }
}