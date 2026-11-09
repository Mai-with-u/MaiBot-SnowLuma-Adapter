from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import asyncio
import sys
import time

import pytest


PACKAGE = "snow_identity_only_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package
lease_module = import_module(f"{PACKAGE}.services.identity_only_lease")
router_module = import_module(f"{PACKAGE}.runtime.router")


def test_lease_defaults_off_renewal_expiry_and_owner_isolation(monkeypatch):
    clock = SimpleNamespace(elapsed=1000.0)
    monkeypatch.setattr(lease_module, "time", SimpleNamespace(monotonic=lambda: clock.elapsed, time=time.time))
    lease = lease_module.IdentityOnlyLease()
    assert not lease.active("123")
    assert lease.update("123", "first", True)["active"]
    assert not lease.active("124")
    clock.elapsed += 10
    lease.update("123", "first", True)
    clock.elapsed += 10
    assert lease.active("123")
    with pytest.raises(ValueError, match="另一个"):
        lease.update("123", "second", True)
    lease.update("123", "second", False)
    assert lease.active("123")
    clock.elapsed += 5
    assert not lease.active("123")
    lease.update("123", "second", True)
    lease.update("123", "first", False)
    assert lease.active("123")
    lease.update("123", "second", False)
    assert not lease.active("123")
    lease.update("123", "second", True)
    lease.clear()
    assert not lease.active("123")
    assert not lease_module.IdentityOnlyLease().active("123")


def make_router():
    settings = SimpleNamespace(
        filters=SimpleNamespace(ban_user_id=[], ban_qq_bot=False),
        debug=SimpleNamespace(ignore_self_message=True), client=SimpleNamespace(connection_id=""), notice=SimpleNamespace(),
    )
    gateway = SimpleNamespace(route_message=AsyncMock(return_value=True))
    router = router_module.QQEventRouter(gateway, Mock(), "gateway", lambda: settings)
    message = {
        "message_id": "message", "timestamp": time.time(), "account_id": "123",
        "message_info": {"group_info": {"group_id": "456"},
                         "user_info": {"user_id": "789", "user_nickname": "小明", "user_cardname": "名片"}},
        "raw_message": [{"type": "text", "data": "今天我们一起讨论新的功能"}],
    }
    runtime = SimpleNamespace(
        runtime_state=SimpleNamespace(account_id="123", scope=None, set_routing_enabled=AsyncMock()),
        official_bot_guard=SimpleNamespace(should_reject=AsyncMock(return_value=False), clear_cache=Mock()),
        inbound_codec=SimpleNamespace(build_message_dict=AsyncMock(return_value=message), clear_cache=Mock()),
        regex_filter=SimpleNamespace(is_message_allowed=Mock(return_value=True)),
        ban_tracker=SimpleNamespace(record_notice=AsyncMock()),
        notice_filter=SimpleNamespace(is_notice_event_allowed=Mock(return_value=True)),
        notice_codec=SimpleNamespace(build_notice_message_dict=AsyncMock(return_value=dict(message)),
                                     build_notice_dedupe_key=Mock(return_value="notice"), clear_cache=Mock()),
    )
    router.bind_runtime(runtime)
    return router, runtime, gateway


@pytest.mark.asyncio
async def test_mode_keeps_identity_collection_blocks_messages_notices_and_expires(monkeypatch):
    clock = SimpleNamespace(elapsed=1000.0)
    monkeypatch.setattr(lease_module, "time", SimpleNamespace(monotonic=lambda: clock.elapsed, time=time.time))
    router, runtime, gateway = make_router()
    router.identity_only_lease.update("123", "owner", True)
    event = {"self_id": "123", "user_id": "789", "message_id": "message", "group_id": "456", "time": time.time()}
    await router.handle_inbound_message(event)
    assert len(router.identity_observations.snapshot("123", ["456"])["observations"]) == 1
    gateway.route_message.assert_not_awaited()
    # 私聊也不投递，但不进入群身份缓存。
    runtime.inbound_codec.build_message_dict.return_value["message_info"]["group_info"] = None
    await router.handle_inbound_message({**event, "message_id": "private", "group_id": ""})
    gateway.route_message.assert_not_awaited()
    await router.handle_notice_event({"self_id": "123", "notice_type": "group_ban"})
    await router.emit_natural_lift_notice({"notice_type": "group_ban"})
    runtime.ban_tracker.record_notice.assert_awaited_once()
    runtime.notice_codec.build_notice_message_dict.assert_not_awaited()
    gateway.route_message.assert_not_awaited()
    # 无需维护任务清除状态：每次投递都检查单调时间，刚好到期即恢复。
    clock.elapsed += 15
    await router.handle_inbound_message(event)
    await router.route_notice_payload({"notice_type": "group_ban"}, "123", "")
    assert gateway.route_message.await_count == 2
    # 断连/重连复用路由器时同样不能残留激活状态。
    router.identity_only_lease.update("123", "owner", True)
    router.reset_caches()
    assert not router.identity_only_lease.active("123")


@pytest.mark.asyncio
async def test_querying_identity_never_renews_lease_and_api_requires_connected_account(monkeypatch):
    clock = SimpleNamespace(elapsed=1000.0)
    monkeypatch.setattr(lease_module, "time", SimpleNamespace(monotonic=lambda: clock.elapsed, time=time.time))
    plugin_type = import_module(f"{PACKAGE}.plugin").SnowLumaAdapterPlugin
    plugin = plugin_type()
    plugin.set_plugin_config(plugin.get_default_config())
    plugin._set_context(SimpleNamespace(call_capability=AsyncMock(return_value={"success": True}), logger=Mock()))
    router, runtime, _ = make_router()
    plugin._event_router, plugin._runtime_bundle = router, runtime
    assert not (await plugin.identity_only_lease("124", "owner"))["active"]
    assert (await plugin.identity_only_lease("123", "owner"))["active"]
    published = plugin.ctx.call_capability.call_args.kwargs["badges"]
    assert published[0]["label"] == "仅身份查询"
    deadline = published[0]["expires_at"]
    clock.elapsed += 10
    await plugin.identity_observations("123", ["456"])
    assert plugin.ctx.call_capability.call_args.kwargs["badges"][0]["expires_at"] == deadline
    clock.elapsed += 5
    assert not router.identity_only_lease.active("123")
    await plugin.identity_only_lease("123", "owner", enabled=False)
    assert plugin.ctx.call_capability.call_args.kwargs["badges"] == []
    runtime.runtime_state.account_id = None
    assert not (await plugin.identity_only_lease("123", "owner"))["active"]
    await plugin._stop_identity_mode_watch()


@pytest.mark.asyncio
async def test_identity_mode_withdraws_outbound_route_and_restores_without_new_messages(monkeypatch):
    plugin_type = import_module(f"{PACKAGE}.plugin").SnowLumaAdapterPlugin
    state_type = import_module(f"{PACKAGE}.runtime_state").QQRuntimeStateManager
    plugin = plugin_type()
    plugin.set_plugin_config(plugin.get_default_config())
    plugin._set_context(SimpleNamespace(call_capability=AsyncMock(return_value={"success": True}), logger=Mock()))
    router, _, gateway = make_router()
    gateway.update_state = AsyncMock(return_value=True)
    state = state_type(gateway, Mock(), "gateway")
    state.detected_protocol = "snowluma"
    await state.report_connected("123", plugin._load_settings().client)
    bundle = SimpleNamespace(
        runtime_state=state,
        outbound_codec=SimpleNamespace(prepare_outbound_actions=AsyncMock(return_value=[("send_group_msg", {})])),
        action_service=SimpleNamespace(call_action=AsyncMock()),
    )
    plugin._event_router, plugin._runtime_bundle = router, bundle
    monkeypatch.setattr(plugin, "_require_runtime_bundle", lambda: bundle)
    monkeypatch.setattr(lease_module, "IDENTITY_ONLY_TTL", 0.1)
    assert (await plugin.identity_only_lease("123", "owner"))["active"]
    assert gateway.update_state.call_args.kwargs["ready"] is False
    assert state.account_id == "123"  # 连接账号仍可用于身份查询和下一次续期。
    calls = gateway.update_state.await_count
    await state.report_connected("123", plugin._load_settings().client)
    assert gateway.update_state.await_count == calls  # 心跳不能重新注册已暂停的发送路由。
    sent = await plugin.handle_snowluma_gateway({"message_id": "reply"})
    assert sent["success"] is False
    bundle.action_service.call_action.assert_not_awaited()
    await asyncio.wait_for(plugin._identity_mode_watch, 2)
    assert gateway.update_state.call_args.kwargs["ready"] is True
    assert plugin.ctx.call_capability.call_args.kwargs["badges"] == []


@pytest.mark.asyncio
async def test_lost_route_update_response_does_not_prevent_restoration():
    state_type = import_module(f"{PACKAGE}.runtime_state").QQRuntimeStateManager
    gateway = SimpleNamespace(update_state=AsyncMock(return_value=True))
    state = state_type(gateway, Mock(), "gateway")
    state.detected_protocol = "snowluma"
    config = SimpleNamespace(connection_id="", build_ws_url=lambda: "ws://localhost")
    await state.report_connected("123", config)
    gateway.update_state.side_effect = RuntimeError("response lost after route withdrawal")
    with pytest.raises(RuntimeError, match="路由切换"):
        await state.set_routing_enabled(False, config)
    gateway.update_state.side_effect = None
    await state.set_routing_enabled(True, config)
    assert gateway.update_state.call_args.kwargs["ready"] is True


@pytest.mark.asyncio
async def test_notice_already_parsing_is_blocked_when_lease_activates():
    router, runtime, gateway = make_router()
    started, release = asyncio.Event(), asyncio.Event()

    async def parse_notice(payload):
        started.set()
        await release.wait()
        return {"message_info": {}, "raw_message": []}

    runtime.notice_codec.build_notice_message_dict.side_effect = parse_notice
    task = asyncio.create_task(router.route_notice_payload({"notice_type": "group_ban"}, "123", ""))
    await asyncio.wait_for(started.wait(), 1)
    router.identity_only_lease.update("123", "owner", True)
    release.set()
    await asyncio.wait_for(task, 1)
    gateway.route_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("filter_kind", ["user", "regex", "official_bot", "self"])
async def test_identity_collection_bypasses_chat_filters_and_restores_them_on_release(filter_kind):
    router, runtime, gateway = make_router()
    settings = router._load_settings()
    sender_id = "123" if filter_kind == "self" else "789"
    runtime.inbound_codec.build_message_dict.return_value["message_info"]["user_info"]["user_id"] = sender_id
    if filter_kind == "user":
        settings.filters.ban_user_id = [sender_id]
    if filter_kind == "regex":
        runtime.regex_filter.is_message_allowed.return_value = False
    if filter_kind == "official_bot":
        runtime.official_bot_guard.should_reject.return_value = True
    event = {"self_id": "123", "user_id": sender_id, "group_id": "456", "time": time.time()}
    router.identity_only_lease.update("123", "owner", True)
    await router.handle_inbound_message(event)
    assert len(router.identity_observations.snapshot("123", ["456"])["observations"]) == 1
    runtime.regex_filter.is_message_allowed.assert_not_called()
    runtime.official_bot_guard.should_reject.assert_not_awaited()
    gateway.route_message.assert_not_awaited()
    router.identity_only_lease.update("123", "owner", False)
    router.identity_observations.clear()
    await router.handle_inbound_message(event)
    assert router.identity_observations.snapshot("123", ["456"])["observations"] == []
    gateway.route_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_during_identity_decode_does_not_forward_unfiltered_message(monkeypatch):
    clock = SimpleNamespace(elapsed=1000.0)
    monkeypatch.setattr(lease_module, "time", SimpleNamespace(monotonic=lambda: clock.elapsed, time=time.time))
    router, runtime, gateway = make_router()
    router._load_settings().filters.ban_user_id = ["789"]
    decoded = runtime.inbound_codec.build_message_dict.return_value

    async def decode(*args):
        clock.elapsed += 15
        return decoded

    runtime.inbound_codec.build_message_dict.side_effect = decode
    router.identity_only_lease.update("123", "owner", True)
    await router.handle_inbound_message({"self_id": "123", "user_id": "789", "group_id": "456", "time": time.time()})
    assert not router.identity_only_lease.active("123")
    assert len(router.identity_observations.snapshot("123", ["456"])["observations"]) == 1
    gateway.route_message.assert_not_awaited()
