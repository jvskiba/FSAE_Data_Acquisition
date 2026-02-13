import serial
import struct
import time

PORT = "COM3"
BAUD = 115200

debug = False

# Global type → name mapping
type_names = {}

def tlv_u8(id, val):
    return bytes([id, 0x01, val])

def tlv_u16(id, val):
    return bytes([id, 0x02]) + val.to_bytes(2, 'little')

def tlv_u64(id, val):
    return bytes([id, 0x08]) + val.to_bytes(8, 'little')

def now_us():
    return time.time_ns() // 1000

CMD_SYNC_REQ  = 0x01
CMD_SYNC_RESP = 0x02

def handle_itv_ntp_request(vals):
    """
    vals = decoded TLV map {id: value}
    """
    if 0x01 not in vals:
        return None

    cmd = vals[0x01]

    if cmd != CMD_SYNC_REQ:
        return None

    req_id = vals.get(0x02, 0)
    t1     = vals.get(0x03, 0)

    t2 = now_us()
    t3 = now_us()

    resp = b""
    resp += tlv_u8(0x01, CMD_SYNC_RESP)
    resp += tlv_u16(0x02, req_id)
    resp += tlv_u64(0x03, t1)
    resp += tlv_u64(0x04, t2)
    resp += tlv_u64(0x05, t3)

    return resp


# -------------------------------
# HEX → BYTES
# -------------------------------
def hex_to_bytes(hex_string):
    hex_string = hex_string.strip()
    return bytes.fromhex(hex_string)

# -------------------------------
# DECODE FLOAT TLV PACKET
# -------------------------------
import struct

TYPE_SIZES = {
    0x00: None,# Name String registration
    0x01: 1,   # u8
    0x02: 2,   # u16
    0x03: 4,   # u32
    0x04: 4,   # float32
    0x05: None,# string special
    0x06: 1,   # bool
    0x07: 1,   # command enum
    0x08: 8    # u64
}

id_to_name = {}

def decode_value_tlv(hex_payload):
    byte_data = bytes.fromhex(hex_payload)
    idx = 0
    result = {}

    while idx + 2 <= len(byte_data):

        id = byte_data[idx]
        t  = byte_data[idx+1]
        idx += 2

        if t == 0x00:
            strlen = byte_data[idx]
            idx += 1

            if idx + strlen > len(byte_data):
                print("!! Truncated string")
                break

            name = byte_data[idx:idx+strlen].decode()
            idx += strlen
            id_to_name[id] = name
            if debug:
                print(f"[NAME] ID {id} = \"{name}\"")
            continue

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

# ++++++++++++++

# ++++++++++++++

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
            parts = line_in.split(",")
            payload_hex = parts[2]

            vals = decode_value_tlv(payload_hex)

            for id, v in vals.items():
                name = id_to_name.get(id, f"ID{id}")
                print(f"{name}: {v}")

            resp = handle_itv_ntp_request(vals)

            if resp:
                hex_out = resp.hex().upper()
                print("TX BYTES:", len(resp))
                print("TX HEX  :", hex_out)

                send_at(f"AT+SEND=1,{len(resp)*2},{hex_out}")
                
    except KeyboardInterrupt:
        break
