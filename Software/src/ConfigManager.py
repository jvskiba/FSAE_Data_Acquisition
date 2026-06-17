import json
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class MainConfig:
    vehicle_ip: str = "0.0.0.0"
    vehicle_port: int = 2002
    lora_com_port: str = "COM4"
    lora_baud: int = 115200
    host_ip: str = "0.0.0.0"
    tcp_port: int = 5000
    udp_port: int = 5002

@dataclass
class WebMetaConfig:
    # dynamic structure: { "RPM": { ... }, "MPH": { ... } }
    widgets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

@dataclass
class Config:
    main: MainConfig = field(default_factory=MainConfig)
    web_meta: WebMetaConfig = field(default_factory=WebMetaConfig)


class ConfigManager:
    def __init__(self, filename):
        self.filename = filename
        self.config = Config()
        self.listeners = []
        self.load()

    def load(self):
        try:
            with open(self.filename, "r") as f:
                data = json.load(f)

            main_data = data.get("Main", {})
            meta_data = data.get("Web_Meta_Config", {})

            self.config = Config(
                main=MainConfig(**main_data),
                web_meta=WebMetaConfig(widgets=meta_data)
            )

            for callback in self.listeners:
                callback(self.config)

        except FileNotFoundError:
            print("Config File not found")
        except Exception as e:
            print(f"Config load error: {e}")

    def register_listener(self, callback):
        self.listeners.append(callback)