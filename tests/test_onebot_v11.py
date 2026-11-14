from aiohttp import WSMsgType, web
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import asyncio
import json

import pytest

QQInboundCodec = import_module("plugins.MaiBot-SnowLuma-Adapter-main.codecs.inbound.message_codec").QQInboundCodec
QQPluginSettings = import_module("plugins.MaiBot-SnowLuma-Adapter-main.config").QQPluginSettings
parse_cq_message = import_module("plugins.MaiBot-SnowLuma-Adapter-main.cqcode").parse_cq_message
SnowLumaAdapterPlugin = import_module("plugins.MaiBot-SnowLuma-Adapter-main.plugin").SnowLumaAdapterPlugin
ONEBOT_V11_PROFILE = import_module("plugins.MaiBot-SnowLuma-Adapter-main.profile").ONEBOT_V11_PROFILE
ProfileState = import_module("plugins.MaiBot-SnowLuma-Adapter-main.profile").ProfileState
probe_client_profile = import_module("plugins.MaiBot-SnowLuma-Adapter-main.profile").probe_client_profile
QQRuntimeBuilder = import_module("plugins.MaiBot-SnowLuma-Adapter-main.runtime.builder").QQRuntimeBuilder
QQEventRouter = import_module("plugins.MaiBot-SnowLuma-Adapter-main.runtime.router").QQEventRouter
QQActionService = import_module("plugins.MaiBot-SnowLuma-Adapter-main.services.action_service").QQActionService
QQBanStateStore = import_module("plugins.MaiBot-SnowLuma-Adapter-main.services.ban_state_store").QQBanStateStore


def test_cq_escaping_and_literal_text():
    assert parse_cq_message(" A&#91;CQ:at,qq=123&#93;[CQ:at,qq=456][CQ:image,file=a&#44;b&amp;c] ") == [
        {"type": "text", "data": {"text": " A[CQ:at,qq=123]"}},
        {"type": "at", "data": {"qq": "456"}},
        {"type": "image", "data": {"file": "a,b&c"}},
        {"type": "text", "data": {"text": " "}},
    ]
    assert parse_cq_message("&amp;#91;CQ:at,qq=1&amp;#93;")[0]["data"]["text"] == "&#91;CQ:at,qq=1&#93;"
    with pytest.raises(ValueError, match="参数"):
        parse_cq_message("[CQ:at,qq=1,qq=2]")


@pytest.mark.asyncio
async def test_cq_and_array_messages_have_identical_mentions():
    queries = SimpleNamespace(get_stranger_info=AsyncMock(return_value={"nickname": "test"}))
    codec = QQInboundCodec(Mock(), queries, ProfileState(ONEBOT_V11_PROFILE), QQPluginSettings)
    cq = "你好 [CQ:at,qq=123]"
    assert await codec.convert_segments({"message": cq}, "123") == await codec.convert_segments(
        {"message": parse_cq_message(cq)}, "123"
    )
    _, mentioned = await codec.convert_segments({"message": cq}, "123")
    assert mentioned


@pytest.mark.asyncio
@pytest.mark.parametrize("action,params", [
    ("upload_group_file", {"group_id": 123, "file": "file:///test"}),
    ("send_group_forward_msg", {"group_id": 123, "message": []}),
    ("send_poke", {"user_id": 123}),
    ("send_group_msg", {"group_id": 123, "message": [{"type": "file", "data": {"file": "x"}}]}),
    ("send_group_msg", {"group_id": 123, "message": "[CQ:file,file=x]"}),
])
async def test_unsupported_actions_fail_before_network(action, params):
    transport = SimpleNamespace(call_action=AsyncMock())
    service = QQActionService(Mock(), transport, ProfileState(ONEBOT_V11_PROFILE))
    with pytest.raises(NotImplementedError):
        await service.safe_call_action_data(action, params)
    transport.call_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_probe_recovers_after_first_timeout(monkeypatch):
    monkeypatch.setattr("plugins.MaiBot-SnowLuma-Adapter-main.profile.PROBE_RETRY_INTERVAL_SEC", 0)
    call = AsyncMock(side_effect=[TimeoutError("timeout"), {"app_name": "NapCat", "app_version": "1"}])
    assert await probe_client_profile(call, Mock()) == ("napcat", "NapCat", "1")


def test_plugin_identity_and_disabled_default():
    plugin = SnowLumaAdapterPlugin()
    plugin.set_plugin_config(plugin.get_default_config())
    assert plugin.config.client.client_type == "auto"
    assert not plugin.config.should_connect()
    components = plugin.get_components()
    names = [component["name"] for component in components]
    assert len(names) == len(set(names))
    assert "snowluma_gateway" in names
    assert "adapter.onebot.action.call" in names
    assert "adapter.napcat.action.call" in names
    assert "adapter.snowluma.action.call" in names
    assert "identity_observations" in names
    assert "identity_only_lease" in names
    by_name = {component["name"]: component for component in components}
    original = by_name["adapter.napcat.action.call"]
    for prefix in ("snowluma", "onebot"):
        alias = by_name[f"adapter.{prefix}.action.call"]
        assert {key: value for key, value in alias.items() if key != "name"} == {
            key: value for key, value in original.items() if key != "name"
        }
    manifest = json.loads((Path(__file__).parents[1] / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "maibot-team.snowluma-adapter"
    store = QQBanStateStore(Mock())
    assert store._storage_path == Path(__file__).parents[2] / "data" / "napcat_adapter" / "ban_state.json"


@pytest.mark.parametrize("client_type", ["snowluma", "napcat"])
def test_vendor_string_messages_keep_original_plain_text_behavior(client_type):
    profiles = import_module("plugins.MaiBot-SnowLuma-Adapter-main.profile")
    codec = QQInboundCodec(Mock(), Mock(), ProfileState(profiles.PROFILE_BY_TYPE[client_type]), QQPluginSettings)
    message = "literal [CQ:at,qq=123] &amp;"
    assert codec._require_message_segments({"message": message}) == [
        {"type": "text", "data": {"text": message}},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("client_type", ["snowluma", "napcat"])
@pytest.mark.parametrize("action", ["upload_group_file", "send_poke", "set_msg_emoji_like"])
async def test_vendor_actions_are_not_restricted_or_rewritten(client_type, action):
    profiles = import_module("plugins.MaiBot-SnowLuma-Adapter-main.profile")
    response = {"status": "ok", "retcode": 0, "data": {}}
    transport = SimpleNamespace(call_action=AsyncMock(return_value=response))
    service = QQActionService(Mock(), transport, ProfileState(profiles.PROFILE_BY_TYPE[client_type]))
    params = {"group_id": "123", "user_id": "456", "vendor_parameter": "preserved"}
    assert await service.call_action(action, params) == response
    transport.call_action.assert_awaited_once_with(action, params)


@pytest.mark.asyncio
@pytest.mark.parametrize("client_type,extensions", [("onebot_v11", False), ("napcat", True), ("snowluma", True)])
async def test_tools_follow_profile(client_type, extensions):
    plugin = SnowLumaAdapterPlugin()
    config = plugin.get_default_config()
    config["plugin"]["enabled"] = True
    config["client"]["client_type"] = client_type
    config["chat_abilities"].update(enable_poke_tool=True, enable_emoji_like_tool=True, enable_forward_tool=True)
    plugin.set_plugin_config(config)
    component = SimpleNamespace(
        enable_component=AsyncMock(return_value={"success": True}),
        disable_component=AsyncMock(return_value={"success": True}),
    )
    plugin._ctx = SimpleNamespace(component=component, logger=Mock())
    await plugin._sync_tool_components_state()
    method = component.enable_component if extensions else component.disable_component
    for name in ("send_poke", "react_emoji", "forward_messages"):
        assert any(call.args == (name, "TOOL") for call in method.await_args_list)


@pytest.mark.asyncio
async def test_real_websocket_handshake_receive_send_and_disconnect(tmp_path, unused_tcp_port):
    """通过本地 OneBot 模拟服务验证完整传输、初始化和消息路由。"""
    connected = asyncio.Event()
    received = asyncio.Event()
    actions = []

    async def endpoint(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.query["access_token"] == "test-token"
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for frame in ws:
            if frame.type != WSMsgType.TEXT:
                continue
            payload = json.loads(frame.data)
            action = payload["action"]
            actions.append(payload)
            if action == "get_version_info":
                data = {"app_name": "TestOneBot", "app_version": "1", "protocol_version": "v11"}
            elif action == "get_login_info":
                data = {"user_id": 123, "nickname": "test"}
            elif action == "send_private_msg":
                assert payload["params"]["user_id"] == 456
                data = {"message_id": 789}
            elif action == "get_stranger_info":
                data = {"user_id": 123, "nickname": "test"}
            else:
                raise AssertionError(f"不应调用额外动作: {action}")
            await ws.send_json({"status": "ok", "retcode": 0, "data": data, "echo": payload["echo"]})
            if action == "get_login_info":
                await connected.wait()
                await ws.send_json({
                    "post_type": "message", "message_type": "private", "self_id": 123,
                    "user_id": 456, "message_id": 100, "time": 123456,
                    "sender": {"nickname": "测试用户"}, "message": "你好 [CQ:at,qq=123]",
                })
        return ws

    app = web.Application()
    app.router.add_get("/", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    settings = QQPluginSettings.model_validate({"plugin": {"enabled": True}, "client": {
        "client_type": "auto", "port": unused_tcp_port, "token": "test-token",
    }})

    async def update_state(**kwargs):
        if kwargs["ready"]:
            connected.set()
        return True

    async def route_message(**kwargs):
        message = kwargs["message"]
        assert message["platform"] == "qq"
        assert message["account_id"] == "123"
        assert message["message_id"] == "100"
        assert message["is_at"]
        received.set()
        return True

    gateway = SimpleNamespace(update_state=AsyncMock(side_effect=update_state), route_message=AsyncMock(side_effect=route_message))
    router = QQEventRouter(gateway, Mock(), "snowluma_gateway", lambda: settings)
    bundle = QQRuntimeBuilder(gateway, Mock(), "snowluma_gateway").build(
        on_connection_opened=router.bootstrap_adapter_runtime_state,
        on_connection_closed=router.handle_transport_disconnected,
        on_payload=router.handle_transport_payload,
        on_natural_lift=router.emit_natural_lift_notice,
        on_heartbeat_timeout=router.handle_heartbeat_timeout,
        profile_state=ProfileState(ONEBOT_V11_PROFILE), load_settings=lambda: settings,
    )
    bundle.ban_tracker._state_store = QQBanStateStore(Mock(), tmp_path / "ban_state.json")
    router.bind_runtime(bundle)
    bundle.transport.configure(settings.client, bundle.profile_state)
    try:
        await bundle.transport.start()
        await asyncio.wait_for(received.wait(), timeout=5)
        assert bundle.profile == ONEBOT_V11_PROFILE
        outbound = await bundle.outbound_codec.prepare_outbound_actions(
            {"raw_message": [{"type": "text", "data": "回复测试"}]}, {"user_id": "456"}
        )
        assert len(outbound) == 1
        action, params = outbound[0]
        result = await bundle.action_service.call_action(action, params)
        assert result["data"]["message_id"] == 789
        assert [item["action"] for item in actions] == [
            "get_version_info", "get_login_info", "get_stranger_info", "send_private_msg",
        ]
    finally:
        await bundle.transport.stop()
        await runner.cleanup()
    assert bundle.runtime_state.account_id is None
    assert gateway.update_state.call_args.kwargs["ready"] is False
    assert not bundle.transport._pending_actions
