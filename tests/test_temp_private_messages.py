"""群临时私聊的入站分类与出站目标回归测试。"""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import pytest

_package = "plugins.MaiBot-SnowLuma-Adapter-main"
QQInboundCodec = import_module(f"{_package}.codecs.inbound.message_codec").QQInboundCodec
QQOutboundCodec = import_module(f"{_package}.codecs.outbound.message_codec").QQOutboundCodec
profile_module = import_module(f"{_package}.profile")


@pytest.mark.parametrize("profile", [profile_module.NAPCAT_PROFILE, profile_module.SNOWLUMA_PROFILE])
@pytest.mark.parametrize("chat_type", ["private", "temp_private", "group"])
def test_inbound_chat_type_and_reply_target(profile, chat_type):
    query = SimpleNamespace(get_group_info=AsyncMock(return_value={"group_name": "来源群"}))
    state = profile_module.ProfileState(profile)
    inbound = QQInboundCodec(SimpleNamespace(), query, state, lambda: SimpleNamespace())
    payload = {
        "message_type": "group" if chat_type == "group" else "private",
        "sub_type": "group" if chat_type == "temp_private" else "normal",
        "message_id": 123,
        "message": [{"type": "text", "data": {"text": "你好"}}],
    }
    if chat_type != "private":
        payload["group_id"] = 456

    message = asyncio.run(inbound.build_message_dict(payload, "111", "789", {"nickname": "用户"}))
    info = message["message_info"]
    metadata = info["additional_config"]
    assert message["processed_plain_text"] == "你好"
    if chat_type == "group":
        assert info["group_info"] == {"group_id": "456", "group_name": "来源群"}
        assert metadata["platform_io_target_group_id"] == "456"
        assert "platform_io_target_user_id" not in metadata
        query.get_group_info.assert_awaited_once_with("456")
    else:
        assert "group_info" not in info
        assert "platform_io_target_group_id" not in metadata
        assert metadata["platform_io_target_user_id"] == "789"
        query.get_group_info.assert_not_awaited()
    if chat_type == "temp_private":
        assert metadata["platform_io_temp_group_id"] == "456"
    else:
        assert "platform_io_temp_group_id" not in metadata

    actions = QQOutboundCodec(state).build_outbound_actions(message, {})
    assert len(actions) == 1
    action, params = actions[0]
    if profile.msg_action_style == profile_module.MSG_ACTION_STYLE_GENERIC:
        assert action == "send_msg"
        assert params["message_type"] == ("group" if chat_type == "group" else "private")
    else:
        assert action == ("send_group_msg" if chat_type == "group" else "send_private_msg")
    if chat_type == "group":
        assert params["group_id"] == "456"
        assert "user_id" not in params
    else:
        assert params["user_id"] == "789"
        assert "group_id" not in params
