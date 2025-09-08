import socket
import threading
import pandas as pd
from datetime import datetime, UTC
import time
import os

# Global state
arm_gate = False
data_log = []
conn = None
conn_lock = threading.Lock()
reset_connection = False

HOST = "0.0.0.0"
PORT = 5000

def save_with_timestamp():
    # Ensure folder exists
    folder = "datalogs"
    os.makedirs(folder, exist_ok=True)

    # Build file path with timestamp
    filename = f"timing_log_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv"
    filepath = os.path.join(folder, filename)

    # Save CSV
    save_to_csv(filepath)
    print(f"Saved log to {filepath}")
    
def save_to_csv(filename="timing_log.csv"):
    df = pd.DataFrame(data_log, columns=["Timestamp", "Event", "Event Time", "Elapsed Time"])
    df.to_csv(filename, index=False)
    print(f"Saved {len(data_log)} events to {filename}")

from datetime import datetime

def decode_trigger_message(msg):
    """
    Returns a dict like:
        {
            "utc_time": datetime,
            "trigger": float
        }
    """
    try:
        parts = [p.strip() for p in msg.split(",")]
        data = {}

        i = 0
        while i < len(parts):
            label = parts[i].upper()

            if label == "Time (UTC)" and i + 1 < len(parts):
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



def listen_to_gate():
    global reset_connection
    global arm_gate, data_log, conn
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((HOST, PORT))
                server_socket.listen(1)
                print(f"Listening on {HOST}:{PORT}...")

                conn, addr = server_socket.accept()
                print(f"Connected by {addr}")

                with conn:
                    conn.settimeout(0.5)
                    while True:
                        try:
                            data = conn.recv(1024)
                            if not data:
                                print("Connection closed by client.")
                                break
                            decoded1 = data.decode().strip()
                            decoded2 = decode_trigger_message(decoded1)
                            now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
                            if arm_gate:
                                print(f"{now} (UTC) - Received: {decoded1}")
                                utc_time = decoded2.get('utc_time')
                                trigger = decoded2.get('trigger')
                                
                                data_log.append([now, "Gate Trigger", utc_time if utc_time else None, trigger])

                            else:
                                print(f"{now} - Ignored (disarmed): {decoded1}")
                        
                        except socket.timeout:
                            # no data this cycle, just check reset_connection
                            pass
                        
                        if reset_connection:
                            reset_connection = False
                            break
        except Exception as e:
            print(f"Server error or disconnected: {e}")
            time.sleep(1)  # wait before retrying

# Start listener thread
listener_thread = threading.Thread(target=listen_to_gate, daemon=True)
listener_thread.start()

print("Timing gate server started! Type commands to control:")

def process_command(cmd):
    global reset_connection
    global arm_gate
    if cmd == "arm":
        arm_gate = True
        print("Gate armed!")
    elif cmd == "disarm":
        arm_gate = False
        print("Gate disarmed!")
    elif cmd == "save":
        save_with_timestamp()
    elif cmd == "reset":
        reset_connection = True
    elif cmd.startswith("marker "):
        text = cmd[7:].strip()
        now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]
        data_log.append([now, "Marker", text])
        print(f"Marker added: {text}")
    else:
        print("Unknown command. Commands: arm, disarm, save, marker <text>")

# Simple command loop (run this in a Jupyter cell or Python script)
while True:
    try:
        cmd = input("Enter command: \n").strip()
        if cmd == "exit":
            print("Exiting...")
            break
        process_command(cmd)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected. Exiting...")
        break
