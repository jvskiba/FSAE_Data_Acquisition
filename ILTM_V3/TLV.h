#pragma once
#include <cstdint>
#include <vector>
#include <string>
#include <cstring>
#include <stdexcept>

class TLV {
public:
    // ---------- Constructors ----------
    TLV(uint8_t type, const uint8_t* value, uint16_t length)
        : type(type), length(length), value(value, value + length) {}

    TLV(uint8_t type, uint8_t val) : type(type), length(1) {
        value.push_back(val);
    }

    TLV(uint8_t type, uint16_t val) : type(type), length(2) {
        value.resize(2);
        value[0] = (val >> 8) & 0xFF;   // big endian
        value[1] = val & 0xFF;
    }

    TLV(uint8_t type, uint32_t val) : type(type), length(4) {
        value.resize(4);
        value[0] = (val >> 24) & 0xFF;
        value[1] = (val >> 16) & 0xFF;
        value[2] = (val >> 8) & 0xFF;
        value[3] = val & 0xFF;
    }

    TLV(uint8_t type, float val) : type(type), length(4) {
        value.resize(4);
        std::memcpy(value.data(), &val, sizeof(float));  // binary float
    }

    TLV(uint8_t type, const std::string& str)
        : type(type), length(str.size()) {
        value.assign(str.begin(), str.end()); // no null terminator
    }

    // ---------- Getters ----------
    uint8_t getType() const { return type; }
    uint16_t getLength() const { return length; }
    const std::vector<uint8_t>& getValue() const { return value; }

    // ---------- Typed Decoding ----------
    uint8_t asUInt8() const {
        if (length != 1) throw std::runtime_error("TLV length != 1");
        return value[0];
    }

    uint16_t asUInt16() const {
        if (length != 2) throw std::runtime_error("TLV length != 2");
        return (value[0] << 8) | value[1];
    }

    uint32_t asUInt32() const {
        if (length != 4) throw std::runtime_error("TLV length != 4");
        return (uint32_t(value[0]) << 24) |
               (uint32_t(value[1]) << 16) |
               (uint32_t(value[2]) << 8)  |
                uint32_t(value[3]);
    }

    float asFloat() const {
        if (length != 4) throw std::runtime_error("TLV length != 4");
        float f;
        std::memcpy(&f, value.data(), 4);
        return f;
    }

    std::string asString() const {
        return std::string(value.begin(), value.end());
    }

private:
    friend class TLVPacket;
    uint8_t type;
    uint16_t length;
    std::vector<uint8_t> value;
};


class TLVPacket {
public:
    // Add TLV to packet
    void addTLV(const TLV& tlv) {
        tlvs.push_back(tlv);
    }

    // Serialize all TLVs into byte buffer
    std::vector<uint8_t> serialize() const {
        std::vector<uint8_t> packet;
        for (const TLV& t : tlvs) {
            packet.push_back(t.type);
            packet.push_back(t.length & 0xFF);
            packet.insert(packet.end(), t.value.begin(), t.value.end());
        }
        return packet;
    }

    // Deserialize from received buffer
    bool deserialize(const uint8_t* data, size_t len) {
        size_t index = 0;
        tlvs.clear();

        while (index + 3 <= len) {
            uint8_t type = data[index++];
            uint16_t length = (data[index++] << 8) | data[index++];

            if (index + length > len) return false; // malformed
            tlvs.emplace_back(type, data + index, length);
            index += length;
        }

        return (index == len);
    }

    const std::vector<TLV>& getTLVs() const { return tlvs; }

    // Convenience find-by-type
    const TLV* find(uint8_t type) const {
        for (const TLV& t : tlvs)
            if (t.getType() == type) return &t;
        return nullptr;
    }

private:
    std::vector<TLV> tlvs;
};



#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>

class ITV {
public:
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
