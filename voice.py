"""语音转码：silk → PCM → MP3（移植自 SnowLuma 适配器）。

SnowLuma 的 ``get_record`` 返回 silk 编码语音（magic 头 ``#!SILK_V3``），
宿主侧需要可播放的 MP3：先用 pysilk 解码为 s16le/24000Hz/单声道 PCM，
再经 ffmpeg 子进程管道转码为 MP3。依赖缺失时返回空结果，
由上层记录警告并降级为占位文本（与 SnowLuma 适配器行为一致）。
"""

from __future__ import annotations

from io import BytesIO
from shutil import which
from typing import Optional

import asyncio
import subprocess

VOICE_TRANSCODE_SAMPLE_RATE = 24000
VOICE_TRANSCODE_TIMEOUT_SECONDS = 15.0

_SILK_MAGIC_PREFIXES = (b"#!SILK_V3", b"\x02#!SILK_V3")


def is_silk_voice_binary(data: bytes) -> bool:
    """按 magic 头判断二进制是否为 silk 编码语音。

    Args:
        data: 语音二进制内容。

    Returns:
        bool: 若为 silk 编码则返回 ``True``。
    """
    return data.startswith(_SILK_MAGIC_PREFIXES)


def _decode_silk_to_pcm_sync(data: bytes, sample_rate: int = VOICE_TRANSCODE_SAMPLE_RATE) -> bytes:
    """同步解码 silk 为 PCM（s16le/单声道）。

    Args:
        data: silk 二进制内容。
        sample_rate: 目标采样率。

    Returns:
        bytes: PCM 二进制；pysilk 未安装时返回空字节串。
    """
    try:
        from importlib import import_module

        pysilk = import_module("pysilk")
    except ImportError:
        return b""

    output_buffer = BytesIO()
    try:
        pysilk.decode(BytesIO(data), output_buffer, sample_rate)
    except Exception:
        return b""
    return output_buffer.getvalue()


async def transcode_silk_voice_binary(data: bytes) -> Optional[bytes]:
    """把 silk 语音转码为 MP3。

    Args:
        data: silk 二进制内容（非 silk 内容原样返回 ``None`` 表示无需转码）。

    Returns:
        Optional[bytes]: MP3 二进制；输入非 silk、依赖缺失或转码失败时返回 ``None``。
    """
    if not data or not is_silk_voice_binary(data):
        return None

    pcm_data = await asyncio.to_thread(_decode_silk_to_pcm_sync, data)
    if not pcm_data:
        return None

    ffmpeg_path = which("ffmpeg")
    if not ffmpeg_path:
        return None

    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-f",
            "s16le",
            "-ar",
            str(VOICE_TRANSCODE_SAMPLE_RATE),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-f",
            "mp3",
            "pipe:1",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None

    try:
        stdout_data, _ = await asyncio.wait_for(
            process.communicate(pcm_data),
            timeout=VOICE_TRANSCODE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        process.kill()
        return None
    except asyncio.CancelledError:
        process.kill()
        raise
    except Exception:
        return None

    if process.returncode != 0 or not stdout_data:
        return None
    return bytes(stdout_data)
