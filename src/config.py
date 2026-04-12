"""兼容插件模式和MMC模式的配置类"""

from dataclasses import dataclass


@dataclass
class LumaClientConfig:
    server: str = "127.0.0.1"
    port: int = 3001
    token: str = ""
    response_timeout: int = 10


class Config:
    def __init__(self):
        self.server: str = "127.0.0.1"
        """服务器地址，默认为127.0.0.1"""
        self.port: int = 3001
        """端口号，默认为3001"""
        self.token: str = ""

    def update_config(self, server: str, port: int, token: str = ""):
        """更新配置"""
        self.server = server
        self.port = port
        self.token = token
