import serial
import struct
import time

PORT = "COM3"
BAUD = 115200

# Global type → name mapping
type_names = {}

# -------------------------------
# HEX → BYTES
# -------------------------------
def hex_to_bytes(hex_string):
    hex_string = hex_string.strip()
    return bytes.fromhex(hex_string)

# -------------------------------
# DECODE NAME PACKET
# -------------------------------
def decode_name_packet(byte_data):
    i = 0
    while i < len(byte_data):
        if i + 2 > len(byte_data):
            print("Truncated name TLV header at index", i)
            break

        t = byte_data[i]           # type
        name_len = byte_data[i+1]  # name length
        i += 2

        if i + name_len > len(byte_data):
            print(f"Truncated name at index {i}")
            break

        name_bytes = byte_data[i:i+name_len]
        i += name_len

        name_str = name_bytes.decode('ascii')
        type_names[t] = name_str

# -------------------------------
# DECODE FLOAT TLV PACKET
# -------------------------------
import struct

TYPE_SIZES = {
    0x01: 1,   # u8
    0x02: 2,   # u16
    0x03: 4,   # u32
    0x04: 4,   # float32
    0x05: None,# string special
    0x06: 1,   # bool
    0x07: 1,   # command enum
    0x08: 8    # u64
}

def decode_value_tlv(hex_payload):
    byte_data = bytes.fromhex(hex_payload)
    idx = 0
    result = {}  # <-- FIXED

    while idx + 2 <= len(byte_data):

        id = byte_data[idx]
        t  = byte_data[idx+1]
        idx += 2

        print(byte_data[idx-2:idx])  # header print debug

        if t == 0x05:  # string
            strlen = byte_data[idx]
            idx += 1

            if idx + strlen > len(byte_data):
                print("!! Truncated string")
                break

            val = byte_data[idx:idx+strlen].decode()
            idx += strlen

        else:
            size = TYPE_SIZES.get(t)

            if size is None:
                print(f"!! Unknown type {t}")
                break

            if idx + size > len(byte_data):
                print("!! Truncated numeric field")
                break

            raw = byte_data[idx: idx+size]
            idx += size

            if t == 0x04:
                val = struct.unpack('<f', raw)[0]
            elif t in (0x01, 0x06, 0x07):
                val = raw[0]
                if t == 0x06:
                    val = bool(val)
            else:
                val = int.from_bytes(raw, 'little')

        result[id] = val

    return result


# -------------------------------
# SERIAL INIT
# -------------------------------
def send_at(cmd):
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.1)
    resp = ser.read_all().decode(errors="ignore").strip()
    print(">>", cmd)
    print("<<", resp)
    return resp


ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(1)

send_at("AT+ADDRESS=2")
send_at("AT+NETWORKID=18")
send_at("AT+BAND=915000000")
send_at("AT+PARAMETER=7,9,1,8")

print("Listening on", PORT)

# -------------------------------
# MAIN LOOP
# -------------------------------
while True:
    try:
        line_in = ser.readline().decode(errors='ignore').strip()
        if not line_in:
            continue

        print(line_in)

        # Only parse +RCV lines
        if line_in.startswith("+RCV="):
            try:
                parts = line_in.split(",")

                if len(parts) < 3:
                    print("Malformed RCV line")
                    continue

                payload_hex = parts[2]
                payload_bytes = hex_to_bytes(payload_hex)

                # Detect if this is a name packet or TLV packet
                if len(payload_bytes) > 1 and payload_bytes[0] == 1:
                    decode_name_packet(payload_bytes[1:])
                    print("Decoded Name Packet:", type_names)

                else:
                    vals = decode_value_tlv(payload_hex)
                    print(vals)


            except Exception as e:
                print("PARSE ERROR:", e)

    except KeyboardInterrupt:
        break
