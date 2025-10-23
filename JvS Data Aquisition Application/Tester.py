import socket
import time
import json

HOST = "0.0.0.0"
PORT = 5000

def now_ns():
    return time.time_ns()  # nanoseconds since Unix epoch (UTC)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"NTP server listening on {HOST}:{PORT}")

while True:
    data, addr = sock.recvfrom(1024)
    t2 = now_ns()  # time when packet received
    try:
        msg = json.loads(data.decode())
        if msg.get("type") == "SYNC_REQ":
            t1 = int(msg["t1"])  # client send time
            resp = {
                "type": "SYNC_RESP",
                "t1": t1,
                "t2": t2,
                "t3": now_ns(),  # server send time
            }
            sock.sendto(json.dumps(resp).encode(), addr)
            print(f"Responded to {addr}, Δt={(resp['t3'] - resp['t2'])/1e3:.1f} µs latency")
    except Exception as e:
        print("Bad packet:", e)
