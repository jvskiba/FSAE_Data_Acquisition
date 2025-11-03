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

struct AnalogueSignal {
  String name;
  uint8_t pin;
  float val_0v;   // value corresponding to 0V reading
  float val_3v;   // value corresponding to 3.3V reading
};

struct LoggerConfig {
  uint16_t sampleRateHz;
  uint16_t telemRateHz;
  bool useNaNForMissing;
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
  { 0x5FE, 4, 2, false,  0.1, 0.0, "STR", true },
  { 0x5F3, 0, 2, false,  0.1, 0.0, "TPS", false },
  { 0x5F2, 6, 2, false,  0.1, 0.0, "CLT1", true },
  { 0x5FE, 0, 2, false,  0.1, 0.0, "CLT2", true },
  { 0x5FD, 4, 2, false,  0.1, 0.0, "OilTemp", true },
  { 0x5F2, 2, 2, false,  0.1, 0.0, "MAP", true },
  { 0x5F2, 4, 2, false,  0.1, 0.0, "MAT", true },
  { 0x5FD, 6, 2, false,  0.1, 0.0, "FuelPres", true },
  { 0x5FD, 2, 2, false,  0.1, 0.0, "OilPres", true },
  { 0x5FD, 0, 2, false,  0.1, 0.0, "AFR", false },
  { 0x5F3, 2, 2, false,  0.1, 0.0, "BatV", false },
  { 0x208, 0, 2, false,  1.0, 0.0, "AccelZ", true },
  { 0x208, 2, 2, false,  1.0, 0.0, "AccelX", true },
  { 0x208, 4, 2, false,  1.0, 0.0, "AccelY", true }
};

//name, pin, 0v value, 3.3v value
AnalogueSignal defaultSignals_Analogue[] = {
  {"FR_Shock", A0, 0, 40},
  {"FL_Shock", A1, 0, 40},
  {"RR_Shock", A2, 0, 40},
  {"RL_Shock", A3, 0, 40}
};
const size_t defaultSignalCount = sizeof(defaultSignals) / sizeof(defaultSignals[0]);
const size_t defaultSignalCount_Analogue = sizeof(defaultSignals_Analogue) / sizeof(defaultSignals_Analogue[0]);
const size_t defaultSignalCount_T = defaultSignalCount + defaultSignalCount_Analogue;

// ===== Default logger config =====
LoggerConfig defaultConfig = {
  50,   // sampleRateHz
  20,   // telemRateHz
  true,   // useNaNForMissing
  "FBI_Safehouse", //Wifi SSID
  "icanttellyou", // Wifi Password
  "192.168.1.207", // Server IP
  5000, // UDP Port 
  5001 // TCP port
};

#endif