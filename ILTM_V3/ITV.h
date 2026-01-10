#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <unordered_map>
#include <iostream>
#include <variant>

class ITV {
public:
    // -------------------------
    // Types
    // -------------------------
    using ITVValue = std::variant<
        uint8_t,
        uint16_t,
        uint32_t,
        uint64_t,
        float,
        bool,
        std::string
    >;

    using ITVMap = std::unordered_map<uint8_t, ITVValue>;

    // -------------------------
    // ENCODERS
    // -------------------------
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

    static void writeU64(uint8_t id, uint64_t val, std::vector<uint8_t>& out) {
        out.push_back(id);
        out.push_back(0x08);
        for (int i = 0; i < 8; i++)
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

    // -------------------------
    // DECODER
    // -------------------------
    static bool decode(const uint8_t* data, size_t len, ITVMap& out) {
        out.clear();
        size_t idx = 0;
        while (idx + 2 <= len) {
            uint8_t id = data[idx++];
            uint8_t t  = data[idx++];

            // variable-length strings
            if (t == 0x00 || t == 0x05) {
                if (idx >= len) return false;
                uint8_t sl = data[idx++];
                if (idx + sl > len) return false;

                out[id] = std::string((const char*)&data[idx], sl);
                idx += sl;
                continue;
            }

            int sz = typeSize(t);
            if (sz <= 0 || idx + sz > len) return false;

            const uint8_t* raw = &data[idx];
            idx += sz;

            switch (t) {
                case 0x01: out[id] = raw[0]; break;
                case 0x02: out[id] = (uint16_t)(raw[0] | (raw[1] << 8)); break;
                case 0x03: out[id] = (uint32_t)(raw[0] | (raw[1] << 8) | (raw[2] << 16) | (raw[3] << 24)); break;
                case 0x04: {
                    float f;
                    std::memcpy(&f, raw, 4);
                    out[id] = f;
                    break;
                }
                case 0x06: out[id] = (bool)raw[0]; break;
                case 0x07: out[id] = raw[0]; break;
                case 0x08: {
                    uint64_t v = 0;
                    for (int i = 0; i < 8; i++) v |= (uint64_t(raw[i]) << (8*i));
                    out[id] = v;
                    break;
                }
                default:
                    return false;
            }
        }
        return true;
    }

    static bool decode_line(char* hex, ITVMap& out) {
        uint8_t buf[128];
        size_t blen = hexToBytes(hex, buf, sizeof(buf));
        return decode(buf, blen, out);
    }

    static String bytesToHex(const std::vector<uint8_t>& data) {
        const char* hex = "0123456789ABCDEF";
        String out;
        out.reserve(data.size() * 2);

        for (uint8_t b : data) {
            out += hex[(b >> 4) & 0x0F];
            out += hex[b & 0x0F];
        }
        return out;
    }

    static void splitOnTLVBoundaries(
        const std::vector<uint8_t>& in,
        size_t maxPayload,
        std::vector<std::vector<uint8_t>>& outPackets
    ) {
        outPackets.clear();
        if (in.empty()) return;

        size_t idx = 0;
        std::vector<uint8_t> current;

        while (idx < in.size()) {
            size_t tlv_len = tlvSize(in.data(), in.size(), idx);
            if (tlv_len == 0) {
                // malformed TLV, drop everything safely
                return;
            }

            // If this TLV alone is too big → protocol error
            if (tlv_len > maxPayload) {
                // You may want to log or assert here
                return;
            }

            // Would this TLV overflow the packet?
            if (current.size() + tlv_len > maxPayload) {
                outPackets.push_back(current);
                current.clear();
            }

            // Append TLV atomically
            current.insert(
                current.end(),
                in.begin() + idx,
                in.begin() + idx + tlv_len
            );

            idx += tlv_len;
        }

        if (!current.empty()) {
            outPackets.push_back(current);
        }
    }

    

private:
    static int typeSize(uint8_t t) {
        switch (t) {
            case 0x01: return 1; //uint 8
            case 0x02: return 2; //uint 16
            case 0x03: return 4; //uint 32
            case 0x04: return 4; //float
            case 0x05: return 1; //string
            case 0x06: return 1; //bool
            case 0x07: return 1; //cmd
            case 0x08: return 8; //uint64
            default:   return -1;
        }
    }

    static uint8_t hexNibble(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return 0;
    }

    static size_t hexToBytes(const char* hex, uint8_t* out, size_t maxLen) {
        size_t len = strlen(hex) / 2;
        if (len > maxLen) len = maxLen;

        for (size_t i = 0; i < len; i++) {
            out[i] = (hexNibble(hex[2*i]) << 4) |
                    hexNibble(hex[2*i + 1]);
        }
        return len;
    }

    static size_t tlvSize(const uint8_t* data, size_t len, size_t offset) {
        if (offset + 2 > len) return 0;

        uint8_t t = data[offset + 1];

        // variable-length types
        if (t == 0x00 || t == 0x05) {
            if (offset + 3 > len) return 0;
            uint8_t sl = data[offset + 2];
            return 3 + sl;   // id + type + strlen + data
        }

        int sz = typeSize(t);
        if (sz <= 0) return 0;

        return 2 + sz;      // id + type + value
    }

};