"""Incoming QQ images and stickers keep their media type and bytes."""

import base64
import hashlib
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TypedDict

import pytest

PACKAGE = "qq_image_chain_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = package
QQInboundCodec = import_module(f"{PACKAGE}.codecs.inbound.message_codec").QQInboundCodec
profiles = import_module(f"{PACKAGE}.profile")
MEDIA = b"received-image-bytes"
ENCODED = base64.b64encode(MEDIA).decode()


class ImageMetadata(TypedDict, total=False):
    subType: int | str | None
    sub_type: int | str | None
    summary: str


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("segment_type", "metadata", "expected"),
    [
        ("image", {"subType": 1}, "emoji"),
        ("image", {"subType": "1"}, "emoji"),
        ("image", {"sub_type": 1}, "emoji"),
        ("image", {"subType": 0}, "image"),
        ("image", {"subType": "0"}, "image"),
        ("image", {"subType": 4}, "image"),
        ("image", {"subType": 9}, "image"),
        ("image", {"sub_type": 4}, "image"),
        ("image", {"sub_type": 9}, "image"),
        ("image", {"sub_type": 7}, "emoji"),
        ("image", {"sub_type": 0, "subType": 1}, "image"),
        ("image", {"subType": 0, "summary": "[动画表情]"}, "image"),
        ("image", {"summary": "holiday photo"}, "image"),
        ("image", {"subType": "invalid"}, "image"),
        ("image", {"subType": None}, "image"),
        ("image", {}, "image"),
        ("mface", {}, "emoji"),
    ],
)
async def test_image_metadata_preserves_media_kind(
    segment_type: str, metadata: ImageMetadata, expected: str,
) -> None:
    # Given an incoming image with its original bytes and protocol metadata.
    codec = QQInboundCodec(None, None, profiles.ProfileState(profiles.NAPCAT_PROFILE), lambda: None)
    payload = {"message": [{"type": segment_type, "data": {"base64": ENCODED, **metadata}}]}

    # When the real inbound converter handles the segment.
    segments, _ = await codec.convert_segments(payload, "123")

    # Then classification does not alter or discard the received media.
    assert segments == [{
        "type": expected, "data": "", "hash": hashlib.sha256(MEDIA).hexdigest(),
        "binary_data_base64": ENCODED,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("segments", "is_emoji", "is_picture"),
    [
        ([("image", {"subType": 1})], True, False),
        ([("mface", {})], True, False),
        ([("image", {"subType": 0})], False, True),
        ([("image", {"subType": 1}), ("image", {"subType": 0})], True, True),
    ],
)
async def test_message_media_flags_follow_converted_segments(
    segments: list[tuple[str, ImageMetadata]], is_emoji: bool, is_picture: bool,
) -> None:
    # Given a message ready for host routing.
    codec = QQInboundCodec(None, None, profiles.ProfileState(profiles.NAPCAT_PROFILE), lambda: SimpleNamespace())
    payload = {
        "message_id": 1, "message_type": "private", "time": 1700000000,
        "message": [{"type": kind, "data": {"base64": ENCODED, **metadata}} for kind, metadata in segments],
    }

    # When the full host message dictionary is built.
    message = await codec.build_message_dict(payload, "123", "456", {"nickname": "sender"})

    # Then both media flags describe the converted content, including mixed messages.
    assert (message["is_emoji"], message["is_picture"]) == (is_emoji, is_picture)
