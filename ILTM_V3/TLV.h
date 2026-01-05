#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <unordered_map>
#include <iostream>

#include <cstdint>
#include <vector>
#include <unordered_map>
#include <variant>
#include <string>
#include <cstring>
#include <iostream>

class ITV {
public:
    static void writeName(uint8_t id, const std::string& s, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x00);
        out.push_back((uint8_t)s.size());
        out.insert(out.end(), s.begin(), s.end());
    }

    static void writeU8(uint8_t id, uint8_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x01);
        out.push_back(val);
    }

    static void writeU16(uint8_t id, uint16_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x02);
        out.push_back(val & 0xFF);
        out.push_back((val >> 8) & 0xFF);
    }

    static void writeU32(uint8_t id, uint32_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x03);
        for (int i = 0; i < 4; i++)
            out.push_back((val >> (8*i)) & 0xFF);
    }

    static void writeF32(uint8_t id, float val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x04);
        uint8_t b[4];
        std::memcpy(b, &val, 4);
        out.insert(out.end(), b, b+4);
    }

    static void writeString(uint8_t id, const std::string& s, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x05);
        out.push_back((uint8_t)s.size());
        out.insert(out.end(), s.begin(), s.end());
    }

    static void writeBool(uint8_t id, bool val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x06);
        out.push_back(val ? 1 : 0);
    }

    static void writeCmd(uint8_t id, uint8_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x07);
        out.push_back(val);
    }

    static void writeU64(uint8_t id, uint64_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x08);
        for (int i = 0; i < 8; i++)
            out.push_back((val >> (8*i)) & 0xFF);
    }
};

static const std::unordered_map<uint8_t, int> TYPE_SIZES = {
    {0x00, -1}, // name (variable)
    {0x01, 1},  // u8
    {0x02, 2},  // u16
    {0x03, 4},  // u32
    {0x04, 4},  // float
    {0x05, -1}, // string (variable)
    {0x06, 1},  // bool
    {0x07, 1},  // cmd enum
    {0x08, 8}   // u64
};

// Define TLV value type
using TLVValue = std::variant<uint8_t, uint16_t, uint32_t, uint64_t, float, bool, std::string>;
using TLVMap = std::unordered_map<uint8_t, TLVValue>;

TLVMap decodeValueTLV(const std::vector<uint8_t>& byte_data) {
    TLVMap result;
    size_t idx = 0;

    while (idx + 2 <= byte_data.size()) {
        uint8_t id = byte_data[idx];
        uint8_t t  = byte_data[idx + 1];
        idx += 2;

        // String types
        if (t == 0x05 || t == 0x00) {
            if (idx >= byte_data.size()) break;
            uint8_t strlen = byte_data[idx++];
            if (idx + strlen > byte_data.size()) break;

            std::string val(reinterpret_cast<const char*>(&byte_data[idx]), strlen);
            idx += strlen;
            result[id] = val;
            continue;
        }

        // Numeric types
        auto it = TYPE_SIZES.find(t);
        if (it == TYPE_SIZES.end()) break;

        size_t size = it->second;
        if (idx + size > byte_data.size()) break;

        const uint8_t* raw = &byte_data[idx];
        idx += size;

        switch (t) {
            case 0x01: result[id] = raw[0]; break; // u8
            case 0x02: result[id] = static_cast<uint16_t>(raw[0] | (raw[1] << 8)); break; // u16
            case 0x03: result[id] = static_cast<uint32_t>(raw[0] | (raw[1] << 8) | (raw[2] << 16) | (raw[3] << 24)); break; // u32
            case 0x04: {
                float fval;
                std::memcpy(&fval, raw, sizeof(float));
                result[id] = fval;
                break;
            }
            case 0x06: result[id] = raw[0] != 0; break; // bool
            case 0x07: result[id] = raw[0]; break; // cmd enum
            case 0x08: {
                uint64_t val = 0;
                for (int i = 0; i < 8; i++) val |= (uint64_t(raw[i]) << (8*i));
                result[id] = val;
                break;
            }
            default: break;
        }
    }

    return result;
}

// Optional: helper to print TLVMap
void printTLVMap(const TLVMap& map) {
    for (auto& [id, val] : map) {
        std::visit([&](auto&& v){
            using T = std::decay_t<decltype(v)>;
            if constexpr (std::is_same_v<T, std::string>)
                std::cout << "ID " << int(id) << ": " << v << "\n";
            else if constexpr (std::is_same_v<T, float>)
                std::cout << "ID " << int(id) << ": " << v << "f\n";
            else
                std::cout << "ID " << int(id) << ": " << +v << "\n";
        }, val);
    }
}
