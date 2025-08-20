import socket
import threading
import pandas as pd
from datetime import datetime

# Global state
arm_gate = False
data_log = []

def save_to_csv(filename="timing_log.csv"):
    df = pd.DataFrame(data_log, columns=["Timestamp", "Event", "Details"])
    df.to_csv(filename, index=False)
    print(f"Saved {len(data_log)} events to {filename}")

def listen_to_gate(host="0.0.0.0", port=5000):
    global arm_gate, data_log
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)
    print(f"Listening on {host}:{port}...")

    conn, addr = server_socket.accept()
    print(f"Connected by {addr}")

    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            decoded = data.decode().strip()
            now = datetime.utcnow()
            if arm_gate:
                print(f"{now} - Received: {decoded}")
                data_log.append([now, "Gate Trigger", decoded])
            else:
                print(f"{now} - Ignored (disarmed): {decoded}")
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        conn.close()
        server_socket.close()

# Run the listener in a thread so you can interact in notebook
listener_thread = threading.Thread(target=listen_to_gate, daemon=True)
listener_thread.start()

# Control functions
def arm():
    global arm_gate
    arm_gate = True
    print("Gate armed!")

def disarm():
    global arm_gate
    arm_gate = False
    print("Gate disarmed!")

def add_marker(text):
    now = datetime.utcnow()
    data_log.append([now, "Marker", text])
    print(f"Marker added: {text}")
