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
def decode_value_tlv(hex_payload):
    data = bytes.fromhex(hex_payload)
    idx = 0
    out = []

    while idx < len(data):

        if idx + 2 > len(data):
            print("Malformed TLV header at index", idx)
            break

        t = data[idx]
        l = data[idx + 1]
        idx += 2

        if idx + l > len(data):
            print("Malformed TLV value at index", idx)
            break

        val_bytes = data[idx: idx + l]
        idx += l

        if l == 4:  # Float32 LE
            value = struct.unpack('<f', val_bytes)[0]
        else:
            value = val_bytes

        out.append((t, value))

    return out

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

                    for t, v in vals:
                        name = type_names.get(t, f"Type{t}")
                        if isinstance(v, float):
                            print(f"{name} ({t}) = {v:.3f}")
                        else:
                            print(f"{name} ({t}) = RAW {v}")

            except Exception as e:
                print("PARSE ERROR:", e)

    except KeyboardInterrupt:
        break
