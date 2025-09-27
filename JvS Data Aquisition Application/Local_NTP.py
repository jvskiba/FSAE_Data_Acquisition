"""
Transport-agnostic NTP-like sync (Python)
Author: ChatGPT (adapted for your project)
Works with: any Transport implementing send(dst, bytes) and recv() -> (bytes, src)
Timestamps are in integer nanoseconds from time.perf_counter_ns()
"""

import time
import json
import threading
import statistics
from typing import Tuple, Optional, Dict, Any, Callable
import queue
import random
import socket

# ------------------------
# Utility helpers
# ------------------------
def now_ns() -> int:
    """High-resolution monotonic timestamp in nanoseconds."""
    return time.perf_counter_ns()

def ns_to_s(ns: int) -> float:
    return ns / 1e9

# NTP-like math:
# T1 = client send (client time)
# T2 = server receive (server time)
# T3 = server send (server time)
# T4 = client receive (client time)
# offset = ((T2 - T1) + (T3 - T4)) / 2
# delay  = (T4 - T1) - (T3 - T2)

def compute_offset_delay(t1: int, t2: int, t3: int, t4: int) -> Tuple[float, float]:
    """Return (offset_seconds, delay_seconds)."""
    offset_ns = ((t2 - t1) + (t3 - t4)) // 2
    delay_ns = (t4 - t1) - (t3 - t2)
    return offset_ns / 1e9, delay_ns / 1e9

# ------------------------
# Transport interface
# ------------------------
class Transport:
    """
    Minimal transport interface.
    send(dst, data_bytes) -> None
    recv(timeout=None) -> (data_bytes, src)
    Implementations can be blocking or non-blocking.
    """
    def send(self, dst: Any, data: bytes) -> None:
        raise NotImplementedError

    def recv(self, timeout: Optional[float] = None) -> Tuple[bytes, Any]:
        raise NotImplementedError

# ------------------------
# In-process simulated network (for testing)
# ------------------------
class SimulatedNetwork:
    """
    Simulates a simple in-process network connecting named endpoints.
    Provides one-way delays (can be asymmetric) and jitter.
    Usage:
        net = SimulatedNetwork()
        net.register('client')
        net.register('server')
        client_transport = net.transport_for('client')
        server_transport = net.transport_for('server')
    """
    def __init__(self, seed: Optional[int] = None):
        self.queues = {}  # endpoint -> queue of (deliver_at_time, data, src, dst)
        self.lock = threading.Lock()
        self.running = True
        self.background = threading.Thread(target=self._deliver_loop, daemon=True)
        self.background.start()
        if seed is not None:
            random.seed(seed)

        # default baseline delays (ns)
        self.default_delay_ns = 0
        self.per_link_delay = {}  # (src, dst) -> (base_ns, jitter_ns)

    def register(self, name: str):
        with self.lock:
            self.queues[name] = queue.PriorityQueue()

    def transport_for(self, name: str):
        return _SimTransport(self, name)

    def set_link_delay(self, src: str, dst: str, base_delay_s: float, jitter_s: float = 0.0):
        self.per_link_delay[(src, dst)] = (int(base_delay_s * 1e9), int(jitter_s * 1e9))

    def send(self, src: str, dst: str, data: bytes):
        # compute delay
        base_ns, jitter_ns = self.per_link_delay.get((src, dst), (self.default_delay_ns, 0))
        jitter = random.randint(-jitter_ns, jitter_ns) if jitter_ns > 0 else 0
        delay_ns = max(0, base_ns + jitter)
        deliver_at = now_ns() + delay_ns
        with self.lock:
            if dst not in self.queues:
                raise KeyError(f"Destination {dst} not registered in simulated network")
            self.queues[dst].put((deliver_at, data, src, dst))

    def _deliver_loop(self):
        while self.running:
            with self.lock:
                for name, q in list(self.queues.items()):
                    try:
                        while not q.empty():
                            deliver_at, data, src, dst = q.queue[0]  # peek
                            if deliver_at <= now_ns():
                                q.get_nowait()
                                # put into a simple receive mailbox (another queue)
                                # We'll create a separate mailbox dict for immediate recv.
                                # For simplicity, put a small per-endpoint recv queue attribute
                                if not hasattr(self, "_mailboxes"):
                                    self._mailboxes = {}
                                self._mailboxes.setdefault(name, queue.Queue()).put((data, src))
                            else:
                                break
                    except Exception:
                        pass
            time.sleep(0.0005)

    def recv_mailbox(self, name: str, timeout: Optional[float] = None):
        if not hasattr(self, "_mailboxes"):
            self._mailboxes = {}
        mb = self._mailboxes.setdefault(name, queue.Queue())
        try:
            item = mb.get(timeout=timeout)
            return item  # (data, src)
        except queue.Empty:
            raise TimeoutError

    def shutdown(self):
        self.running = False
        self.background.join(timeout=0.5)

class _SimTransport(Transport):
    """Transport wrapper for an endpoint in SimulatedNetwork."""
    def __init__(self, net: SimulatedNetwork, name: str):
        self.net = net
        self.name = name

    def send(self, dst: str, data: bytes) -> None:
        self.net.send(self.name, dst, data)

    def recv(self, timeout: Optional[float] = None) -> Tuple[bytes, str]:
        try:
            data, src = self.net.recv_mailbox(self.name, timeout)
            return data, src
        except TimeoutError:
            raise TimeoutError

# ------------------------
# (Optional) UDP transport example
# ------------------------
class UDPTransport(Transport):
    def __init__(self, bind_addr: Tuple[str, int]):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind_addr)
        self.sock.settimeout(0.1)

    def send(self, dst: Tuple[str, int], data: bytes) -> None:
        self.sock.sendto(data, dst)

    def recv(self, timeout: Optional[float] = None) -> Tuple[bytes, Tuple[str, int]]:
        old = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            data, addr = self.sock.recvfrom(4096)
            return data, addr
        finally:
            self.sock.settimeout(old)

# ------------------------
# Protocol messages (JSON)
# ------------------------
def pack_msg(obj: Dict) -> bytes:
    return json.dumps(obj).encode()

def unpack_msg(b: bytes) -> Dict:
    return json.loads(b.decode())

# ------------------------
# Sync server & client
# ------------------------
class SyncServer:
    """
    Simple stateless sync server: when it receives a request with client's T1,
    it records T2 (receive), prepares a response with T1, T2, T3 (send).
    The server must timestamp at receive and right before send with its local clock.
    """
    REQ = "SYNC_REQ"
    RESP = "SYNC_RESP"

    def __init__(self, transport: Transport, name: Any):
        self.transport = transport
        self.name = name  # how the transport addresses this server (used by SimulatedNetwork)

    def serve_once(self, timeout: Optional[float] = None):
        # blocking receive
        data, src = self.transport.recv(timeout=timeout)
        t2 = now_ns()
        msg = unpack_msg(data)
        if msg.get("type") != self.REQ:
            return  # ignore
        t1 = int(msg["t1"])
        # prepare response; record send time right before sending
        resp = {"type": self.RESP, "t1": t1, "t2": t2, "t3": None}
        # wait a tiny bit to simulate server processing if you'd like (not necessary)
        t3 = now_ns()
        resp["t3"] = t3
        self.transport.send(src, pack_msg(resp))


class SyncClient:
    """
    Client that performs one exchange with a server and computes offset/delay.
    It is transport-agnostic: you pass in a transport and the server address (dst).
    """
    REQ = "SYNC_REQ"
    RESP = "SYNC_RESP"

    def __init__(self, transport: Transport, name: Any):
        self.transport = transport
        self.name = name

    def exchange_once(self, server_addr: Any, timeout: float = 1.0) -> Tuple[float, float, Dict]:
        """
        Perform one sync exchange. Returns (offset_s, delay_s, debug_dict)
        debug_dict contains raw T1..T4 as ints (ns) and src/dst info.
        """
        t1 = now_ns()
        req = {"type": self.REQ, "t1": t1}
        self.transport.send(server_addr, pack_msg(req))

        # wait for response
        data, src = self.transport.recv(timeout=timeout)
        t4 = now_ns()
        msg = unpack_msg(data)
        if msg.get("type") != self.RESP:
            raise RuntimeError("Unexpected message type")

        t2 = int(msg["t2"])
        t3 = int(msg["t3"])
        offset_s, delay_s = compute_offset_delay(t1, t2, t3, t4)
        debug = {"t1": t1, "t2": t2, "t3": t3, "t4": t4, "server": src}
        return offset_s, delay_s, debug

    def sync(self, server_addr: Any, exchanges: int = 11, timeout: float = 1.0):
        """
        Perform multiple exchanges and return a robust offset estimate.
        Returns dict containing: offset_s (median), delay_s (median), samples list.
        """
        samples = []
        for i in range(exchanges):
            try:
                off, d, dbg = self.exchange_once(server_addr, timeout=timeout)
                samples.append({"offset": off, "delay": d, "debug": dbg})
            except Exception as e:
                # ignore drops; continue
                samples.append({"offset": None, "delay": None, "error": str(e)})
            # small sleep to avoid sending bursts that might bias queue order
            time.sleep(0.01)

        # filter valid
        valid = [s for s in samples if s["offset"] is not None]
        if not valid:
            return {"offset": None, "delay": None, "samples": samples}
        offsets = [s["offset"] for s in valid]
        delays = [s["delay"] for s in valid]

        # Use median as robust estimator; you can use weighted or min-delay if desired.
        result = {
            "offset": statistics.median(offsets),
            "delay": statistics.median(delays),
            "samples": samples
        }
        return result

# ------------------------
# Example usage with simulation
# ------------------------
def example_simulation():
    # Create network and two endpoints
    net = SimulatedNetwork()
    net.register("client")
    net.register("server")

    # set asymmetric delays to simulate realistic conditions
    # from client -> server: 5 ms +/- 2 ms jitter
    net.set_link_delay("client", "server", base_delay_s=0.005, jitter_s=0.002)
    # from server -> client: 8 ms +/- 3 ms jitter
    net.set_link_delay("server", "client", base_delay_s=0.008, jitter_s=0.003)

    client_transport = net.transport_for("client")
    server_transport = net.transport_for("server")

    server = SyncServer(server_transport, name="server-name")
    client = SyncClient(client_transport, name="client-name")

    # run server loop in a background thread
    stop_flag = threading.Event()

    def server_loop():
        while not stop_flag.is_set():
            try:
                server.serve_once(timeout=0.2)
            except TimeoutError:
                continue

    srv_thread = threading.Thread(target=server_loop, daemon=True)
    srv_thread.start()

    # perform sync on client
    result = client.sync("server", exchanges=15)
    print("Sync result:", result["offset"], "s  delay:", result["delay"], "s")
    # Show sample debug
    for i, s in enumerate(result["samples"]):
        print(i, s)

    # cleanup
    stop_flag.set()
    net.shutdown()

if __name__ == "__main__":
    example_simulation()
