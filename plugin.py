from __future__ import annotations

from .snowluma_adapter.core import SnowLumaAdapterPlugin


def create_plugin() -> SnowLumaAdapterPlugin:
    """创建 SnowLuma 适配器插件实例。"""

    return SnowLumaAdapterPlugin()
