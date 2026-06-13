import socket

ESP_IP = "192.168.8.175"
PORT = 2002

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((ESP_IP, PORT))

s.sendall(b"Disable FileServer\n")
print(s.recv(1024).decode())

s.close()