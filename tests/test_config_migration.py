"""旧连接段在默认值补齐前迁移，显式的新配置始终优先。"""

from copy import deepcopy
from importlib import import_module
from typing import Any, Dict

import pytest


Plugin = import_module("plugins.MaiBot-SnowLuma-Adapter-main.plugin").SnowLumaAdapterPlugin


@pytest.mark.parametrize("section", ["luma_client", "napcat_server", "connection"])
@pytest.mark.parametrize("aliases", [False, True])
def test_legacy_connection_and_settings_survive_normalization(section: str, aliases: bool) -> None:
    client = {"server": "192.0.2.10", "port": 3456, "token": "test-only-token"}
    legacy = {"host": client["server"], "access_token": client["token"], "port": client["port"]} if aliases else client
    raw = {
        "plugin": {"config_version": "2.7.1", "enabled": True, "enable_poke_tool": True},
        section: legacy,
        "filters": {"ban_user_id": ["123"], "ignore_self_message": False},
    }
    original = deepcopy(raw)
    plugin = Plugin()
    normalized, changed = plugin.normalize_plugin_config(raw)
    assert changed
    assert {key: normalized["client"][key] for key in client} == client
    assert normalized["chat_abilities"]["enable_poke_tool"] is True
    assert normalized["debug"]["ignore_self_message"] is False
    assert normalized["filters"]["ban_user_id"] == ["123"]
    assert normalized["plugin"]["enabled"] is True
    assert section not in normalized
    assert raw == original
    plugin.set_plugin_config(normalized)
    assert plugin.config.client.server == client["server"]
    assert plugin.config.client.token == client["token"]


def test_explicit_current_fields_override_legacy_even_when_equal_to_defaults() -> None:
    raw: Dict[str, Any] = {
        "plugin": {"config_version": "2.7.1", "enable_poke_tool": True},
        "luma_client": {"server": "192.0.2.10", "port": 3456, "token": "old-test-token"},
        "client": {"server": "127.0.0.1", "port": 3001, "token": ""},
        "chat_abilities": {"enable_poke_tool": False},
    }
    normalized, _ = Plugin().normalize_plugin_config(raw)
    assert {key: normalized["client"][key] for key in raw["client"]} == raw["client"]
    assert normalized["chat_abilities"]["enable_poke_tool"] is False


def test_missing_version_is_not_silently_initialized() -> None:
    with pytest.raises(ValueError, match="config_version"):
        Plugin().normalize_plugin_config({"client": {"token": "test-only-token"}})
