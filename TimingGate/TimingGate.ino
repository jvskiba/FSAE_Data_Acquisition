#include "config.h"

#include <WiFi.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <LiquidCrystal.h>

// ==== GPS CONFIG ====
const int gpsRXPin = D4;
const int gpsTXPin = D5;
const int ppsPin = D3;

// ==== GATE CONFIG ====
const int gatePin = D2;
bool gateState = HIGH;
const int ledPin = 13;    // Onboard LED

const int buttonPin = D12;
LiquidCrystal lcd(D10, D11, D6, D7, D8, D9); // RS, E, D4, D5, D6, D7

volatile bool buttonPressed = false;
int mode = 0; //0-SingleGate

unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL = 1000; // ms
const unsigned long WIFI_TIMEOUT = 10000; // ms

volatile bool waitingForStart = true;   // True if waiting to start timing
volatile uint32_t startTime = 0;
volatile uint32_t startTimeOld = 0;
volatile uint32_t finishTime = 0;
volatile bool runFinished = false;
volatile uint32_t lastTriggerTime = 0;  // For debounce
const int debounceTime = 2000; // ms

volatile uint32_t ppsMicros = 0;
volatile uint32_t ppsMicrosLast = 0;
volatile bool ppsFlag = false;
bool firstPPS = true;
uint32_t correctionFactor = 1;

bool connected = false;

float lastLap = 0.0;
float recentLap = 0.0;

struct UtcTime {
  uint16_t year;    // e.g., 2025
  uint8_t month;    // 1-12
  uint8_t day;      // 1-31
  uint8_t hour;     // 0-23
  uint8_t minute;   // 0-59
  uint8_t second;   // 0-59
  uint16_t millisecond; // 0-999, optional if you want ms precision
};

UtcTime currentTimeUtc;
UtcTime startTimeUtc;
UtcTime finishTimeUtc;

HardwareSerial GPSSerial(1);  // Use UART1

TinyGPSPlus gps;

portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;


// ==== TIMING ====
WiFiClient client;

void IRAM_ATTR onGateTrigger() {
  uint32_t now = micros();
  if (now - lastTriggerTime < debounceTime * 1000) {  // Ignore if less than debounceTime in us
    return;
  }
  lastTriggerTime = now;

  portENTER_CRITICAL_ISR(&mux);
  if (waitingForStart) {
    startTime = now;
    waitingForStart = false;
  } else {
    finishTime = now;
    startTimeOld = startTime;
    startTime = now;
    waitingForStart = false;
    runFinished = true;
  }
  portEXIT_CRITICAL_ISR(&mux);
}

void IRAM_ATTR onPPS() {
  portENTER_CRITICAL_ISR(&mux);
  ppsMicrosLast = ppsMicros;
  ppsMicros = micros();
  ppsFlag = true;
  portEXIT_CRITICAL_ISR(&mux);
}

void IRAM_ATTR onButton() {
  portENTER_CRITICAL_ISR(&mux);
  buttonPressed = true;
  portEXIT_CRITICAL_ISR(&mux);
}

void saveTime(UtcTime &tStruct, TinyGPSPlus &gps, uint16_t millisecond) {
  tStruct.year = gps.date.year();
  tStruct.month = gps.date.month();
  tStruct.day = gps.date.day();
  tStruct.hour = gps.time.hour();
  tStruct.minute = gps.time.minute();
  tStruct.second = gps.time.second();
  tStruct.millisecond = millisecond;
}

// ---- Updates screen with last & recent lap times ----
void updateLapTimes(float newLap) {
  // Shift down: recent becomes last
  lastLap = recentLap;
  recentLap = newLap;

  lcd.clear();
  lcd.setCursor(0, 1);
  lcd.print("Last:   ");
  if (lastLap > 0) {
    lcd.print(lastLap, 3);  // 2 decimals
    lcd.print(" s");
  }

  lcd.setCursor(0, 0);
  lcd.print("Recent: ");
  lcd.print(recentLap, 3);
  lcd.print(" s");
}

void handleCommand(String cmd) {
    if (cmd == "ARM") {
        waitingForStart = true;
        Serial.println("Gate armed");
    } else if (cmd == "DISARM") {
        waitingForStart = false;
        Serial.println("Gate disarmed");
    } else if (cmd.startsWith("SET_MODE")) {
        // e.g., "SET_MODE 1"
        int mode = cmd.substring(9).toInt();
        Serial.print("Mode set to ");
        Serial.println(mode);
    } else {
        Serial.print("Unknown command: ");
        Serial.println(cmd);
    }
}

void transmit_heartbeat() {
  // send UDP packet
  udp.beginPacket(config.host, config.udpPort);
  udp.print("0, ");
  udp.print(millis());
  udp.println();
  udp.endPacket();
}

void setup() {
  Serial.begin(115200);
  pinMode(gatePin, INPUT_PULLUP); 
  pinMode(ledPin, OUTPUT);
  pinMode(ppsPin, INPUT);
  pinMode(buttonPin, INPUT_PULLUP); 
  
  attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS, RISING);
  attachInterrupt(digitalPinToInterrupt(gatePin), onGateTrigger, RISING);
  attachInterrupt(digitalPinToInterrupt(buttonPin), onButton, FALLING);

  GPSSerial.begin(9600, SERIAL_8N1, gpsRXPin, gpsTXPin);

  lcd.begin(16, 2);
  lcd.clear();
  lcd.print("JvS Lap Timer");
  lcd.setCursor(0, 1);
  lcd.print("Wifi Connecting");

  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(ssid, password);
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - startTime > WIFI_TIMEOUT) {
        Serial.println("\nWi-Fi connect timed out!");
        break; // exit the loop if timeout reached
    }
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWi-Fi connected!");
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
      lcd.clear();
      lcd.print("===Connected===");
      lcd.setCursor(0, 1);
      lcd.print(WiFi.localIP());
  } else {
      Serial.println("Proceeding without Wi-Fi...");
      lcd.clear();
      lcd.print("Unable 2 Connect");
  }  

  /*Serial.println("Connecting to server...");
  if (!client.connect(host, port)) {
    Serial.println("Connection to server failed.");
  } else {
    Serial.println("Connected to server!");
  }
  */
}

void loop() {
  while (GPSSerial.available() > 0) {
    char c = GPSSerial.read();
    gps.encode(c);
  }

  if (ppsFlag && gps.time.isUpdated()) {
    portENTER_CRITICAL(&mux);
    uint32_t interval = ppsMicros - ppsMicrosLast;
    ppsFlag = false;
    portEXIT_CRITICAL(&mux);
    Serial.printf("%lu\n", interval);
  }

  if (buttonPressed) {
    buttonPressed = false;
    Serial.println("Pressed!");
  }

  if (client.connected()) {
    // Check if there are any commands from Python
    if (client.available()) {
      String cmd = client.readStringUntil('\n');  // read until newline
      cmd.trim();
      handleCommand(cmd);
    }
  }

  // Detect trigger (falling edge)
  if (runFinished) {
    portENTER_CRITICAL(&mux);
    uint32_t elapsedMicros = finishTime - startTimeOld;
    runFinished = false;
    portEXIT_CRITICAL(&mux);

    float elapsedSeconds = elapsedMicros / 1000000.0;
    Serial.print("Elapsed time (s): ");
    Serial.println(elapsedSeconds, 6);
    

    digitalWrite(ledPin, HIGH);
    delay(100);
    digitalWrite(ledPin, LOW);

    String msg;
    char buf[64]; // enough for one message

    snprintf(buf, sizeof(buf), "TRIGGER, %.3f", elapsedSeconds);
    msg = buf;

    if (gps.time.isUpdated()) {
      if (micros() - ppsMicros < 2000000) {
        saveTime(currentTimeUtc, gps, (ppsMicros - finishTime)/1000);
        snprintf(buf, sizeof(buf),
        ", Time (UTC), %02d:%02d:%02d.%03d",
        currentTimeUtc.hour,
        currentTimeUtc.minute,
        currentTimeUtc.second,
        currentTimeUtc.millisecond % 1000 // ensure range 0-999
        );

      } else {
        saveTime(currentTimeUtc, gps, 1000);
        snprintf(buf, sizeof(buf),
        ", Time (UTC), %02d:%02d:%02d",
        currentTimeUtc.hour,
        currentTimeUtc.minute,
        currentTimeUtc.second
        );
      }
      msg += buf;
    }
    // Send to server
    if (client.connected()) {
      client.print(msg);
    } else {
      Serial.println("Lost connection to server!\n");
      /*if (client.connect(host, port)) {
        Serial.println("Connected");
        client.print(msg);
      }*/
    }

    updateLapTimes(elapsedSeconds);
  }

  // Socket Reconnection
  if (!client.connected() && WiFi.status() == WL_CONNECTED) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > RECONNECT_INTERVAL) {
      lastReconnectAttempt = now;
      Serial.println("Attempting reconnect...");
      if (client.connect(host, port)) {
        Serial.println("Reconnected");
      } else {
        Serial.println("Reconnect failed");
      }
    }
  }
}
