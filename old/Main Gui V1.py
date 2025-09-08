import socket
import threading
import pandas as pd
from datetime import datetime, UTC
import time
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import queue

gui_queue = queue.Queue()
arm_gate = False
HOST = "0.0.0.0"
GATE_PORT = 5000
UDP_PORT = 5002 

latest_telem_data = None

running = True # Global flag to stop threads

def on_exit():
    global running
    print("Exiting app...")
    running = False
    root.destroy()
    sys.exit(0)


def arm():
    global arm_gate
    arm_gate = True
    status_label.config(text="Gate Armed")
    log("test")

def disarm():
    global arm_gate
    arm_gate = False
    status_label.config(text="Gate Disarmed")

# Add marker
def add_marker():
    text = marker_entry.get()
    if text:
        now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
        data_log.append([now, "Marker", None, text])
        log(f"Marker added: {text}")
        marker_entry.delete(0, tk.END)

def update_plot():
    ax.clear()

    trigger_times = []
    trigger_indices = []

    if trigger_times:
        ax.plot(trigger_indices, trigger_times, marker='o', linestyle='-', color='blue')
        ax.set_ylabel("Elapsed Time (s)")
        ax.set_xlabel("Trigger #")
        ax.set_title("Gate Trigger Times")
    else:
        ax.set_ylabel("Elapsed Time (s)")
        ax.set_xlabel("Trigger #")
        ax.set_title("Gate Trigger Times (No valid data)")

    ax.grid(True)
    canvas.draw()

def process_gui_queue():
    """Process messages from other threads and update GUI."""
    if not running:
        return  # GUI gone, stop processing
        
    while not gui_queue.empty():
        item = gui_queue.get()
        if item[0] == "log":
            text_console.insert(tk.END, item[1] + "\n")
            text_console.see(tk.END)
        elif item[0] == "plot":
            update_plot()
    root.after(100, process_gui_queue)

def log(message):
    if running:  # only if GUI is still running
        gui_queue.put(("log", message))

def gate_listener():
    """Listen for TCP connections and print messages. Reconnects on failure."""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, GATE_PORT))
                s.listen(1)
                print(f"[TCP] Listening on {HOST}:{GATE_PORT}")
                
                conn, addr = s.accept()
                with conn:
                    log(f"[TCP] Connected by {addr}")
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            print("[TCP] Connection closed")
                            break
                        print(f"[TCP] {data.decode(errors='ignore')}")
        except Exception as e:
            log(f"[TCP] Error: {e}, retrying in 2s...")
            time.sleep(2)


def iltm_udp_listener():
    global latest_telem_data
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, UDP_PORT))
                log(f"[UDP] Listening on {HOST}:{UDP_PORT}")
                while True:
                    data, addr = s.recvfrom(1024)
                    line = data.decode(errors="ignore")
                    row = parse_row(line, CanRow)
                    if row:
                        latest_telem_data = row
                        root.after(1, update_gauges)
        except Exception as e:
            log(f"[UDP] Error: {e}, retrying in 2s...")
            time.sleep(2)


def start_listeners():
    """Start both TCP and UDP listeners in separate threads."""
    threading.Thread(target=gate_listener, daemon=True).start()
    threading.Thread(target=iltm_udp_listener, daemon=True).start()

def update_gauges():
    tps_label.config(text=latest_telem_data.TPS)

def update_timing_log():
    timing_gate_label.config(text=latest_telem_data.TPS)




from dataclasses import dataclass, make_dataclass
CONFIG_FILE = "can_config.csv"  # same file you put on SD/ESP32


# =====================
# Load CAN signal names from CSV
# =====================
def load_config_signals(config_file: str) -> list[str]:
    try:
        with open(config_file, newline="") as f:
            reader = csv.DictReader(f)
            # Expect the CSV to have a "Name" column (like your ECU sheet)
            return [row["Name"] for row in reader]
    except FileNotFoundError:
        print(f"Config file {config_file} not found. Using defaults.")
        return ["timestamp", "RPM", "CLT", "TPS", "VSS"]


# =====================
# Make a dynamic dataclass
# =====================
def make_can_row_class(signal_names: list[str]):
    # Ensure timestamp is always first
    fields = [("timestamp", float)] + [(name, float) for name in signal_names if name != "timestamp"]
    return make_dataclass("CanRow", fields)


# =====================
# Parse incoming UDP line
# =====================
def parse_row(line: str, row_class):
    try:
        parts = line.strip().split(",")
        values = [float(x) if x not in ("NaN", "nan") else float("nan") for x in parts]
        return row_class(*values)
    except Exception as e:
        print("Parse error:", e, "for line:", line)
        return None







root = tk.Tk()
root.title("Dashboard Layout")
root.geometry("1400x900")  # set window size

# Configure grid
for i in range(3):
    root.rowconfigure(i, weight=1, uniform="row")
for j in range(4):
    root.columnconfigure(j, weight=1, uniform="col")

frame_a = tk.Frame(root, bg="lightblue")
frame_b = tk.Frame(root, bg="lightgreen")
frame_c = tk.Frame(root, bg="lightcoral")
frame_d = tk.Frame(root, bg="khaki")
frame_e = tk.Frame(root, bg="plum")
frame_f = tk.Frame(root, bg="lightblue")
frame_g = tk.Frame(root, bg="lightgreen")

# Place frames in grid
frame_a.grid(row=0, column=0, rowspan=2, sticky="nsew") 
frame_b.grid(row=0, column=1, columnspan=2, rowspan=2, sticky="nsew")  
frame_c.grid(row=0, column=3, sticky="nsew")  
frame_d.grid(row=2, column=0, sticky="nsew")    
frame_e.grid(row=2, column=1, sticky="nsew")    
frame_f.grid(row=2, column=2, sticky="nsew")    
frame_g.grid(row=1, column=3, rowspan=2, sticky="nsew")

# Gauges
tps_label = ttk.Label(frame_b, text="Nan")
tps_label.pack(pady=5)

# Timing Gate Controls
ttk.Button(frame_d, text="Arm Gate", command=arm).pack(pady=5)
ttk.Button(frame_d, text="Disarm Gate", command=disarm).pack(pady=5)
status_label = ttk.Label(frame_d, text="Gate Disarmed")
status_label.pack(pady=5)
ttk.Label(frame_d, text="Marker:").pack()
marker_entry = ttk.Entry(frame_d)
marker_entry.pack()
ttk.Button(frame_d, text="Add Marker", command=add_marker).pack(pady=5)

# Timing Log
timing_gate_label = ttk.Label(frame_e, text="Nan")
timing_gate_label.pack(pady=5)

# Timing Plot
fig, ax = plt.subplots(figsize=(8,4))
canvas = FigureCanvasTkAgg(fig, master=frame_f)
canvas.get_tk_widget().pack(fill="both", expand=True)
update_plot()

# Console Log
text_console = tk.Text(frame_g, height=20, width=80)
text_console.pack(fill="both", expand=True)

if __name__ == "__main__":
    start_listeners()

signal_names = load_config_signals(CONFIG_FILE)
log(f"Loaded signals: {signal_names}")
CanRow = make_can_row_class(signal_names)


# Handle window close
root.protocol("WM_DELETE_WINDOW", on_exit)
root.after(100, process_gui_queue)
root.mainloop()
