// config.h

#ifndef CONFIG_H
#define CONFIG_H

struct CanSignal {
  uint16_t canId;
  uint8_t startByte;
  uint8_t length;
  bool littleEndian;
  float scale;
  float offset;
  String name;
};

struct LoggerConfig {
  uint16_t sampleRateHz;
  bool useNaNForMissing;   // true = write NaN, false = last known value
  char* ssid;
  char* password; 
  char* host;
  uint16_t udpPort; 
  uint16_t tcpPort;
};



// ===== Default CAN signal definitions =====
//id,startByte,length,littleEndian,scale,offset,name
CanSignal defaultSignals[] = {
  { 0x5F0, 6, 2, true,  1.0, 0.0, "RPM" },
  { 0x5F2, 6, 2, true,  0.10, 0.0, "CLT" },
  { 0x5F3, 0, 2, true,  1.0, 0.0, "TPS" },
  { 0x61A, 0, 2, true,  0.1, 0.0, "VSS" }
};
const size_t defaultSignalCount = sizeof(defaultSignals) / sizeof(defaultSignals[0]);

// ===== Default logger config =====
LoggerConfig defaultConfig = {
  100,   // sampleRateHz (100 Hz)
  true,   // useNaNForMissing
  "UGA_Motorsports", //Wifi SSID
  "formulaSAE", // Wifi Passworf
  "192.168.0.3", // Server IP
  5002, //udpPort 
  5001 // TCP port
};


#endif