"""JSON 卡片编码、SDK 包装及出站路由回归测试。"""

from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict

import json
import pytest
import sys


PACKAGE = "qq_json_outbound_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package
QQOutboundSegmentEncoder = import_module(f"{PACKAGE}.codecs.outbound.segment_encoder").QQOutboundSegmentEncoder
QQOutboundCodec = import_module(f"{PACKAGE}.codecs.outbound.message_codec").QQOutboundCodec
profiles = import_module(f"{PACKAGE}.profile")

CARD = {
    "app": "com.tencent.miniapp_01",
    "meta": {"detail_1": {"title": "视频分享", "qqdocurl": "https://www.bilibili.com/video/test"}},
    "signature": "keep+/=signature",
    "unknown_field": {"enabled": True, "count": 1},
}
CARD_JSON = " \n" + json.dumps(CARD, ensure_ascii=False, indent=2) + "\n "


def json_item(payload: Any, wrapped: bool) -> Dict[str, Any]:
    item = {"type": "json", "data": payload}
    return {"type": "dict", "data": item} if wrapped else item


@pytest.mark.parametrize("wrapped", [False, True], ids=["direct", "sdk"])
@pytest.mark.parametrize("payload", [CARD, CARD_JSON], ids=["object", "string"])
def test_json_preserves_card_fields_and_string_original(payload, wrapped):
    segments = QQOutboundSegmentEncoder().convert_segments([json_item(payload, wrapped)])
    assert len(segments) == 1
    assert segments[0]["type"] == "json"
    assert set(segments[0]["data"]) == {"data"}
    encoded = segments[0]["data"]["data"]
    assert json.loads(encoded) == CARD
    if isinstance(payload, str):
        assert encoded == payload


@pytest.mark.parametrize("wrapped", [False, True], ids=["direct", "sdk"])
@pytest.mark.parametrize(
    "payload",
    ["", "{invalid", "{}", "[]", "null", '"text"', "123", "true", {}, [], None,
     {"value": object()}, {"value": float("nan")}, '{"value": Infinity}'],
    ids=["empty", "malformed", "empty-object", "array-json", "null-json", "string-json", "number-json",
         "boolean-json", "empty-dict", "list", "none", "unserializable", "nan", "infinity"],
)
def test_invalid_json_raises_instead_of_sending_placeholder(payload, wrapped):
    with pytest.raises(ValueError, match="JSON"):
        QQOutboundSegmentEncoder().convert_segments([json_item(payload, wrapped)])


@pytest.mark.parametrize("wrapped", [False, True], ids=["direct", "sdk"])
def test_missing_json_payload_is_rejected(wrapped):
    item = {"type": "json"}
    if wrapped:
        item = {"type": "dict", "data": item}
    with pytest.raises(ValueError, match="JSON"):
        QQOutboundSegmentEncoder().convert_segments([item])


@pytest.mark.parametrize("profile", [profiles.NAPCAT_PROFILE, profiles.SNOWLUMA_PROFILE], ids=["napcat", "snowluma"])
@pytest.mark.parametrize("group", [True, False], ids=["group", "private"])
def test_sdk_card_uses_existing_route_and_preserves_message_order(profile, group):
    codec = QQOutboundCodec(SimpleNamespace(profile=profile))
    route = {"group_id": "456"} if group else {"user_id": "789"}
    actions = codec.build_outbound_actions(
        {"raw_message": [json_item(CARD_JSON, True), {"type": "text", "data": "分享感想"}]}, route
    )
    expected_action = "send_msg" if profile == profiles.SNOWLUMA_PROFILE else (
        "send_group_msg" if group else "send_private_msg"
    )
    assert len(actions) == 1
    action, params = actions[0]
    assert action == expected_action
    assert params["group_id" if group else "user_id"] == ("456" if group else "789")
    assert params["message"] == [
        {"type": "json", "data": {"data": CARD_JSON}},
        {"type": "text", "data": {"text": "分享感想"}},
    ]


@pytest.mark.parametrize("profile", [profiles.NAPCAT_PROFILE, profiles.SNOWLUMA_PROFILE], ids=["napcat", "snowluma"])
def test_invalid_card_aborts_action_preparation(profile):
    codec = QQOutboundCodec(SimpleNamespace(profile=profile))
    with pytest.raises(ValueError, match="JSON"):
        codec.build_outbound_actions(
            {"raw_message": [{"type": "text", "data": "before"}, json_item("{}", True)]},
            {"group_id": "456"},
        )
