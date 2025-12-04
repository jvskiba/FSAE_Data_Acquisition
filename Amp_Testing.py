import serial
import matplotlib.pyplot as plt
from collections import deque
import time
import re

# ------------------------
# SETTINGS
# ------------------------
PORT = "COM4"          # <-- change to your port
BAUD = 115200
MAX_POINTS = 500       # number of points to keep in the plot
# ------------------------

# regex to extract voltage + current from Arduino print
line_pattern = re.compile(r"Smoothed Voltage:\s*([\d.]+)\s*V\s*Current:\s*([-.\d]+)")

# buffers
voltage_data = deque(maxlen=MAX_POINTS)
current_data = deque(maxlen=MAX_POINTS)
time_data = deque(maxlen=MAX_POINTS)

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)  # allow Arduino to reset

plt.ion()
fig, ax = plt.subplots()
line1, = ax.plot([], [], label="Current (A)")
ax.set_xlabel("Sample #")
ax.set_ylabel("Current (A)")
ax.set_title("Live Current Readings")
ax.legend()
ax.grid(True)

print("Reading serial...")

sample_count = 0

while True:
    try:
        line = ser.readline().decode(errors='ignore').strip()

        if not line:
            continue

        match = line_pattern.search(line)
        if match:
            voltage = float(match.group(1))
            current = float(match.group(2))

            voltage_data.append(voltage)
            current_data.append(current)
            time_data.append(sample_count)
            sample_count += 1

            # Update plot
            line1.set_xdata(time_data)
            line1.set_ydata(current_data)
            ax.relim()
            ax.autoscale()

            plt.pause(0.001)

            print(f"Voltage={voltage:.3f}V  Current={current:.2f}A")

    except KeyboardInterrupt:
        print("\nClosing...")
        ser.close()
        break
