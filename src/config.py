"""兼容插件模式和MMC模式的配置类"""

from pathlib import Path
from typing import Any
from maibot_sdk import PluginConfigBase

import tomlkit


class LumaClientConfig(PluginConfigBase):
    server: str = "127.0.0.1"
    """ws服务器地址，默认127.0.0.1"""
    port: int = 3001
    """ws端口号，默认3001"""
    token: str = ""
    """ws连接token，默认为空字符串，必填"""
    response_timeout: int = 10
    """请求响应超时时间，单位为秒，默认10秒"""


class Config(PluginConfigBase):
    luma_client: LumaClientConfig = LumaClientConfig()
    """LumaClient配置"""


def update_config(config_dict: dict[str, Any], config_instance: PluginConfigBase):
    """更新配置"""
    for key, value in config_dict.items():
        if hasattr(config_instance, key):
            attr = getattr(config_instance, key)
            if isinstance(attr, PluginConfigBase) and isinstance(value, dict):
                update_config(value, attr)
            else:
                setattr(config_instance, key, value)


def load_config_from_dict(config_dict: dict[str, Any]) -> Config:
    """加载配置"""
    config = Config()
    update_config(config_dict, config)
    return config


def load_config_from_file(file_path: Path) -> Config:
    """从文件加载配置"""
    with open(file_path, "r", encoding="utf-8") as f:
        config_dict = tomlkit.load(f)
    return load_config_from_dict(config_dict)
