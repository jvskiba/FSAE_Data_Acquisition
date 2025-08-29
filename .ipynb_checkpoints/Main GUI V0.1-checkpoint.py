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

# Global state
arm_gate = False
data_log = []
conn = None
conn_lock = threading.Lock()
reset_connection = False
plot_start_index = 0

HOST = "0.0.0.0"
TCP_PORT = 5000
UDP_PORT = 5002 

# ===== GUI QUEUE =====
gui_queue = queue.Queue()

# Global flag to stop threads
running = True

def safe_after(ms, func, *args):
    try:
        if root.winfo_exists():  # only schedule if GUI exists
            root.after(ms, func, *args)
    except tk.TclError:
        pass

def on_close():
    global running, conn
    running = False
    if conn:
        try:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        except:
            pass
    root.destroy()

def log(message):
    if running:  # only if GUI is still running
        gui_queue.put(("log", message))

def schedule_plot_update():
    if running:
        gui_queue.put(("plot", None))

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
    safe_after(100, process_gui_queue)

def save_with_timestamp():
    global data_log
    save_to_csv(data_log)

def save_to_csv(data_log, folder_name="TimingGateLogs"):
    # Create folder inside user's Documents
    folder = os.path.join(os.path.expanduser("~"), "Documents", folder_name)
    os.makedirs(folder, exist_ok=True)

    # Create timestamped filename
    filename = os.path.join(folder, f"timing_log_{datetime.now():%Y%m%d_%H%M%S}.csv")

    # Save data_log to CSV
    df = pd.DataFrame(data_log, columns=["Received Time", "Event", "UTC Time", "Trigger"])
    df.to_csv(filename, index=False)
    print(f"Saved {len(data_log)} events to {filename}")

def update_plot():
    ax.clear()

    trigger_times = []
    trigger_indices = []

    for i, row in enumerate(data_log[plot_start_index:], start=plot_start_index):
        if len(row) >= 4 and row[1] == "Gate Trigger":
            try:
                trigger_val = float(row[3])
                trigger_times.append(trigger_val)
                trigger_indices.append(len(trigger_times))  # sequential trigger #
            except (ValueError, TypeError):
                continue

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

def reset_con():
    global reset_connection
    global data_log
    data_log = []
    plot_start_index = 0
    reset_connection = True
    

def reset_plot():
    global data_log
    global plot_start_index
    plot_start_index = len(data_log)
    update_plot()

def send_command(cmd):
    global conn
    try:
        if conn and conn.fileno() != -1:  # check connection is valid
            conn.sendall((cmd + "\n").encode())
            print(f"Sent command: {cmd}")
        else:
            print("No connection to Arduino.")
    except Exception as e:
        print(f"Error sending command: {e}")    

class ConsoleRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)  # auto-scroll

    def flush(self):
        pass  # Needed for compatibility with sys.stdout
        
def decode_trigger_message(msg):
    """ "utc_time": datetime,
            "trigger": float """
    try:
        parts = [p.strip() for p in msg.split(",")]
        data = {}

        i = 0
        while i < len(parts):
            label = parts[i].upper()

            if label == "TIME (UTC)" and i + 1 < len(parts):
                time_str = parts[i + 1]
                try:
                    # Parse fractional seconds
                    utc_time = datetime.strptime(time_str, "%H:%M:%S.%f")
                except ValueError:
                    # Fallback if no fractional seconds
                    utc_time = datetime.strptime(time_str, "%H:%M:%S")

                # Attach today's date in UTC
                #now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
                #utc_time = utc_time.replace(year=now.year, month=now.month, day=now.day)

                data["utc_time"] = utc_time
                i += 2

            elif label == "TRIGGER" and i + 1 < len(parts):
                data["trigger"] = float(parts[i + 1])
                i += 2

            else:
                i += 1

        return data if data else None

    except Exception as e:
        print(f"Failed to decode message: {msg} ({e})")
        return None

# Arm / Disarm Buttons
def arm():
    global arm_gate
    arm_gate = True
    status_label.config(text="Gate Armed")

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

def process_command(cmd):
    global reset_connection
    global arm_gate
    if cmd == "arm":
        arm()
    elif cmd == "disarm":
        disarm()
    elif cmd == "save":
        save_with_timestamp()
    elif cmd == "reset":
        reset()
    elif cmd.startswith("marker "):
        text = cmd[7:].strip()
        now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
        data_log.append([now, "Marker", text])
        print(f"Marker added: {text}")
    else:
        print("Unknown command. Commands: arm, disarm, save, marker <text>")

def listen_to_gate():
    global reset_connection, arm_gate, data_log, conn, running
    while running:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((HOST, PORT))
                server_socket.listen(1)
                #server_socket.settimeout(0.5)  # 500 ms timeout for accept
                log(f"Listening on {HOST}:{PORT}...")

                conn, addr = server_socket.accept()
                log(f"Connected by {addr}")

                with conn:
                    conn.settimeout(0.5)
                    while running:
                        try:
                            data = conn.recv(1024)
                            if not data:
                                log("Connection closed by client.")
                                break

                            decoded1 = data.decode().strip()
                            decoded2 = decode_trigger_message(decoded1)
                            if not decoded2:
                                continue

                            now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]

                            if arm_gate:
                                log(f"{now} (UTC) - Received: {decoded1}")
                                utc_time = decoded2.get('utc_time')
                                trigger = float(decoded2.get('trigger'))
                                data_log.append([now, "Gate Trigger", utc_time, trigger])
                            
                                # Schedule plot update
                                schedule_plot_update()

                            else:
                                log(f"{now} - Ignored (disarmed): {decoded1}")

                        except socket.timeout:
                            continue

                        if reset_connection:
                            reset_connection = False
                            break

        except Exception as e:
            log(f"Server error or disconnected: {e}")
            time.sleep(0.5)

def listen_to_ILTM():
    global reset_connection, running
    while running:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((HOST, UDP_PORT))
                server_socket.listen(1)
                #server_socket.settimeout(0.5)  # 500 ms timeout for accept
                log(f"Listening on {HOST}:{UDP_PORT}...")

                conn, addr = server_socket.accept()
                log(f"Connected by {addr}")

                with conn:
                    conn.settimeout(0.5)
                    while running:
                        try:
                            data = conn.recv(1024)
                            if not data:
                                log("Connection closed by client.")
                                break

                            decoded1 = data.decode().strip()
                            log(decoded1)

                        except socket.timeout:
                            continue

                        if reset_connection:
                            reset_connection = False
                            break

        except Exception as e:
            log(f"Server error or disconnected: {e}")
            time.sleep(0.5)



root = tk.Tk()
root.title("Timing Gate Monitor")
root.geometry("1000x700")  # optional, set window size

# ===== Top Frame =====
top_frame = ttk.Frame(root)
top_frame.grid(row=0, column=0, sticky="nsew")
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

# --- Left Panel (Controls) ---
left_panel = ttk.Frame(top_frame)
left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
top_frame.grid_columnconfigure(0, weight=1)

ttk.Button(left_panel, text="Arm Gate", command=arm).pack(pady=5)
ttk.Button(left_panel, text="Disarm Gate", command=disarm).pack(pady=5)
status_label = ttk.Label(left_panel, text="Gate Disarmed")
status_label.pack(pady=5)

ttk.Label(left_panel, text="Marker:").pack()
marker_entry = ttk.Entry(left_panel)
marker_entry.pack()
ttk.Button(left_panel, text="Add Marker", command=add_marker).pack(pady=5)
ttk.Button(left_panel, text="Save CSV", command=save_with_timestamp).pack(pady=5)
ttk.Button(left_panel, text="Reset Plot", command=reset_plot).pack(pady=5)
ttk.Button(left_panel, text="Reset Con/Log", command=reset_con).pack(pady=5)
ttk.Button(left_panel, text="Mode 1", command=lambda: send_command("SET_MODE 1")).pack(pady=5)

# --- Right Panel (Console) ---
right_panel = ttk.Frame(top_frame)
right_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
top_frame.grid_columnconfigure(1, weight=2)  # console wider

text_console = tk.Text(right_panel, height=20, width=80)
text_console.pack(fill="both", expand=True)

# ===== Bottom Frame (Plot) =====
bottom_panel = ttk.Frame(root)
bottom_panel.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
root.grid_rowconfigure(1, weight=1)

fig, ax = plt.subplots(figsize=(8,4))
canvas = FigureCanvasTkAgg(fig, master=bottom_panel)
canvas.get_tk_widget().pack(fill="both", expand=True)
update_plot()

# Start listener thread
listener_thread = threading.Thread(target=listen_to_gate, daemon=True)
listener_thread.start()
listener2_thread = threading.Thread(target=listen_to_ILTM, daemon=True)
listener2_thread.start()
safe_after(100, process_gui_queue)
root.protocol("WM_DELETE_WINDOW", on_close)

# Start Tkinter main loop
root.mainloop()

