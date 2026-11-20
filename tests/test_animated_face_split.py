"""动图表情出站拆分回归测试：同条消息里排在动图表情之后的内容会被平台丢弃。"""

from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import sys


PACKAGE = "qq_animated_face_split_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package

message_codec = import_module(f"{PACKAGE}.codecs.outbound.message_codec")
QQOutboundCodec = message_codec.QQOutboundCodec
split_after_animated_faces = message_codec.split_after_animated_faces
profiles = import_module(f"{PACKAGE}.profile")

# 317 /菜汪 与 311 /打call 是动图表情，264 /捂脸 是经典小黄脸。
ANIMATED_STICKER = {"type": "face", "data": {"id": "317"}}
CLASSIC_FACE = {"type": "face", "data": {"id": "264"}}


def build_actions(raw_message, group=False, profile=profiles.SNOWLUMA_PROFILE):
    """以开启文本表情转换的配置构建发送动作。"""
    codec = QQOutboundCodec(SimpleNamespace(profile=profile), enable_text_face_conversion=lambda: True)
    route = {"group_id": "456"} if group else {"user_id": "789"}
    return codec.build_outbound_actions({"raw_message": raw_message}, route)


def messages(actions):
    """取出每个发送动作的消息段列表。"""
    return [params["message"] for _, params in actions]


@pytest.mark.parametrize(
    "raw_message,expected",
    [
        pytest.param([ANIMATED_STICKER, {"type": "text", "data": "正文"}],
                     [[ANIMATED_STICKER], [{"type": "text", "data": {"text": "正文"}}]],
                     id="animated-then-text"),
        pytest.param([ANIMATED_STICKER],
                     [[ANIMATED_STICKER]],
                     id="animated-alone"),
        pytest.param([{"type": "text", "data": "正文"}, ANIMATED_STICKER],
                     [[{"type": "text", "data": {"text": "正文"}}, ANIMATED_STICKER]],
                     id="text-then-animated"),
        pytest.param([ANIMATED_STICKER, ANIMATED_STICKER],
                     [[ANIMATED_STICKER], [ANIMATED_STICKER]],
                     id="animated-run"),
        pytest.param([CLASSIC_FACE, {"type": "text", "data": "正文"}],
                     [[CLASSIC_FACE, {"type": "text", "data": {"text": "正文"}}]],
                     id="classic-face-keeps-text"),
        pytest.param([{"type": "text", "data": "/菜汪 这不就来了喵"}],
                     [[ANIMATED_STICKER], [{"type": "text", "data": {"text": " 这不就来了喵"}}]],
                     id="text-face-conversion"),
        pytest.param([{"type": "text", "data": "/捂脸 这不就来了喵"}],
                     [[CLASSIC_FACE, {"type": "text", "data": {"text": " 这不就来了喵"}}]],
                     id="text-classic-face-conversion"),
        pytest.param([{"type": "text", "data": "今天 /菜汪 真冷"}],
                     [[{"type": "text", "data": {"text": "今天 "}}, ANIMATED_STICKER],
                      [{"type": "text", "data": {"text": " 真冷"}}]],
                     id="animated-mid-sentence"),
    ],
)
def test_animated_face_splits_following_segments(raw_message, expected):
    assert messages(build_actions(raw_message)) == expected


@pytest.mark.parametrize(
    "profile_name,action",
    [("NAPCAT_PROFILE", "send_group_msg"), ("SNOWLUMA_PROFILE", "send_msg")],
    ids=["napcat", "snowluma"],
)
def test_group_message_keeps_target_and_order(profile_name, action):
    actions = build_actions(
        [{"type": "text", "data": "/菜汪 在吗"}], group=True, profile=getattr(profiles, profile_name)
    )
    assert [name for name, _ in actions] == [action, action]
    assert all(params["group_id"] == "456" for _, params in actions)


def test_split_keeps_single_group_without_animated_face():
    segments = [{"type": "text", "data": {"text": "你好"}}]
    assert split_after_animated_faces(segments) == [segments]


def test_split_returns_empty_when_no_segments():
    assert split_after_animated_faces([]) == []
