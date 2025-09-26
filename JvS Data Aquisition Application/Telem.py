from dataclasses import make_dataclass
import threading, socket, sys, csv
from datetime import datetime, UTC
import time
from typing import Optional
from Loggers import *

class Device:
    def __init__(self, ip, dev_type, heartbeat_interval=1.0):
        self.ip = ip
        self.dev_type = dev_type
        self.last_rx_time = None
        self.heartbeat_interval = heartbeat_interval
        self.connected = True

    def update_heartbeat(self, ip=None):
        """Update heartbeat time and optionally IP for UDP device."""
        self.last_rx_time = time.time()
        if ip is not None:
            self.ip = ip  # Update IP for UDP device

    def get_status(self):
        if not self.connected:
            return "DOWN"
        if self.last_rx_time is None:
            return "DEGRADED"
        age = time.time() - self.last_rx_time
        if age < self.heartbeat_interval * 1.2:
            return "UP"
        elif age < self.heartbeat_interval * 3:
            return "DEGRADED"
        else:
            return "DOWN"


# ======================================================
# CONTROLLER: All logic, networking, state
# ======================================================
class TelemetryController:
    def __init__(self, gui_queue, root, config_file="can_config.csv"):
        self.gui_queue = gui_queue
        self.root = root
        self.running = True
        self.arm_gate = False
        self.latest_telem_data = None
        self.data_log = []
        self.timing_log = []
        self.flag_state = "Green"

        self.devices = {}
        self.lock = threading.Lock()
        self.logging = False
        self.logger = SessionLogger()

        # Config
        self.HOST = "0.0.0.0"
        self.GATE_PORT = 5000
        self.UDP_PORT = 5002

        # Load CAN config
        self.signal_names = self.load_config_signals(config_file)
        self.CanRow = self.make_can_row_class(self.signal_names)

        header = ["UTC", "Elapsed_Time"]
        self.telem_logger = BufferedLogger("Telemetry.csv", self.signal_names, buffer_size=100)
        self.timing_logger = BufferedLogger("Timing.csv", header, buffer_size=10)


    # ------------------------------
    # Config parsing
    # ------------------------------
    def load_config_signals(self, config_file: str) -> list[str]:
        """Load signal names from CSV config, or fall back to defaults."""
        try:
            with open(config_file, newline="") as f:
                reader = csv.DictReader(f)
                return [row["Name"] for row in reader]
        except FileNotFoundError:
            print(f"Config file {config_file} not found. Using defaults.")
            return [
                "timestamp", "RPM", "MPH", "Gear", "STR", "TPS",
                "CLT1", "CLT2", "OilTemp", "MAP", "MAT", "FuelPres",
                "OilPres", "AFR", "BatV", "AccelZ", "AccelX", "AccelY"
            ]
    
    def make_can_row_class(self, signal_names: list[str]):
        """Build a dataclass dynamically from signal names."""
        fields = [(name, float) for name in signal_names]
        return make_dataclass("CanRow", fields)
    
    def make_can_classes(self, signal_names: list[str], extra_fields: list[tuple[str, type]]):
        # Raw class
        RawCanRow = make_dataclass("RawCanRow", [(name, float) for name in signal_names])

        # Augmented class inherits RawCanRow and adds new fields
        AugmentedCanRow = make_dataclass(
            "AugmentedCanRow",
            fields=extra_fields,
            bases=(RawCanRow,)
        )

        return RawCanRow, AugmentedCanRow
    
    def parse_row(self, line: str):
        """Parse one line of CSV into a CanRow dataclass instance."""
        try:
            parts = line.strip().split(",")[1:]
            if len(parts) != len(self.signal_names):
                raise ValueError(f"Expected {len(self.signal_names)} values, got {len(parts)}")
    
            # Convert values safely
            values = {}
            for name, raw in zip(self.signal_names, parts):
                if raw in ("NaN", "nan", ""):
                    values[name] = float("nan")
                else:
                    values[name] = float(raw)
    
            # Example normalization (Accel signals)
            for key in ("AccelZ", "AccelX", "AccelY"):
                if key in values:
                    values[key] /= 2048.0
    
            return self.CanRow(**values)
    
        except Exception as e:
            print("Parse error:", e, "for line:", line)
            return None
        
    def calc_math_fields(self):
        return None

    # ------------------------------
    # Gate Controls
    # ------------------------------
    def arm(self):
        self.arm_gate = True
        self.log("Gate Armed")
    def disarm(self):
        self.arm_gate = False
        self.log("Gate Disarmed")
    def add_marker(self, text: str):
        if text:
            self.logger.log_event({"type": "MARKER", "value": text})
            self.log(f"Marker added: {text}")
    def log_cone(self):
        self.logger.log_event({"type": "CONE", "value": "1"})
        self.log("Cone Hit")
    def log_off_track(self):
        self.logger.log_event({"type": "OFF_TRACK", "value": "1"})
        self.log("Off track")
    def change_flag(self, flag):
        self.flag_state = flag
        self.logger.log_event({"type": "FLAG", "value": flag})
        self.gui_queue.put(("flag", self.flag_state))
        #self.send_flag()
    def start_logging(self):
        self.logger.start_session(notes="")
        self.logging=True
    def stop_logging(self):
        self.logger.stop_session()
        self.logging=False

    # ------------------------------
    # Logging & Queue
    # ------------------------------
    def log(self, message):
        if self.running:
            self.gui_queue.put(("log", message))

    def stop(self):
        self.running = False
        self.log("Exiting app...")
        self.telem_logger.close()
        self.timing_logger.close()
        # root.destroy() will be called by main thread via WM_DELETE_WINDOW binding
        self.root.after(0, self.root.destroy)
        sys.exit(0)

    def decode_trigger_message(self, msg):
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
    
    def handle_timing(self, data):
        decoded_data: Optional[dict] = self.decode_trigger_message(data)
        now = datetime.now(UTC).strftime('%H:%M:%S.%f')[:-3]

        if self.arm_gate and decoded_data is not None:
            #utc_time = decoded2.get('utc_time')
            trigger = float(decoded_data.get('trigger', 0.0))
            self.logger.log_event({"type": "GATE_TRIGGER", "value": trigger})
            self.timing_log.append(trigger)
            vals = self.timing_log
            row = {
                "LastTime": vals[-1] if vals else 0,
                "BestTime": min(vals) if vals else 0,
                "AvgTime": sum(vals) / len(vals) if vals else 0,
                "DeltaTime": (vals[-1] - vals[-2]) if len(vals) >= 2 else 0
            }
            self.gui_queue.put(("time_data", row))

    # ------------------------------
    # Networking
    # ------------------------------
    def register_device(self, ip, dev_type):
        with self.lock:
            if ip not in self.devices:
                dev = Device(ip, dev_type)
                self.devices[ip] = dev
                self.log(f"Registered device {ip} ({dev_type})")
            else:
                # Device already exists; just update IP if needed
                self.devices[ip].ip = ip

    def remove_device(self, ip):
        with self.lock:
            if ip in self.devices:
                self.devices[ip].connected = False
                self.log(f"Device {ip} disconnected")

    def update_heartbeat(self, ip, new_ip=None):
        """Update heartbeat; optionally update IP for UDP device."""
        with self.lock:
            if ip in self.devices:
                self.devices[ip].update_heartbeat(new_ip)

    def all_statuses(self):
        with self.lock:
            return {ip: dev.get_status() for ip, dev in self.devices.items()}

    def gate_client_handler(self, conn, addr):
        ip = addr[0]
        dev_type = "timing"  # Could be identified by first message
        self.register_device(ip, dev_type)
    
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    self.log("[TCP] Connection closed")
                    break
                decoded = data.decode(errors='ignore')
                parsed = decoded.strip().split(",")
                if parsed[0] == "0":
                    self.update_heartbeat(ip, "timing")
                else:
                    self.handle_timing(decoded)
                    self.log(f"[TCP] {decoded}")
        except Exception as e:
            self.log(f"Connection error with {ip}: {e}")
        finally:
            conn.close()
            self.remove_device(ip)
    
    
    def start_gate_server(self, host="0.0.0.0", port=5000):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((host, port))
        server_socket.listen()
    
        self.log(f"Server listening on {host}:{port}")
    
        def accept_loop():
            while True:
                conn, addr = server_socket.accept()
                thread = threading.Thread(target=self.gate_client_handler, args=(conn, addr), daemon=True)
                thread.start()
    
        threading.Thread(target=accept_loop, daemon=True).start()

    def start_udp_listener(self, port=5002):
        udp_device_key = "ILTM"  # unique identifier for single UDP device
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        self.log(f"UDP listener running on port {port}")
    
        while True:
            data, addr = sock.recvfrom(1024)
            ip = addr[0]
            # Register/update the UDP device with the latest IP and heartbeat
            self.register_device(udp_device_key, "udp")

            line = data.decode(errors="ignore")
            parsed = line.strip().split(",")
            if parsed[0] == "0":
                self.update_heartbeat(udp_device_key, new_ip=ip)
            else:
                row = self.parse_row(line)
                if row:
                    self.latest_telem_data = row
                    self.gui_queue.put(("telem_data", row))
                    self.logger.log_telemetry(row)
                    #print(row)
    
    def start_listeners(self):
        self.start_gate_server()
        threading.Thread(target=self.start_udp_listener, daemon=True).start()
