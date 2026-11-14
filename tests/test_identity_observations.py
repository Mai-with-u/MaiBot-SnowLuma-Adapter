from hashlib import sha256
from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import sys
import time

import pytest


PACKAGE = "snow_identity_observation_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package
observations = import_module(f"{PACKAGE}.services.identity_observations")


def message(key, timestamp, group="456", account="123"):
    return {
        "message_id": key, "timestamp": timestamp, "account_id": account,
        "message_info": {
            "group_info": {"group_id": group},
            "user_info": {"user_id": "789", "user_nickname": "小明", "user_cardname": ""},
        },
        "raw_message": [{"type": "text", "data": "hello world 123"}],
    }


def test_snapshot_contains_only_requested_groups_account_and_fingerprint():
    source = observations.IdentityObservations()
    now = time.time()
    for group, account in [("456", "123"), ("457", "123"), ("456", "124")]:
        source.observe(message("first", now, group, account))
    rows = source.snapshot("123", ["456"])["observations"]
    assert len(rows) == 1
    assert rows[0]["fingerprint"] == sha256(b"hello world 123").hexdigest()
    assert rows[0]["nickname"] == "小明"
    assert "raw_message" not in rows[0] and "received_at" not in rows[0]
    with pytest.raises(ValueError):
        source.snapshot("123", ["456"] * 129)


def test_source_limits_expiry_and_duplicate_delivery(monkeypatch):
    current = SimpleNamespace(wall=time.time(), elapsed=1000.0)
    monkeypatch.setattr(observations, "time", SimpleNamespace(time=lambda: current.wall, monotonic=lambda: current.elapsed))
    monkeypatch.setattr(observations, "MAX_OBSERVATIONS", 4)
    monkeypatch.setattr(observations, "MAX_GROUP_OBSERVATIONS", 2)
    source = observations.IdentityObservations()
    for index in range(10):
        source.observe(message(str(index), current.wall))
    assert len(source._rows) == 2
    source.observe(message("9", current.wall))
    assert len(source._rows) == 2
    for index in range(10):
        source.observe(message(str(index), current.wall, group=str(500 + index)))
    assert len(source._rows) == 4
    current.elapsed += observations.OBSERVATION_TTL
    assert source.snapshot("123", ["509"])["observations"] == []
    assert not source._rows


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), 0.0])
def test_invalid_or_stale_platform_timestamp_is_not_observed(timestamp):
    source = observations.IdentityObservations()
    source.observe(message("first", timestamp))
    assert not source._rows


def test_private_messages_are_not_observed():
    source = observations.IdentityObservations()
    payload = message("first", time.time())
    payload["message_info"]["group_info"] = None
    source.observe(payload)
    assert not source._rows


@pytest.mark.asyncio
async def test_public_api_gates_current_account_and_router_records_messages():
    plugin_type = import_module(f"{PACKAGE}.plugin").SnowLumaAdapterPlugin
    router_type = import_module(f"{PACKAGE}.runtime.router").QQEventRouter
    settings = SimpleNamespace(
        filters=SimpleNamespace(ban_user_id=[], ban_qq_bot=False),
        debug=SimpleNamespace(ignore_self_message=True), client=SimpleNamespace(connection_id=""),
    )
    gateway = SimpleNamespace(route_message=AsyncMock(return_value=True))
    router = router_type(gateway, Mock(), "gateway", lambda: settings)
    payload = message("first", time.time())
    runtime = SimpleNamespace(
        runtime_state=SimpleNamespace(account_id="123"),
        official_bot_guard=SimpleNamespace(should_reject=AsyncMock(return_value=False)),
        inbound_codec=SimpleNamespace(build_message_dict=AsyncMock(return_value=payload)),
        regex_filter=SimpleNamespace(is_message_allowed=Mock(return_value=True)),
    )
    router.bind_runtime(runtime)
    await router.handle_inbound_message({
        "self_id": "123", "user_id": "789", "group_id": "456", "time": time.time(),
    })
    plugin = plugin_type()
    plugin._event_router = router
    plugin._runtime_bundle = runtime
    assert len((await plugin.identity_observations("123", ["456"]))["observations"]) == 1
    assert (await plugin.identity_observations("124", ["456"]))["observations"] == []
    runtime.runtime_state.account_id = None
    assert (await plugin.identity_observations("123", ["456"]))["observations"] == []
    # 不依赖内存实例共享，接口声明会由 SDK 正常注册。
    assert any(component["name"] == "identity_observations" for component in plugin.get_components())


def test_fingerprint_protocol_handles_mentions_and_media():
    segments = [{"type": "at", "data": {"target_user_id": "123"}},
                {"type": "text", "data": " hello　world １２３ "}]
    assert observations.text_fingerprint(segments) == sha256(b"hello world 123").hexdigest()
    for text in ("收到", "哈哈哈哈哈哈哈哈哈", "/assign_id 123456789"):
        assert observations.text_fingerprint([{"type": "text", "data": text}]) == ""
    assert observations.text_fingerprint([{"type": "image", "data": "binary"}]) == ""
