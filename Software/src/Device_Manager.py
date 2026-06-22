import threading, socket, sys, time
from dataclasses import dataclass
from Loggers import *  #SessionLogger, BufferedLogger
from LoRa_Service import *
import serial
from collections import deque
import asyncio
from aiohttp import web
import json
from ConfigManager import *
import queue

debug = False
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
    
    def timestamp(self, name: str):
        return self._meta.get(name)


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
    def __init__(self, gui_queue, root, config : Config):
        self.gui_queue = gui_queue
        self.root = root
        self.config = config
        self.running = True
        self.sigNamesRequested = True

        # Layers
        self.logger = SessionLogger()
        self.signals = SignalStore()
        self.server = TelemetryWebServer(self.signals)
        self.server.set_channel_meta(config.web_meta.widgets)

        # Ports
        self.HOST = config.main.host_ip
        self.TCP_PORT = config.main.tcp_port
        self.UDP_PORT = config.main.udp_port
        self.COM_PORT = config.main.lora_com_port
        self.BAUD = config.main.lora_baud

        self.tx_queue = deque()
        self.tx_busy = False
        self.last_tx_time = 0
        self.lastRxTime = 0
        self.TX_GUARD = 0.05  # seconds
        self.RX_GUARD = 0.01  # seconds

        self.command_queue = queue.Queue()

        threading.Thread(
            target=self.command_worker,
            daemon=True
        ).start()

    def log(self, message: str):
        self.gui_queue.put(("log", message))

    # ------------------------------
    # Gate controls
    # ------------------------------
    def add_marker(self, text: str):
        if text:
            self.logger.log_event({"type": "MARKER", "value": text})
            self.log(f"Marker added: {text}")

    def start_logging(self):
        #self.logger.start_session(telem_cols=self.signal_names, notes="") #TODO: Fix logging
        self.logging=True
    def stop_logging(self):
        self.logger.stop_session()
        self.logging=False
    def send_cmd(self, cmd, val=None):
        resp = b""
        resp += itv_u8(0x01, cmd)

        if val is not None:
            resp += itv_u8(0x02, int(val))  # or to_bytes(...)

        self.queue_send(resp)

    # ------------------------------
    # Device handlers
    # ------------------------------
    def stop(self):
        self.running = False
        self.log("Exiting app...")
        #self.telem_logger.close()
        #self.timing_logger.close()
        sys.exit(0)

    def start_udp_telem_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.HOST, self.UDP_PORT))
        self.log(f"UDP Telemetru Listener running on UDP port {self.UDP_PORT}")

        while True:
            data, addr = sock.recvfrom(1024)

            itv_vals = decode_value_itv(data)

            if not itv_vals:
                if debug:
                    print("Couldn't decode wifi ITV packet")
                continue

            # -----------------------------
            # Timestamp + fake radio stats
            # -----------------------------
            self.lastRxTime = time.time()
            self.signals.update("TIME_RX", now_us())

            # -----------------------------
            # Command handling
            # -----------------------------
            itv_vals = self.filter_and_handle_commands(itv_vals)

            if len(itv_vals) == 0:
                continue

            # -----------------------------
            # Debug print (clean)
            # -----------------------------
            if debug:
                for id, v in itv_vals.items():
                    name = id_to_name.get(id, f"ID{id}")
                    print(f"{name}: {v}")


            self.itv_to_signal_store(itv_vals)

            # -----------------------------
            # Push to GUI
            # -----------------------------
            self.gui_queue.put(
                ("telem_data", self.signals.get_latest_telem())
            )

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

        payload, _ = self.tx_queue.popleft()   # payload should already be bytes

        length = len(payload)

        if length > 66:
            print("⚠ Payload too large")
            return

        # Send: [LEN][PAYLOAD]
        packet = bytes([length]) + payload
        self.ser.write(packet)

        if debug:
            print(">> TX:", payload)

        self.tx_busy = True
        self.last_tx_time = now

    def itv_to_signal_store(self, itv_vals: dict):
        for sig_id, raw_val in itv_vals.items():
            name = id_to_name.get(sig_id)
            if not name and not self.sigNamesRequested:
                self.sigNamesRequested = True
                self.send_cmd(3)
                continue

            try:
                val = float(raw_val)
            except (TypeError, ValueError):
                val = float("nan")

            # normalize accel signals
            #if name in ("AccelZ", "AccelX", "AccelY") and not math.isnan(val):
                #val /= 2048.0
            if not name: 
                print("Missing Signal Name \n")
                return
            self.signals.update(name, val)

    # -------
    # Wifi Commands
    # -------

    def command_worker(self):
        while True:
            name, cmd = self.command_queue.get()

            try:
                self.send_command(name, cmd)
            except Exception as e:
                print(e)

            self.command_queue.task_done()

    def send_cmd_async(self, name, cmd):
        self.command_queue.put((name, cmd))

    def send_command(self, name, cmd):
        print(f"Sending command {name}")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.config.main.vehicle_ip, self.config.main.vehicle_port))

        packet = (
            itv_cmd(0x01, cmd.ID) +
            itv_u8(0x02, cmd.Data)
        )

        s.sendall(packet)
        print(s.recv(1024).decode())

        s.close()
        return

    # ITV command IDs
    CMD_SYNC_REQ  = 0x01
    CMD_SYNC_RESP = 0x02
    CMD_NAME_SYNC_REQ = 0x03

    COMMAND_IDS = {
        CMD_SYNC_REQ,
        CMD_SYNC_RESP,
        CMD_NAME_SYNC_REQ
    }

    def build_ntp_sync_response(self, vals):
        req_id = vals.get(0x02, 0)
        t1     = vals.get(0x03, 0)

        t2 = now_us()
        t3 = now_us()

        resp = b""
        resp += itv_u8(0x01, self.CMD_SYNC_RESP)
        resp += itv_u16(0x02, req_id)
        resp += itv_u64(0x03, t1)
        resp += itv_u64(0x04, t2)
        resp += itv_u64(0x05, t3)

        return resp

    def handle_sync_request(self, itv_vals):
        print("⏱ Sync request received")
        resp = self.build_ntp_sync_response(itv_vals)
        self.queue_send(resp)

    COMMAND_HANDLERS = {
        CMD_SYNC_REQ: handle_sync_request
    }

    def filter_and_handle_commands(self, itv_vals: dict) -> dict:
        """
        Handles command itvs in-place.
        Returns telemetry-only itvs.
        """

        remaining = {}

        for tid, value in itv_vals.items():
            if tid == 0x01:
                handler = self.COMMAND_HANDLERS.get(value)
                if handler:
                    handler(self, itv_vals)
                    break # SKIPS SENDING NTP TO GUI, ================== Could Cause Forces command to consume line
                else:
                    print(f"⚠ Unhandled command ID 0x{tid:02X}")
            else:
                remaining[tid] = value

        return remaining

    def start_LoRa_listener(self):
        self.log("Starting LoRa Service")

        try:
            self.ser = serial.Serial(self.COM_PORT, self.BAUD, timeout=0.1)
            time.sleep(.5)  # ESP32 reset delay
            self.log(f"Listening on {self.COM_PORT}")
        except:
            self.log("Plug the LoRa Device in Bruh")
            return

        while True:
            try:
                # -----------------------------
                # TX Handling
                # -----------------------------
                self.process_tx()

                # -----------------------------
                # RX Handling
                # -----------------------------
                
                # Step 1: Find start label "D:"
                data = self.read_packet();
                #print(data)
                # Step 4: Decode
                itv_vals = decode_value_itv(data)

                if not itv_vals:
                    if debug:
                        print("⚠ Empty or invalid Serial Line")
                    continue

                # -----------------------------
                # Command handling
                # -----------------------------
                itv_vals = self.filter_and_handle_commands(itv_vals)

                if len(itv_vals) == 0:
                    continue

                # -----------------------------
                # Debug print (clean)
                # -----------------------------
                if debug:
                    for id, v in itv_vals.items():
                        name = id_to_name.get(id, f"ID{id}")
                        print(f"{name}: {v}")

                # -----------------------------
                # Signal update
                # -----------------------------
                self.itv_to_signal_store(itv_vals)

                # -----------------------------
                # Push to GUI
                # -----------------------------
                self.gui_queue.put(
                    ("telem_data", self.signals.get_latest_telem())
                )

            except KeyboardInterrupt:
                break

            except Exception as e:
                print("Listener error:", e)

    def read_packet(self):
        # 1. sync to D:
        while True:
            if self.ser.read(1) == b'D':
                if self.ser.read(1) == b':':
                    break

        # 2. read length
        length_byte = self.ser.read(1)
        if not length_byte:
            return None

        length = length_byte[0]

        # 3. read EXACT payload
        data = bytearray()
        while len(data) < length:
            chunk = self.ser.read(length - len(data))
            if not chunk:
                return None
            data.extend(chunk)

        return data

    async def telemetry_loop(self):
        while True:
            data = self.signals.get_latest_telem()
            await self.server.broadcast(data)
            await asyncio.sleep(0.05)  # 20 Hz update rate

    def start_async_loop(self):
        hostname = socket.gethostname()
        IPAddr = socket.gethostbyname(hostname)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Start telemetry task
            loop.create_task(self.telemetry_loop())

            # Start web server in same loop
            web_runner = web.AppRunner(self.server.app)

            async def start_server():
                await web_runner.setup()
                site = web.TCPSite(web_runner, self.server.host, self.server.port)
                await site.start()
                print(f"Server running on http://{IPAddr}:{self.server.port}")

            loop.run_until_complete(start_server())

            # Run everything forever
            loop.run_forever()
        except Exception as e:
            print("ASYNC LOOP ERROR:", e)
    # ------------------------------
    # Start all listeners
    # ------------------------------
    def start_listeners(self):
        threading.Thread(target=self.start_LoRa_listener, daemon=True).start()
        threading.Thread(target=self.start_udp_telem_listener, daemon=True).start()
        threading.Thread(target=self.start_async_loop, daemon=True).start()

class TelemetryWebServer:
    def __init__(self, signal_store, host="0.0.0.0", port=8080):
        self.signal_store = signal_store
        self.host = host
        self.port = port
        self.channel_meta = {}

        self.app = web.Application()
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/ws", self.websocket_handler)

        self.clients = set()
        print("Telem WebSocket Initialized")

    def set_channel_meta(self, channel_meta):
        self.channel_meta = channel_meta

    # --------------------------
    # HTTP (serves your webpage)
    # --------------------------
    async def index(self, request):
        print("New Client")
        return web.FileResponse("index.html")

    # --------------------------
    # WebSocket handler
    # --------------------------
    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.clients.add(ws)

        await ws.send_json({
            "type": "meta",
            "channels": self.channel_meta
        })


        try:
            async for msg in ws:
                # You can handle incoming messages here if needed
                pass
        finally:
            self.clients.remove(ws)

        return ws

    # --------------------------
    # Broadcast telemetry
    # --------------------------
    async def broadcast(self, data: dict):
        if not self.clients:
            return

        dead_clients = []

        for ws in self.clients:
            if ws.closed:
                dead_clients.append(ws)
                continue

            await ws.send_json({
                    "type": "telemetry",
                    "channels": data
                })

        # Cleanup dead connections
        for ws in dead_clients:
            self.clients.discard(ws)

    # --------------------------
    # Start server
    # --------------------------
    def run(self):
        web.run_app(self.app, host=self.host, port=self.port)
        print(f"Server running on http://{self.host}:{self.port}")
        