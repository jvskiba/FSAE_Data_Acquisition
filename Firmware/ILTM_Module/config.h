// config.h
#ifndef CONFIG_H
#define CONFIG_H

struct CanSignal {
  uint8_t id;
  String name;
  uint32_t canId;
  uint8_t startByte;
  uint8_t length;
  bool littleEndian;
  float mult;
  float div;
  int16_t add;
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
  uint16_t telemRateHz_Lora;
  uint16_t telemRateHz_Wifi;
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
//id,name,CAN id,startByte,length,littleEndian,multiply,divide,signed
// (value * mult) / div + add;
CanSignal defaultSignals_Can[] = {
  {11, "RPM", 0x5F0, 6, 2, false,  1.0, 1.0, 0, false },
  {12, "CLT1",0x5F2, 6, 2, false,  1.0, 10.0, 0, true },
  {13, "OilTemp", 0x5FD, 2, 2, false,  1.0, 10.0, 0, true },
  {14, "MAP", 0x5F2, 2, 2, false,  1.0, 10.0, 0, true },
  {15, "MAT", 0x5F2, 4, 2, false,  1.0, 10.0, 0, true },
  {16, "OilPres", 0x5FD, 4, 2, false,  1.0, 10.0, 0, true },
  {17, "AFR", 0x5FD, 0, 2, false,  1.0, 10.0, 0, false },
  {18, "BatV", 0x5F3, 2, 2, false,  1.0, 10.0, 0, false },
  {20, "APPS1", 0x0D2, 0, 2, true,  1.0, 1.0, 0, false },
  {21, "SIM-IN2", 0x0D2, 2, 2, true,  1.0, 1.0, 0, false },
  {22, "SIM-IN3", 0x0D2, 4, 2, true,  1.0, 1.0, 0, false },
  {23, "SIM-IN4", 0x0D2, 6, 2, true,  1.0, 1.0, 0, false },
  {24, "SIM-IN5", 0x0D3, 0, 2, true,  1.0, 1.0, 0, false },
  {25, "SIM-IN6", 0x0D3, 2, 2, true,  1.0, 1.0, 0, false },
  {26, "SIM-IN7", 0x0D3, 4, 2, true,  1.0, 1.0, 0, false },
  {27, "SIM-IN8", 0x0D3, 6, 2, true,  1.0, 1.0, 0, false },
  {28, "APPS2", 0x0D7, 6, 2, true,  1.0, 1.0, 0, false },
  {28, "TPS1", 0x0D7, 4, 2, true,  1.0, 1.0, 0, false },
  {28, "TPS2", 0x0D7, 2, 2, true,  1.0, 1.0, 0, false },
  {28, "FBPS", 0x0D7, 0, 2, true,  2000.0, 3276.0, -250, false },
  {29, "RBPS", 0x0D6, 6, 2, true,  2000.0, 3276.0, -250, false },
  {30, "SIM-IN14", 0x0D6, 4, 2, true,  1.0, 1.0, 0, false },
  {31, "SIM-IN15", 0x0D6, 2, 2, true,  1.0, 1.0, 0, false },
  {32, "SIM-IN16", 0x0D6, 0, 2, true,  1.0, 1.0, 0, false },
  {33, "SIM-IN17", 0x0D4, 0, 2, true,  1.0, 1.0, 0, false },
  {34, "SIM-IN18", 0x0D4, 2, 2, true,  1.0, 1.0, 0, false },
  {35, "AirTanK", 0x0D4, 4, 2, true,  5000.0, 3276.0, -626, false },
  {36, "RadTemp", 0x0D4, 6, 2, true,  1.0, 1.0, 0, false },
  {37, "FuelPres", 0x0D5, 0, 2, true,  75.0, 3276.0, -9, false },
  {38, "GearRaw", 0x0D5, 2, 2, true,  1.0, 1.0, 0, false },
  {39, "OilResTemp", 0x0D5, 4, 2, true,  1.0, 1.0, 0, false },
  {40, "StrAngle", 0x0D5, 6, 2, true,  1.0, 1.0, 0, false },
  {40, "Gear", 0x032, 0, 2, true,  1.0, 1.0, 0, false }
};

IMUSignal defaultSignals_IMU[] = {
  {101, "AccelX"},
  {102, "AccelY"},
  {103, "AccelZ"},
  {104, "Yaw"},
  {105, "Pitch"},
  {106, "Roll"},
  {107, "VelNorth"},
  {108, "VelEast"},
  {109, "VelDown"},
  {110, "PosLat"},
  {111, "PosLong"},
  {112, "PosAlt"},
  {113, "GyroX"},
  {114, "GyroY"},
  {115, "GyroZ"},
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
  2,   // telemRateHz_Lora
  20,   // telemRateHz_Wifi
  false,   // useNaNForMissing - Local TODO: Maybe does nothing?
  "JvS Wifi", //Wifi SSID
  "alllowercase", // Wifi Password
  "192.168.8.159", // Server IP
  5002, // UDP Port 
  2000, // RS232 TCP port
  "1", // LoRa Address
  "18", // LoRa Network ID
  "915000000", // LoRa Band
  "7,9,1,8" // LoRa Parameters
};

#endif