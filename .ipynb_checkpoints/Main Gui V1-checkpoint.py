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
TCP_PORT = 5000
UDP_PORT = 5002 

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

HOST = "0.0.0.0"
TCP_PORT = 5000
UDP_PORT = 5002

def tcp_listener():
    """Listen for TCP connections and print messages. Reconnects on failure."""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, TCP_PORT))
                s.listen(1)
                print(f"[TCP] Listening on {HOST}:{TCP_PORT}")
                
                conn, addr = s.accept()
                with conn:
                    print(f"[TCP] Connected by {addr}")
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            print("[TCP] Connection closed")
                            break
                        print(f"[TCP] {data.decode(errors='ignore')}")
        except Exception as e:
            print(f"[TCP] Error: {e}, retrying in 2s...")
            time.sleep(2)


def udp_listener():
    """Listen for UDP datagrams and print messages."""
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, UDP_PORT))
                print(f"[UDP] Listening on {HOST}:{UDP_PORT}")
                while True:
                    data, addr = s.recvfrom(1024)
                    print(f"[UDP] {addr}: {data.decode(errors='ignore')}")
        except Exception as e:
            print(f"[UDP] Error: {e}, retrying in 2s...")
            time.sleep(2)


def start_listeners():
    """Start both TCP and UDP listeners in separate threads."""
    threading.Thread(target=tcp_listener, daemon=True).start()
    threading.Thread(target=udp_listener, daemon=True).start()

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

#

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

# Handle window close
root.protocol("WM_DELETE_WINDOW", on_exit)
root.after(100, process_gui_queue)
root.mainloop()
