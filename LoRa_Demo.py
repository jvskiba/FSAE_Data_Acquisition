import serial
import time

# Update with your actual COM port
PORT = "COM3"
BAUD = 115200

def send_at(cmd):
    """Send an AT command and print the module's response."""
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.1)

    resp = ser.read_all().decode(errors="ignore").strip()
    print(f">> {cmd}")
    if resp:
        print(f"<< {resp}")
    return resp

# -------------------
# Initialize Serial
# -------------------

print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, BAUD, timeout=0.2)

time.sleep(1)
print("\nConfiguring RYLR998...\n")

send_at("AT")
send_at("AT+RESET")
time.sleep(0.5)

send_at("AT+NETWORKID=18")
send_at("AT+ADDRESS=2")                # This receiver is node 2
send_at("AT+BAND=915000000")
send_at("AT+PARAMETER=12,7,1,7")       # LoRa settings
send_at("AT+IPR=115200")               # Force baud (good practice)
send_at("AT+MODE=0")                   # LoRa P2P mode

print("\n--- Listening for LoRa packets ---\n")

# -------------------
# Main receive loop
# -------------------

while True:
    try:
        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            continue

        print("Received:", line)

        if line.startswith("+RCV="):
            parts = line.split(",")

            # Packet format:
            # +RCV=sender,length,payload,rssi,snr
            sender = parts[0].split("=")[1]
            length = parts[1]
            payload = parts[2]
            rssi = parts[3]
            snr = parts[4]

            print("\n--- Packet Received ---")
            print(f"Sender : {sender}")
            print(f"Length : {length}")
            print(f"Payload: {payload}")
            print(f"RSSI   : {rssi}")
            print(f"SNR    : {snr}")
            print("------------------------\n")

    except KeyboardInterrupt:
        break
