import json
from dataclasses import dataclass

@dataclass
class Config:
    vehicle_ip: str = "0.0.0.0"
    vehicle_port: int = 2002
    lora_com_port: str = "COM4"
    host_ip: str = "0.0.0.0"
    tcp_port: int = 5000
    udp_port: int = 5002

class ConfigManager:
    def __init__(self, filename):
        self.filename = filename
        self.config = Config()
        self.listeners = []

        self.load()

    def load(self):
        try:
            with open(self.filename) as f:
                data = json.load(f)

            self.config = Config(**data)

            for callback in self.listeners:
                callback(self.config)
        except Exception as e:
            print("Config File not found")

    def register_listener(self, callback):
        self.listeners.append(callback)