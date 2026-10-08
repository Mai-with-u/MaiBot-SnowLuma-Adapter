"""无效引用应被丢弃，正文和有效引用应保留。"""

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
@pytest.mark.parametrize("target_id", ["qq-notice-missing", "qq-missing", "", None, 0, "0"])
def test_unlocatable_outbound_reply_preserves_body(profile, target_id):
    codec = QQOutboundCodec(profile_module.ProfileState(profile))
    message = {"raw_message": [
        {"type": "reply", "data": {"target_message_id": target_id}},
        {"type": "text", "data": "戳两次是吧"},
    ]}
    actions = codec.build_outbound_actions(message, {"user_id": "123"})
    assert actions[0][1]["message"] == [{"type": "text", "data": {"text": "戳两次是吧"}}]


@pytest.mark.parametrize("target_id", ["123", "-123"])
def test_valid_outbound_reply_is_preserved(target_id):
    codec = QQOutboundCodec(profile_module.ProfileState(profile_module.NAPCAT_PROFILE))
    message = {"raw_message": [
        {"type": "reply", "data": {"target_message_id": target_id}},
        {"type": "text", "data": "正文"},
    ]}
    actions = codec.build_outbound_actions(message, {"user_id": "123"})
    assert actions[0][1]["message"] == [
        {"type": "reply", "data": {"id": target_id}},
        {"type": "text", "data": {"text": "正文"}},
    ]


@pytest.mark.parametrize("found", [False, True])
def test_inbound_missing_reply_preserves_body(found):
    detail = {"message": [{"type": "text", "data": {"text": "原消息"}}]} if found else None
    query = SimpleNamespace(get_message_detail=AsyncMock(return_value=detail))
    codec = QQInboundCodec(SimpleNamespace(), query, None, lambda: None)
    payload = {"message": [
        {"type": "reply", "data": {"id": "123"}},
        {"type": "text", "data": {"text": "正文"}},
    ]}
    segments, _ = asyncio.run(codec.convert_segments(payload, "456"))
    assert segments[-1] == {"type": "text", "data": "正文"}
    assert len(segments) == (2 if found else 1)
    if found:
        assert segments[0]["data"]["target_message_content"] == "原消息"
    query.get_message_detail.assert_awaited_once_with("123")


def test_reply_preview_does_not_query_nested_reply():
    query = SimpleNamespace(get_message_detail=AsyncMock())
    codec = QQInboundCodec(SimpleNamespace(), query, None, lambda: None)
    segment = asyncio.run(codec._build_reply_segment({"id": "123"}, resolve_details=False))
    assert segment == {"type": "reply", "data": {"target_message_id": "123"}}
    query.get_message_detail.assert_not_awaited()
