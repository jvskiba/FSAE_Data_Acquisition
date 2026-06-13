#include <WiFi.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>

// ==== CONFIG ====
const char* ssid = "FBI_Safehouse";
const char* password = "icanttellyou";
const char* host = "192.168.1.207";  // <-- Replace with your PC's IP
const uint16_t port = 5000;

// ==== GPS CONFIG ====
const int gpsRXPin = D4;
const int gpsTXPin = D5;
const int ppsPin = D3;

// ==== GATE CONFIG ====
const int gatePin = D2;
bool gateState = HIGH;
const int ledPin = 13;    // Onboard LED

volatile bool waitingForStart = true;   // True if waiting to start timing
volatile uint32_t startTime = 0;
volatile uint32_t startTimeOld = 0;
volatile uint32_t finishTime = 0;
volatile bool runFinished = false;
volatile uint32_t lastTriggerTime = 0;  // For debounce
const int debounceTime = 500;

volatile uint32_t ppsMicros = 0;
volatile uint32_t ppsMicrosLast = 0;
volatile bool ppsFlag = false;
bool firstPPS = true;
uint32_t correctionFactor = 1;

bool connected = false;

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


void saveTime(UtcTime &tStruct, TinyGPSPlus &gps, uint16_t millisecond) {
  tStruct.year = gps.date.year();
  tStruct.month = gps.date.month();
  tStruct.day = gps.date.day();
  tStruct.hour = gps.time.hour();
  tStruct.minute = gps.time.minute();
  tStruct.second = gps.time.second();
  tStruct.millisecond = millisecond;
}

void setup() {
  Serial.begin(115200);
  pinMode(gatePin, INPUT_PULLUP); 
  pinMode(ledPin, OUTPUT);
  pinMode(ppsPin, INPUT);
  
  attachInterrupt(digitalPinToInterrupt(ppsPin), onPPS, RISING);
  attachInterrupt(digitalPinToInterrupt(gatePin), onGateTrigger, RISING);

  GPSSerial.begin(9600, SERIAL_8N1, gpsRXPin, gpsTXPin);

  Serial.println("Single-gate timing ready with 100ms debounce.");

  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  Serial.println("Connecting to server...");
  if (!client.connect(host, port)) {
    Serial.println("Connection to server failed.");
  } else {
    Serial.println("Connected to server!");
  }
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
    //Serial.printf("ISR: ppsMicrosLast=%lu, ppsMicros=%lu\n", ppsMicrosLast, ppsMicros);
    Serial.printf("%lu\n", interval);
  }

  if (!client.connected()) {
    if (client.connect(host, port)) {
        Serial.println("Connected");
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
      if (client.connect(host, port)) {
        Serial.println("Connected");
        client.print(msg);
      }
    }
  }
}
