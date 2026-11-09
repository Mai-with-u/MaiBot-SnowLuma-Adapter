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


def make_heartbeat_router(client_type: str):
    gateway = SimpleNamespace(update_state=AsyncMock(return_value=True))
    state = QQRuntimeStateManager(gateway, Mock(), "gateway")
    state.detected_protocol = client_type
    settings = SimpleNamespace(client=SimpleNamespace(
        connection_id="connection", heartbeat_interval=30, build_ws_url=lambda: "ws://localhost",
    ))
    runtime = SimpleNamespace(
        runtime_state=state, profile=profile.PROFILE_BY_TYPE[client_type],
        heartbeat_monitor=SimpleNamespace(observe_meta_event=AsyncMock(), stop=AsyncMock()),
        notice_codec=SimpleNamespace(handle_meta_event=AsyncMock(), clear_cache=Mock()),
        inbound_codec=SimpleNamespace(clear_cache=Mock()),
        official_bot_guard=SimpleNamespace(clear_cache=Mock()),
        ban_tracker=SimpleNamespace(stop=AsyncMock()),
    )
    router = QQEventRouter(gateway, Mock(), "gateway", lambda: settings)
    router.bind_runtime(runtime)
    return router, runtime, gateway, settings


@pytest.mark.asyncio
@pytest.mark.parametrize("client_type", ["snowluma", "napcat", "onebot_v11"])
@pytest.mark.parametrize("online,good", [(True, True), (True, False), (False, True), (False, False)])
async def test_heartbeat_routing_respects_client_status_semantics(client_type: str, online: bool, good: bool):
    router, runtime, gateway, settings = make_heartbeat_router(client_type)
    await runtime.runtime_state.report_connected("123", settings.client)
    payload = {"meta_event_type": "heartbeat", "self_id": 123, "status": {"online": online, "good": good}}
    await router.handle_meta_event(payload)
    ready = online and (client_type == "snowluma" or good)
    assert gateway.update_state.call_args.kwargs["ready"] is ready
    assert runtime.runtime_state.account_id == ("123" if ready else None)
    runtime.heartbeat_monitor.observe_meta_event.assert_awaited_once_with(payload, 30)
    runtime.notice_codec.handle_meta_event.assert_awaited_once_with(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_only", [False, True])
async def test_snowluma_health_changes_never_toggle_existing_route(identity_only: bool):
    router, runtime, gateway, settings = make_heartbeat_router("snowluma")
    await runtime.runtime_state.report_connected("123", settings.client)
    if identity_only:
        router.identity_only_lease.update("123", "official", True)
        await runtime.runtime_state.set_routing_enabled(False, settings.client)
    gateway.update_state.reset_mock()
    for good in (False, False, True):
        await router.handle_meta_event({
            "meta_event_type": "heartbeat", "self_id": 123, "status": {"online": True, "good": good},
        })
        assert runtime.runtime_state.account_id == "123"
    gateway.update_state.assert_not_awaited()
    assert router.identity_only_lease.active("123") is identity_only


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["timeout", "websocket_closed"])
async def test_snowluma_real_connection_loss_still_withdraws_route(reason: str):
    router, runtime, gateway, settings = make_heartbeat_router("snowluma")
    await runtime.runtime_state.report_connected("123", settings.client)
    if reason == "timeout":
        await router.handle_heartbeat_timeout("123")
    else:
        await router.handle_transport_disconnected()
    assert gateway.update_state.call_args.kwargs["ready"] is False
    assert runtime.runtime_state.account_id is None


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
@pytest.mark.parametrize("declared_type,ready", [("napcat", True), ("auto", True), ("onebot_v11", True)])
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
    expected_profile = profile.NAPCAT_PROFILE if declared_type == "napcat" else profile.ONEBOT_V11_PROFILE
    assert runtime.profile_state.profile == expected_profile
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
