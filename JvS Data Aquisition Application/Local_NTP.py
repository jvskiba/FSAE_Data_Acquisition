import socket 
import time 
import json 
HOST = "0.0.0.0" 
PORT = 5000 

#def now_us(): 
#    return round(time.time_ns() / 1000) # UTC nanoseconds (system clock) 
t0 = time.monotonic_ns()  # reference when server starts

def now_us():
    return (time.monotonic_ns() - t0) // 1000  # microseconds since server start

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
sock.bind((HOST, PORT)) 
print(f"NTP server listening on {HOST}:{PORT}") 
while True: 
    data, addr = sock.recvfrom(1024) 
    t2 = now_us() 
    try: 
        msg = json.loads(data.decode()) 
        if msg.get("type") == "SYNC_REQ": 
            t1 = int(msg["t1"]) # server receive time (t2), and send time (t3) 
            resp = { "type": "SYNC_RESP", "t1": t1, "t2": t2, "t3": now_us(), } 
            sock.sendto(json.dumps(resp).encode(), addr) 
            print(resp["t1"]) 
    except Exception as e: 
        print("Bad packet:", e)