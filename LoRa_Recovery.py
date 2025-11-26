import serial
import time

PORT = "COM3"
BAUD = 115200

def send_at(ser, cmd, wait=0.2):
    ser.write((cmd + "\r\n").encode())
    time.sleep(wait)
    resp = ser.read_all().decode(errors='ignore').strip()
    print(f">> {cmd}\n<< {resp}")
    return resp

ser = serial.Serial(PORT, BAUD, timeout=0.5)
time.sleep(1)

# Initialize LoRaWAN module
send_at(ser, "AT")
send_at(ser, "AT+RESET")
send_at(ser, "AT+MODE=2")  # LoRaWAN mode
send_at(ser, "AT+NETWORKID=18")
send_at(ser, "AT+DEVADDR=260111FD")
send_at(ser, "AT+NWKSKEY=00112233445566778899AABBCCDDEEFF")
send_at(ser, "AT+APPSKEY=FFEEDDCCBBAA99887766554433221100")
send_at(ser, "AT+JOIN=1")  # ABP join

print("\n--- Listening for LoRaWAN packets ---\n")

while True:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print("Received:", line)
        # LoRaWAN modules will send something like:
        # +RCV=<port>,<len>,<payload>,<RSSI>,<SNR>
