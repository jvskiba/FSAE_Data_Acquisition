// config.h
#ifndef CONFIG_H
#define CONFIG_H

struct CanSignal {
  uint8_t id;
  String name;
  uint16_t canId;
  uint8_t startByte;
  uint8_t length;
  bool littleEndian;
  float mult;
  float div;
  bool is_signed;
};

struct SIMSignal {
  uint8_t id;
  String name;
};

struct IMUSignal {
  uint8_t id;
  String name;
};

struct MainConfig {
  uint16_t sampleRateHz;
  uint16_t telemRateHz;
  bool useNaNForMissing;
  String ssid;
  String password; 
  String host;
  uint16_t udpPort; 
  uint16_t tcpPort;
  String lora_address;
  String lora_netId;
  String lora_band;
  String lora_param;
};

// ===== Default CAN signal definitions =====
//id,startByte,length,littleEndian,multiply,divide,name, signed
CanSignal defaultSignals_Can[] = {
  {11, "RPM", 0x5F0, 6, 2, false,  1.0, 1.0, false },
  {12, "VSS", 0x61A, 0, 2, false,  1.0, 10.0, false },
  {13, "Gear", 0x611, 6, 1, false,  1.0, 1.0, false },
  {14, "STR", 0x5FE, 4, 2, false,  1.0, 10.0, true },
  {15, "TPS", 0x5F3, 0, 2, false,  1.0, 10.0, false },
  {16, "CLT1",0x5F2, 6, 2, false,  1.0, 10.0, true },
  {17, "CLT2", 0x5FE, 0, 2, false,  1.0, 10.0, true },
  {18, "OilTemp", 0x5FD, 4, 2, false,  1.0, 10.0, true },
  {19, "MAP", 0x5F2, 2, 2, false,  1.0, 10.0, true },
  {20, "MAT", 0x5F2, 4, 2, false,  1.0, 10.0, true },
  {21, "FuelPres", 0x5FD, 6, 2, false,  1.0, 10.0, true },
  {22, "OilPres", 0x5FD, 2, 2, false,  1.0, 10.0, true },
  {23, "AFR", 0x5FD, 0, 2, false,  1.0, 10.0, false },
  {24, "BatV", 0x5F3, 2, 2, false,  1.0, 10.0, false }
};

IMUSignal defaultSignals_IMU[] = {
  {1, "AccelX"},
  {2, "AccelY"},
  {3, "AccelZ"},
  {4, "Heading"},
  {5, "Pitch"},
  {6, "Roll"},
  {7, "Velocity"},
};

SIMSignal defaultSignals_SIM[] = {
  {1, "AccelX"},
  {2, "AccelY"},
  {3, "AccelZ"},
  {4, "Heading"},
  {5, "Pitch"},
  {6, "Roll"},
  {7, "Velocity"},
};

// ===== Default logger config =====
MainConfig defaultConfig = {
  50,   // sampleRateHz
  20,   // telemRateHz
  false,   // useNaNForMissing - Local TODO: Maybe does nothing?
  "FBI_Safehouse", //Wifi SSID
  "icanttellyou", // Wifi Password
  "192.168.2.206", // Server IP
  5002, // UDP Port 
  2000, // RS232 TCP port
  "1", // LoRa Address
  "18", // LoRa Network ID
  "915000000", // LoRa Band
  "7,9,1,8" // LoRa Parameters
};

#endif