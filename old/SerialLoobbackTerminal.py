import socket

HOST = "192.168.1.151"  # replace with your Nano 33 IoT IP
PORT = 4000             # must match Arduino server port

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print(f"Connected to {HOST}:{PORT}")
    while True:
        msg = input("Send> ")
        if not msg:
            break
        s.sendall(msg.encode() + b"\n")
        data = s.recv(1024)
        print("Recv<", data.decode(errors="ignore"))
