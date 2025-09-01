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
  bool is_signed;
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
//id,startByte,length,littleEndian,scale,offset,name, signed
CanSignal defaultSignals[] = {
  { 0x5F0, 6, 2, false,  1.0, 0.0, "RPM", false },
  { 0x61A, 0, 2, false,  0.1, 0.0, "VSS", false },
  { 0x611, 6, 1, false,  1.0, 0.0, "Gear", false },
  { 0x5FE, 4, 2, false,  1.0, 100, "STR", true },
  { 0x5F3, 0, 2, false,  0.1, 0.0, "TPS", false },
  { 0x5F2, 6, 2, false,  0.1, 0.0, "CLT1", true },
  { 0x5FE, 0, 2, false,  0.1, 0.0, "CLT2", true },
  { 0x5FD, 4, 2, false,  0.1, 0.0, "OilTemp", true },
  { 0x5F3, 0, 2, false,  0.1, 0.0, "MAT", true },
  { 0x5FD, 6, 2, false,  0.1, 0.0, "FuelPres", true },
  { 0x5FD, 2, 2, false,  0.1, 0.0, "OilPres", true },
  { 0x5FD, 0, 2, false,  0.1, 0.0, "AFR", false }
};
const size_t defaultSignalCount = sizeof(defaultSignals) / sizeof(defaultSignals[0]);

// ===== Default logger config =====
LoggerConfig defaultConfig = {
  10,   // sampleRateHz (100 Hz)
  true,   // useNaNForMissing
  "UGA_Motorsports", //Wifi SSID
  "formulaSAE", // Wifi Passworf
  "192.168.0.3", // Server IP
  5002, //udpPort 
  5001 // TCP port
};


#endif