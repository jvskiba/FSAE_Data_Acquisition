import threading, socket, sys, csv, time
from dataclasses import dataclass, make_dataclass
from datetime import datetime, UTC
from typing import Optional
from Loggers import *  #SessionLogger, BufferedLogger
from LoRa_Service import *
import serial
import math
from collections import deque

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
@dataclass
class SignalValue:
    value: float
    mono_ts: float

class SignalDict(dict):
    def __init__(self, values, meta):
        super().__init__(values)
        self._meta = meta

    def age(self, name: str):
        sig = self._meta.get(name)
        if not sig:
            return None
        return time.monotonic() - sig


class SignalStore:
    def __init__(self):
        self._signals: dict[str, SignalValue] = {}

    def update(self, name: str, value: float):
        self._signals[name] = SignalValue(
            value=value,
            mono_ts=time.monotonic()
        )

    def get(self, name: str, max_age: float | None = None):
        sig = self._signals.get(name)
        if not sig:
            return None
        if max_age is not None and False:
            return None
        return sig.value
    
    def snapshot_values(self, max_age: float | None = None) -> dict[str, float]:
        """Return a dict suitable for GUI/logging."""
        now = time.monotonic()
        out = {}

        for name, sig in self._signals.items():
            if max_age is not None and (now - sig.mono_ts > max_age):
                out[name] = float("nan")
            else:
                out[name] = sig.value

        return out
    
    def snapshot_meta(self, max_age: float | None = None) -> dict[str, float]:
        """Return a dict suitable for GUI/logging."""
        now = time.monotonic()
        out = {}

        for name, sig in self._signals.items():
            out[name] = sig.mono_ts

        return out

    def get_latest_telem(self):
        values = self.snapshot_values()
        meta   = self.snapshot_meta()

        return SignalDict(values, meta)
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

        # Layers
        self.devices = DeviceRegistry()
        self.logger = SessionLogger()
        self.signals = SignalStore()

        # Ports
        self.HOST = "0.0.0.0"
        self.TCP_PORT = 5000
        self.UDP_PORT = 5002
        self.DISCOVERY_PORT = 4999

        self.tx_queue = deque()
        self.tx_busy = False
        self.last_tx_time = 0
        self.lastRxTime = 0
        self.TX_GUARD = 0.05  # seconds
        self.RX_GUARD = 0.01  # seconds

    def log(self, message: str):
        self.gui_queue.put(("log", message))

    # ------------------------------
    # Gate controls
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
        self.logger.start_session(telem_cols=self.signal_names, notes="") #TODO: Fix logging
        self.logging=True
    def stop_logging(self):
        self.logger.stop_session()
        self.logging=False
    def send_cmd(self, cmd):
        resp = b""
        resp += tlv_u8(0x01, cmd)
        self.queue_send(resp)

    # ------------------------------
    # Device handlers
    # ------------------------------
    def handle_command(self, device_id, payload):
        # Example: payload=["RESET"]
        cmd = payload[0].upper() if payload else None
        if cmd == "RESET":
            self.logger.log_event({"type": "COMMAND", "value": "RESET"})
        elif cmd == "PING":
            self.logger.log_event({"type": "COMMAND", "value": "PING"})

    def stop(self):
        self.running = False
        self.log("Exiting app...")
        #self.telem_logger.close()
        #self.timing_logger.close()
        # root.destroy() will be called by main thread via WM_DELETE_WINDOW binding
        self.root.after(0, self.root.destroy)
        sys.exit(0)

    # ------------------------------
    # TCP Handler (Heartbeat + Commands)
    # ------------------------------
    def tcp_client_handler(self, conn, addr):
        ip = addr[0]
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    self.log(f"[TCP] {ip} connection closed")
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
                    # TODO: FIX ALL THIS
                    print("UHHHHHH this is unexpected")
                    #self.handle_data(device_id, payload)
                elif channel == "CMD":
                    self.handle_command(device_id, payload)

                self.log(f"[TCP] {device_id}: {channel} {payload}")

        except Exception as e:
            self.log(f"[TCP] Connection error with {ip}: {e}")
        finally:
            conn.close()
            self.devices.remove_device(device_id)

    def start_tcp_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.HOST, self.TCP_PORT))
        server_socket.listen()
        self.log(f"TCP Server listening on {self.HOST}:{self.TCP_PORT}")

        def accept_loop():
            while True:
                conn, addr = server_socket.accept()
                threading.Thread(target=self.tcp_client_handler, args=(conn, addr), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()

    # ------------------------------
    # UDP Discovery Listener
    # ------------------------------
    def start_discovery_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.HOST, self.DISCOVERY_PORT))
        self.log(f"Discovery Listener running on UDP port {self.DISCOVERY_PORT}")

        while True:
            data, addr = sock.recvfrom(1024)
            msg = data.decode(errors="ignore").strip()
            if msg == "DISCOVER_SERVER":
                response = f"SERVER,{self.TCP_PORT},{self.UDP_PORT}"
                sock.sendto(response.encode(), addr)
                self.log(f"[DISCOVERY] Replied to {addr} with {response}")

    def send_at(self, cmd):
        self.ser.write((cmd + "\r\n").encode())
        time.sleep(0.05)
        raw = self.ser.read_all()
        resp = raw.decode(errors="ignore").strip() if raw else ""

        if debug:
            print(">>", cmd)
            print("<<", resp)
        return resp

    def queue_send(self, payload_bytes):
        hex_out = payload_bytes.hex().upper()
        self.tx_queue.append((payload_bytes, hex_out))

    def process_tx(self):
        now = time.time()

        # Clear busy by time
        if self.tx_busy and (now - self.last_tx_time) > self.TX_GUARD:
            self.tx_busy = False

        if now - self.lastRxTime < self.RX_GUARD:
            return
        
        if self.tx_busy or not self.tx_queue:
            return

        payload, hex_out = self.tx_queue.popleft()

        cmd = f"AT+SEND=1,{len(payload)*2},{hex_out}"
        self.ser.write((cmd + "\r\n").encode())

        if debug:
            print(">>", cmd)

        self.tx_busy = True
        self.last_tx_time = now

    def tlv_to_signal_store(self, tlv_vals: dict): #TODO: Probably a bad name
        for sig_id, raw_val in tlv_vals.items():
            name = id_to_name.get(sig_id)
            if not name:
                # TODO: REQUEST NAME FROM SENDER!!
                continue

            try:
                val = float(raw_val)
            except (TypeError, ValueError):
                val = float("nan")

            # normalize accel signals
            if name in ("AccelZ", "AccelX", "AccelY") and not math.isnan(val):
                val /= 2048.0

            self.signals.update(name, val)

    # ITV command IDs
    CMD_SYNC_REQ  = 0x01
    CMD_SYNC_RESP = 0x02
    CMD_NAME_SYNC_REQ = 0x03
    CMD_CONFIG_RESP = 0x04

    COMMAND_IDS = {
        CMD_SYNC_REQ,
        CMD_SYNC_RESP,
        CMD_NAME_SYNC_REQ,
        CMD_CONFIG_RESP,
    }

    def build_ntp_sync_response(self, vals):
        req_id = vals.get(0x02, 0)
        t1     = vals.get(0x03, 0)

        t2 = now_us()
        t3 = now_us()

        resp = b""
        resp += tlv_u8(0x01, self.CMD_SYNC_RESP)
        resp += tlv_u16(0x02, req_id)
        resp += tlv_u64(0x03, t1)
        resp += tlv_u64(0x04, t2)
        resp += tlv_u64(0x05, t3)

        return resp

    def handle_sync_request(self, tlv_vals):
        print("⏱ Sync request received")
        resp = self.build_ntp_sync_response(tlv_vals)
        self.queue_send(resp)

    COMMAND_HANDLERS = {
        CMD_SYNC_REQ: handle_sync_request
    }

    def filter_and_handle_commands(self, tlv_vals: dict) -> dict:
        """
        Handles command TLVs in-place.
        Returns telemetry-only TLVs.
        """

        remaining = {}

        for tid, value in tlv_vals.items():
            if tid == 0x01:
                handler = self.COMMAND_HANDLERS.get(value)
                if handler:
                    handler(self, tlv_vals)
                    break # SKIPS SENDING NTP TO GUI, ================== Could Cause Forces command to consume line
                else:
                    print(f"⚠ Unhandled command ID 0x{tid:02X}")
            else:
                remaining[tid] = value

        return remaining


    def start_LoRa_listener(self):
        self.log("Starting LoRa Service")
        try:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.1)
            time.sleep(1)

            self.send_at("AT+ADDRESS=2")
            self.send_at("AT+NETWORKID=18")
            self.send_at("AT+BAND=915000000")
            self.send_at("AT+PARAMETER=7,9,1,8")

            print("Listening on", PORT)
        except:
            print("Plug the LoRa Device in Bruh")
            return

        cmd = tlv_cmd(0x01, self.CMD_NAME_SYNC_REQ)
        self.queue_send(cmd)

        while True:
            try:
                #Send Response
                self.process_tx()

                line_in = self.ser.readline().decode(errors='ignore').strip()
                if not line_in:
                    continue

                #Error Handling

                if debug: print(line_in)

                if line_in.startswith("+ERR=5"):
                    # radio still busy — just wait
                    self.tx_busy = True
                    continue

                elif line_in.startswith("+ERR="):
                    print("LoRa error:", line_in)
                    self.tx_busy = False
                    continue

                elif not line_in.startswith("+RCV="):
                    continue

                # Data/Command Handling

                parts = line_in.split(",")
                if len(parts) < 5:
                    continue

                self.lastRxTime = time.time()
                payload_hex = parts[2]
                
                self.signals.update("RSSI", float(parts[3]))
                self.signals.update("SNR", float(parts[4]))
                self.signals.update("TIME_RX", now_us())

                # 🔹 Decode TLV
                tlv_vals = decode_value_tlv(payload_hex)

                # 🔹 Handle commands & filter telemetry
                if not tlv_vals:
                    print("⚠ TLV decode failed")
                    continue
                tlv_vals = self.filter_and_handle_commands(tlv_vals)

                # 🔹 Print decoded values
                if debug: 
                    for id, v in tlv_vals.items():
                        name = id_to_name.get(id, f"ID{id}")
                        print(f"{name}: {v}")

                self.devices.register_device(0, "udp_device", channel="udp", ip=0)
                # 🔹 Convert to CanRow
                if len(tlv_vals) == 0:
                    continue

                self.tlv_to_signal_store(tlv_vals)

                self.gui_queue.put(("telem_data", self.signals.get_latest_telem()))

                #self.telem_logger.log_frame(snapshot)

            except KeyboardInterrupt:
                break

    # ------------------------------
    # Start all listeners
    # ------------------------------
    def start_listeners(self):
        self.start_tcp_server()
        #threading.Thread(target=self.start_udp_listener, daemon=True).start()
        threading.Thread(target=self.start_discovery_listener, daemon=True).start()
        threading.Thread(target=self.start_LoRa_listener, daemon=True).start()
        