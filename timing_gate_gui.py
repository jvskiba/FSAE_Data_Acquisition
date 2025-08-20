import socket
import threading
import pandas as pd
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox

HOST = "0.0.0.0"
PORT = 5000

class TimingGateApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Timing Gate Monitor")
        
        self.arm_gate = False
        self.data_log = []
        self.conn = None
        self.server_socket = None
        self.listener_thread = None
        self.listening = False
        
        # GUI setup
        self.text_area = scrolledtext.ScrolledText(root, width=60, height=20, state='disabled')
        self.text_area.grid(row=0, column=0, columnspan=4, padx=10, pady=10)
        
        self.arm_btn = tk.Button(root, text="Arm", command=self.arm)
        self.arm_btn.grid(row=1, column=0, padx=5, pady=5)
        
        self.disarm_btn = tk.Button(root, text="Disarm", command=self.disarm)
        self.disarm_btn.grid(row=1, column=1, padx=5, pady=5)
        
        self.marker_btn = tk.Button(root, text="Add Marker", command=self.add_marker)
        self.marker_btn.grid(row=1, column=2, padx=5, pady=5)
        
        self.save_btn = tk.Button(root, text="Save Log", command=self.save_to_csv)
        self.save_btn.grid(row=1, column=3, padx=5, pady=5)
        
        self.reset_btn = tk.Button(root, text="Reset Connection", command=self.reset_connection)
        self.reset_btn.grid(row=2, column=0, columnspan=4, pady=5)
        
        self.start_listening()

    def log(self, message):
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, f"{datetime.utcnow()} - {message}\n")
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

    def arm(self):
        self.arm_gate = True
        self.log("Gate armed.")

    def disarm(self):
        self.arm_gate = False
        self.log("Gate disarmed.")

    def add_marker(self):
        text = simpledialog.askstring("Add Marker", "Enter marker text:")
        if text:
            self.data_log.append([datetime.utcnow(), "Marker", text])
            self.log(f"Marker added: {text}")

    def save_to_csv(self):
        if not self.data_log:
            messagebox.showinfo("Save Log", "No data to save.")
            return
        df = pd.DataFrame(self.data_log, columns=["Timestamp", "Event", "Details"])
        filename = f"timing_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False)
        self.log(f"Saved {len(self.data_log)} events to {filename}")

    def reset_connection(self):
        self.log("Resetting connection...")
        self.stop_listening()
        self.start_listening()

    def stop_listening(self):
        self.listening = False
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        if self.listener_thread:
            self.listener_thread.join(timeout=1)
            self.listener_thread = None
        self.log("Connection stopped.")

    def start_listening(self):
        self.listening = True
        self.listener_thread = threading.Thread(target=self.listen_to_gate, daemon=True)
        self.listener_thread.start()
        self.log(f"Listening on {HOST}:{PORT}...")

    def listen_to_gate(self):
        while self.listening:
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server_socket.bind((HOST, PORT))
                self.server_socket.listen(1)
                self.log("Waiting for connection...")
                self.conn, addr = self.server_socket.accept()
                self.log(f"Connected by {addr}")

                while self.listening:
                    data = self.conn.recv(1024)
                    if not data:
                        self.log("Connection lost.")
                        break
                    decoded = data.decode().strip()
                    if self.arm_gate:
                        self.log(f"Gate Trigger: {decoded}")
                        self.data_log.append([datetime.utcnow(), "Gate Trigger", decoded])
                    else:
                        self.log(f"Ignored (disarmed): {decoded}")

                self.conn.close()
                self.conn = None
                self.server_socket.close()
                self.server_socket = None
            except Exception as e:
                self.log(f"Error: {e}")
            if self.listening:
                self.log("Reconnecting in 3 seconds...")
                threading.Event().wait(3)  # Wait 3 seconds before retry

if __name__ == "__main__":
    root = tk.Tk()
    app = TimingGateApp(root)
    root.mainloop()
