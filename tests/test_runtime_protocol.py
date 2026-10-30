from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import sys

import pytest


PACKAGE = "sl_runtime_protocol_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package
QQRuntimeStateManager = import_module(f"{PACKAGE}.runtime_state").QQRuntimeStateManager
QQEventRouter = import_module(f"{PACKAGE}.runtime.router").QQEventRouter
profile = import_module(f"{PACKAGE}.profile")


@pytest.mark.asyncio
async def test_protocol_detection_and_switch_are_reported():
    gateway = SimpleNamespace(update_state=AsyncMock(return_value=True))
    state = QQRuntimeStateManager(gateway, Mock(), "gateway")
    config = SimpleNamespace(connection_id="connection", build_ws_url=lambda: "ws://localhost")
    assert not await state.report_connected("bot", config)
    gateway.update_state.assert_not_awaited()
    for protocol in ("napcat", "snowluma"):
        state.detected_protocol = protocol
        assert await state.report_connected("bot", config)
        assert gateway.update_state.call_args.kwargs["metadata"]["protocol"] == protocol
        assert gateway.update_state.call_args.kwargs["platform"] == "qq"
    assert gateway.update_state.await_count == 2
    assert await state.report_connected("bot", config)
    assert gateway.update_state.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("declared_type,ready", [("napcat", True), ("auto", False)])
async def test_unknown_app_name_respects_explicit_profile(declared_type, ready):
    settings = SimpleNamespace(client=SimpleNamespace(client_type=declared_type, heartbeat_interval=30))
    runtime = SimpleNamespace(
        action_service=SimpleNamespace(call_action_data=AsyncMock(return_value={"app_name": "LLOneBot"})),
        runtime_state=SimpleNamespace(detected_protocol=None, report_connected=AsyncMock()),
        profile_state=profile.ProfileState(profile.NAPCAT_PROFILE),
        profile=profile.NAPCAT_PROFILE,
        query_service=SimpleNamespace(get_login_info=AsyncMock(return_value={"user_id": 123})),
        heartbeat_monitor=SimpleNamespace(start=AsyncMock()),
        ban_tracker=SimpleNamespace(start=AsyncMock()),
    )
    router = QQEventRouter(Mock(), Mock(), "gateway", lambda: settings)
    router.bind_runtime(runtime)
    await router.bootstrap_adapter_runtime_state()
    assert runtime.runtime_state.report_connected.await_count == int(ready)
    assert runtime.runtime_state.detected_protocol == ("LLOneBot" if ready else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["user_id", "operator_id", "target_id"])
async def test_notice_blacklist_blocks_each_participant(field):
    settings = SimpleNamespace(
        client=SimpleNamespace(connection_id="connection"),
        filters=SimpleNamespace(ban_user_id=["123"]),
        notice=SimpleNamespace(),
    )
    gateway = SimpleNamespace(route_message=AsyncMock(return_value=True))
    runtime = SimpleNamespace(
        ban_tracker=SimpleNamespace(record_notice=AsyncMock()),
        notice_filter=SimpleNamespace(is_notice_event_allowed=Mock(return_value=True)),
        notice_codec=SimpleNamespace(
            build_notice_message_dict=AsyncMock(return_value={}),
            build_notice_dedupe_key=Mock(return_value="notice"),
        ),
    )
    router = QQEventRouter(gateway, Mock(), "gateway", lambda: settings)
    router.bind_runtime(runtime)
    payload = {"notice_type": "notify", "sub_type": "poke", field: 123}
    await router.handle_notice_event(payload)
    runtime.ban_tracker.record_notice.assert_awaited_once_with(payload)
    runtime.notice_codec.build_notice_message_dict.assert_not_awaited()
    gateway.route_message.assert_not_awaited()

    payload[field] = 456
    await router.handle_notice_event(payload)
    gateway.route_message.assert_awaited_once()
