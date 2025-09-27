import threading, socket, sys, csv, time
from dataclasses import make_dataclass
from datetime import datetime, UTC
from typing import Optional
from Loggers import *  # Assuming you already have SessionLogger, BufferedLogger

# ==============================
# Device Layer
# ==============================
class Device:
    def __init__(self, device_id: str, dev_type: str, heartbeat_interval=1.0):
        self.device_id = device_id
        self.dev_type = dev_type
        self.heartbeat_interval = heartbeat_interval
        self.last_rx_time = None
        self.connected = True
        self.channels = {}  # "tcp": socket, "udp": ip

    def update_heartbeat(self, ip=None):
        self.last_rx_time = time.time()
        if ip:
            self.channels["udp"] = ip

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

class DeviceRegistry:
    """Thread-safe registry for all devices."""
    def __init__(self):
        self.devices: dict[str, Device] = {}
        self.lock = threading.Lock()

    def register_device(self, device_id, dev_type, channel=None, conn=None, ip=None):
        with self.lock:
            if device_id not in self.devices:
                dev = Device(device_id, dev_type)
                self.devices[device_id] = dev
            else:
                dev = self.devices[device_id]
                dev.connected = True
            # Update channels
            if channel == "tcp" and conn:
                dev.channels["tcp"] = conn
            elif channel == "udp" and ip:
                dev.channels["udp"] = ip
            return dev

    def remove_device(self, device_id):
        with self.lock:
            if device_id in self.devices:
                self.devices[device_id].connected = False

    def update_heartbeat(self, device_id, ip=None):
        with self.lock:
            if device_id in self.devices:
                self.devices[device_id].update_heartbeat(ip)

    def all_statuses(self):
        with self.lock:
            return {id: dev.get_status() for id, dev in self.devices.items()}

# ==============================
# Parser Layer
# ==============================
class CanParser:
    def __init__(self, signal_names):
        self.signal_names = signal_names
        self.CanRow = make_dataclass("CanRow", [(name, float) for name in signal_names])

    def parse_row(self, line: str):
        try:
            parts = line.strip().split(",")[1:]  # skip channel/device_id
            if len(parts) != len(self.signal_names):
                raise ValueError(f"Expected {len(self.signal_names)} values, got {len(parts)}")
            values = {}
            for name, raw in zip(self.signal_names, parts):
                if raw in ("NaN", "nan", ""):
                    values[name] = float("nan")
                else:
                    values[name] = float(raw)
            # normalize accel signals
            for key in ("AccelZ", "AccelX", "AccelY"):
                if key in values:
                    values[key] /= 2048.0
            return self.CanRow(**values)
        except Exception as e:
            print("Parse error:", e, "for line:", line)
            return None

class TriggerParser:
    """Parse gate trigger messages"""
    def decode_trigger_message(self, msg: str):
        try:
            parts = [p.strip() for p in msg.split(",")]
            data = {}
            i = 0
            while i < len(parts):
                label = parts[i].upper()
                if label == "TIME (UTC)" and i + 1 < len(parts):
                    time_str = parts[i + 1]
                    try:
                        utc_time = datetime.strptime(time_str, "%H:%M:%S.%f")
                    except ValueError:
                        utc_time = datetime.strptime(time_str, "%H:%M:%S")
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

# ==============================
# Logger Layer
# ==============================
class LoggerWrapper:
    def __init__(self, gui_queue):
        self.gui_queue = gui_queue
        self.session_logger = SessionLogger()

    def log_event(self, device_id, event: dict):
        self.session_logger.log_event(event)
        self.gui_queue.put(("log", f"{device_id}: {event}"))

    def log(self, message: str):
        self.gui_queue.put(("log", message))

# ==============================
# Controller / Networking
# ==============================
class TelemetryController:
    def __init__(self, gui_queue, root, config_file="can_config.csv"):
        self.gui_queue = gui_queue
        self.root = root
        self.running = True
        self.arm_gate = False
        self.flag_state = "Green"
        self.latest_telem_data = None

        # Layers
        self.devices = DeviceRegistry()
        self.logger = LoggerWrapper(gui_queue)
        self.can_parser = CanParser(self.load_config_signals(config_file))
        self.trigger_parser = TriggerParser()

        # Ports
        self.HOST = "0.0.0.0"
        self.TCP_PORT = 5000
        self.UDP_PORT = 5002
        self.DISCOVERY_PORT = 4999

        # Logging
        self.telem_logger = BufferedLogger("Telemetry.csv", self.can_parser.signal_names, buffer_size=100)
        self.timing_logger = BufferedLogger("Timing.csv", ["UTC", "Elapsed_Time"], buffer_size=10)

    # ------------------------------
    # Config parsing
    # ------------------------------
    def load_config_signals(self, config_file: str) -> list[str]:
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

    # ------------------------------
    # Gate controls
    # ------------------------------
    def arm(self):
        self.arm_gate = True
        self.logger.log("Gate Armed")

    def disarm(self):
        self.arm_gate = False
        self.logger.log("Gate Disarmed")

    # ------------------------------
    # Device handlers
    # ------------------------------
    def handle_data(self, device_id, payload):
        # payload is list of strings
        line = ",".join(payload)
        row = self.can_parser.parse_row(line)
        if row:
            self.latest_telem_data = row
            self.gui_queue.put(("telem_data", row))
            self.telem_logger.log_frame(row)

    def handle_command(self, device_id, payload):
        # Example: payload=["RESET"]
        cmd = payload[0].upper() if payload else None
        if cmd == "RESET":
            self.logger.log_event(device_id, {"type": "COMMAND", "value": "RESET"})
        elif cmd == "PING":
            self.logger.log_event(device_id, {"type": "COMMAND", "value": "PING"})

    # ------------------------------
    # TCP Handler (Heartbeat + Commands)
    # ------------------------------
    def tcp_client_handler(self, conn, addr):
        ip = addr[0]
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    self.logger.log(f"[TCP] {ip} connection closed")
                    break

                line = data.decode(errors="ignore").strip()
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                channel, device_id = parts[0], parts[1]
                payload = parts[2:] if len(parts) > 2 else []

                self.devices.register_device(device_id, "tcp_device", channel="tcp", conn=conn, ip=ip)

                if channel == "HB":
                    self.devices.update_heartbeat(device_id, ip)
                elif channel == "DATA":
                    self.handle_data(device_id, payload)
                elif channel == "CMD":
                    self.handle_command(device_id, payload)

                self.logger.log(f"[TCP] {device_id}: {channel} {payload}")

        except Exception as e:
            self.logger.log(f"[TCP] Connection error with {ip}: {e}")
        finally:
            conn.close()
            self.devices.remove_device(device_id)

    def start_tcp_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.HOST, self.TCP_PORT))
        server_socket.listen()
        self.logger.log(f"TCP Server listening on {self.HOST}:{self.TCP_PORT}")

        def accept_loop():
            while True:
                conn, addr = server_socket.accept()
                threading.Thread(target=self.tcp_client_handler, args=(conn, addr), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()

    # ------------------------------
    # UDP Handler (Telemetry + Heartbeat)
    # ------------------------------
    def start_udp_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.HOST, self.UDP_PORT))
        self.logger.log(f"UDP Listener running on {self.UDP_PORT}")

        while True:
            data, addr = sock.recvfrom(1024)
            ip = addr[0]
            line = data.decode(errors="ignore").strip()
            parts = line.split(",")
            if len(parts) < 2:
                continue
            channel, device_id = parts[0], parts[1]
            payload = parts[2:] if len(parts) > 2 else []

            self.devices.register_device(device_id, "udp_device", channel="udp", ip=ip)

            if channel == "HB":
                self.devices.update_heartbeat(device_id, ip)
            elif channel == "DATA":
                self.handle_data(device_id, payload)

            self.logger.log(f"[UDP] {device_id}: {channel} {payload}")

    # ------------------------------
    # UDP Discovery Listener
    # ------------------------------
    def start_discovery_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.HOST, self.DISCOVERY_PORT))
        self.logger.log(f"Discovery Listener running on UDP port {self.DISCOVERY_PORT}")

        while True:
            data, addr = sock.recvfrom(1024)
            msg = data.decode(errors="ignore").strip()
            if msg == "DISCOVER_SERVER":
                response = f"SERVER,{self.TCP_PORT},{self.UDP_PORT}"
                sock.sendto(response.encode(), addr)
                self.logger.log(f"[DISCOVERY] Replied to {addr} with {response}")

    # ------------------------------
    # Start all listeners
    # ------------------------------
    def start_listeners(self):
        self.start_tcp_server()
        threading.Thread(target=self.start_udp_listener, daemon=True).start()
        threading.Thread(target=self.start_discovery_listener, daemon=True).start()
