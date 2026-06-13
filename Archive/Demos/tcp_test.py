import socket

HOST = "192.168.8.175"   # change this to your server IP
PORT = 2000          # change this to your server port

def tcp_echo_test(value: str):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))

            # send data
            s.sendall(value.encode('utf-8'))

            # receive response
            response = s.recv(1024).decode('utf-8')

            print(f"Sent:     {value}")
            print(f"Received: {response}")

            if response == value:
                print("Match confirmed. The universe is behaving.")
                return True
            else:
                print("Mismatch. Something is lying (probably the network).")
                return False

    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    tcp_echo_test("12345")