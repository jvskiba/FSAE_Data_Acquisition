import time
import serial

PORT = "COM4"
BAUD = 115200

debug = True

ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(1)




while(1):
    line = ser.readline().decode(errors='ignore').strip()
    print(line)
    data = {}
    for pair in line.split(","):
        try:
            key, val = pair.split(":", 1)
            data[int(key)] = float(val)  # or smarter parsing
        except:
            print("oops")

    print(data)