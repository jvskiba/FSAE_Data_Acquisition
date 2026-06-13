import serial
import time
import matplotlib.pyplot as plt
from collections import deque
from matplotlib.widgets import Button

def reset_plots(event):
    # Clear data arrays
    time_data.clear()
    iat_data.clear()
    bps_data.clear()

    rssi_data.clear()
    snr_data.clear()
    rssi_time.clear()

    # Clear plot lines
    line_iat.set_xdata([])
    line_iat.set_ydata([])

    line_bps.set_xdata([])
    line_bps.set_ydata([])

    line_rssi.set_xdata([])
    line_rssi.set_ydata([])

    line_snr.set_xdata([])
    line_snr.set_ydata([])

    # Redraw both figures
    fig1.canvas.draw()
    fig2.canvas.draw()

    print("Plots have been reset!")


def send_at(cmd):
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.1)
    resp = ser.read_all().decode(errors="ignore").strip()
    print(">>", cmd)
    print("<<", resp)
    return resp

PORT = "COM3"
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=0.1)
send_at("AT+ADDRESS=2")
send_at("AT+NETWORKID=18")
send_at("AT+BAND=915000000")
send_at("AT+PARAMETER=7,9,1,8")

print("Listening...")

last_seq = -1
last_packet_time = None

packet_times = deque(maxlen=200)
byte_times = deque(maxlen=200)

time_data = []
iat_data = []  
bps_data = []

rssi_data = []
snr_data = []
rssi_time = []

start_time = time.time()

# -------------------------
# Figure 1: IAT + BPS
# -------------------------
plt.ion()
fig1, ax1 = plt.subplots()
# --- Reset Button ---
reset_ax = fig1.add_axes([0.8, 0.92, 0.15, 0.05])  # x, y, width, height
reset_button = Button(reset_ax, 'Reset')
reset_button.on_clicked(reset_plots)



# Inter-packet time
line_iat, = ax1.plot([], [], label="Inter-packet time (ms)", color="tab:orange")
ax1.set_xlabel("Time (s)")
ax1.set_ylabel("Inter-packet time (ms)", color="tab:orange")
ax1.tick_params(axis='y', labelcolor="tab:orange")
ax1.grid(True)

# Bytes per second
ax2 = ax1.twinx()
line_bps, = ax2.plot([], [], label="Bytes/sec", color="tab:green")
ax2.set_ylabel("Bytes/sec", color="tab:green")
ax2.tick_params(axis='y', labelcolor="tab:green")

# -------------------------
# Figure 2: RSSI + SNR
# -------------------------
fig2, ax_rssi = plt.subplots()

line_rssi, = ax_rssi.plot([], [], label="RSSI", color="tab:red")
ax_rssi.set_xlabel("Time (s)")
ax_rssi.set_ylabel("RSSI (dBm)", color="tab:red")
ax_rssi.tick_params(axis='y', labelcolor="tab:red")
ax_rssi.grid(True)

ax_snr = ax_rssi.twinx()
line_snr, = ax_snr.plot([], [], label="SNR", color="tab:blue")
ax_snr.set_ylabel("SNR (dB)", color="tab:blue")
ax_snr.tick_params(axis='y', labelcolor="tab:blue")

# -------------------------
# Update Functions
# -------------------------

def update_plot1():
    line_iat.set_xdata(time_data)
    line_iat.set_ydata(iat_data)

    line_bps.set_xdata(time_data)
    line_bps.set_ydata(bps_data)

    ax1.relim(); ax1.autoscale_view()
    ax2.relim(); ax2.autoscale_view()

    fig1.canvas.draw()
    fig1.canvas.flush_events()


def update_plot2():
    line_rssi.set_xdata(rssi_time)
    line_rssi.set_ydata(rssi_data)

    line_snr.set_xdata(rssi_time)
    line_snr.set_ydata(snr_data)

    ax_rssi.relim(); ax_rssi.autoscale_view()
    ax_snr.relim(); ax_snr.autoscale_view()

    fig2.canvas.draw()
    fig2.canvas.flush_events()


# -------------------------
# Main Loop
# -------------------------
last_update_time = 0

while True:
    line_in = ser.readline().decode(errors='ignore').strip()
    if not line_in:
        continue

    print("RX:", line_in)

    if line_in.startswith("+RCV="):
        try:
            parts = line_in.split(",")

            payload = parts[2]
            rssi = int(parts[-2])
            snr = float(parts[-1])

            pkt_bytes = len(payload.encode())
            now = time.time()

            # ----------- Inter-packet time -----------
            if last_packet_time is None:
                iat_ms = 0
            else:
                iat_ms = (now - last_packet_time) * 1000
            last_packet_time = now

            # ----------- Bytes/sec -----------
            byte_times.append((now, pkt_bytes))
            bps = sum(b for t, b in byte_times if now - t <= 1.0)

            # Store data
            time_data.append(now - start_time)
            iat_data.append(iat_ms)
            bps_data.append(bps)

            # ----------- RSSI & SNR -----------
            rssi_time.append(now - start_time)
            rssi_data.append(rssi)
            snr_data.append(snr)

            # Update plots
            # Update plots at 10 Hz
            now = time.time()
            if now - last_update_time >= 1:   # 0.1 sec = 10 Hz
                update_plot1()
                update_plot2()
                last_update_time = now


            # Detect packet loss
            if payload.startswith("SEQ="):
                seq = int(payload.split("=")[1])
                if last_seq != -1 and seq != last_seq + 1:
                    print(f"!!! LOST PACKETS: expected {last_seq+1}, got {seq}")
                last_seq = seq

        except Exception as e:
            print("PARSE ERROR:", e)
