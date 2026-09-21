"""客户端画像：NapCat / SnowLuma 能力差异定义与自动判定。

两类客户端都讲 OneBot v11 风格 WebSocket，但在以下维度存在实现差异，
统一由画像（ClientProfile）声明，编解码与传输层按画像取值：

1. 发送消息动作：NapCat 用 ``send_group_msg`` / ``send_private_msg``，SnowLuma 用通用 ``send_msg``。
2. 出站文件：SnowLuma 需要拆成独立 ``upload_group_file`` / ``upload_private_file`` 动作，
   NapCat 支持内联 ``file`` 段。
3. 合并转发参数键：NapCat 为 ``message``，SnowLuma 为 ``messages``。
4. 语音：SnowLuma 返回 silk 编码，需要 pysilk + ffmpeg 转码；NapCat 可直接要 wav。
5. QZone 系列 API 仅 SnowLuma 实现。

token 鉴权不区分画像：传输层同时附带 ``Authorization: Bearer`` 头与 URL
``access_token`` 参数（OneBot v11 两种标准方式），两类服务端各取所需，
这也是 auto 模式下唯一可行的方式——探测发生在握手之后。

对端类型判定基于标准动作 ``get_version_info`` 返回的 ``app_name``：
该字段由各实现自报家门（SnowLuma 返回 "SnowLuma"，对端返回 "NapCat"），
属于确定性识别而非启发式猜测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Tuple

import asyncio

PROBE_ACTION = "get_version_info"
PROBE_ATTEMPTS = 2
PROBE_RETRY_INTERVAL_SEC = 1.0

MSG_ACTION_STYLE_TARGETED = "targeted"
MSG_ACTION_STYLE_GENERIC = "generic"

FORWARD_PARAM_KEY_MESSAGE = "message"
FORWARD_PARAM_KEY_MESSAGES = "messages"

QZONE_API_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("get_qzone_msg_list", "获取 QZone 好友动态列表"),
    ("get_qzone_feeds", "获取 QZone 个人档与动态"),
    ("send_qzone_msg", "发表 QZone 说说"),
    ("delete_qzone_msg", "删除 QZone 说说"),
    ("like_qzone", "点赞 QZone 内容"),
    ("unlike_qzone", "取消 QZone 点赞"),
    ("comment_qzone", "评论 QZone 内容"),
)


@dataclass(frozen=True)
class ClientProfile:
    """单个客户端实现的能力画像。"""

    client_type: str
    expected_app_name: str
    msg_action_style: str
    split_file_upload: bool
    forward_param_key: str
    record_out_format: str
    transcode_silk_voice: bool
    supports_qzone: bool


NAPCAT_PROFILE = ClientProfile(
    client_type="napcat",
    expected_app_name="napcat",
    msg_action_style=MSG_ACTION_STYLE_TARGETED,
    split_file_upload=False,
    forward_param_key=FORWARD_PARAM_KEY_MESSAGE,
    record_out_format="wav",
    transcode_silk_voice=False,
    supports_qzone=False,
)

SNOWLUMA_PROFILE = ClientProfile(
    client_type="snowluma",
    expected_app_name="snowluma",
    msg_action_style=MSG_ACTION_STYLE_GENERIC,
    split_file_upload=True,
    forward_param_key=FORWARD_PARAM_KEY_MESSAGES,
    record_out_format="mp3",
    transcode_silk_voice=True,
    supports_qzone=True,
)

PROFILE_BY_TYPE: Dict[str, ClientProfile] = {
    NAPCAT_PROFILE.client_type: NAPCAT_PROFILE,
    SNOWLUMA_PROFILE.client_type: SNOWLUMA_PROFILE,
}


class ProfileState:
    """当前连接生效画像的可变容器。

    连接建立前以配置声明（或 auto 的临时占位）初始化；
    ``get_version_info`` 探测完成后由路由器写回判定结果。
    """

    def __init__(self, initial_profile: ClientProfile) -> None:
        """初始化画像容器。

        Args:
            initial_profile: 初始生效画像。
        """
        self._profile = initial_profile

    @property
    def profile(self) -> ClientProfile:
        """返回当前生效画像。"""

        return self._profile

    def update(self, profile: ClientProfile) -> ClientProfile:
        """写入新的生效画像并返回。

        Args:
            profile: 探测判定后的画像。

        Returns:
            ClientProfile: 写入后的当前画像。
        """
        self._profile = profile
        return self._profile


def detect_client_type_from_app_name(app_name: str) -> Optional[str]:
    """从 ``get_version_info`` 的 app_name 判定客户端类型。

    Args:
        app_name: 对端自报的实现名称。

    Returns:
        Optional[str]: 判定出的客户端类型；无法识别时返回 ``None``（由调用方显式报错）。
    """

    normalized_app_name = str(app_name or "").strip().lower()
    if not normalized_app_name:
        return None
    if "snowluma" in normalized_app_name:
        return SNOWLUMA_PROFILE.client_type
    if "napcat" in normalized_app_name:
        return NAPCAT_PROFILE.client_type
    return None


async def probe_client_profile(
    call_action_data: Callable[[str, Optional[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
    logger: Any,
) -> Tuple[str, str, str]:
    """探测对端客户端类型。

    Args:
        call_action_data: 发送 OneBot 动作并返回 ``data`` 字段的回调。
        logger: 插件日志对象。

    Returns:
        Tuple[str, str, str]: ``(client_type, app_name, app_version)``。

    Raises:
        RuntimeError: 探测动作失败或对端类型无法识别时抛出（不静默猜测）。
    """

    last_error: Optional[Exception] = None
    version_info: Any = None
    for attempt in range(1, PROBE_ATTEMPTS + 1):
        try:
            version_info = await call_action_data(PROBE_ACTION, {})
            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning(f"客户端类型探测动作 {PROBE_ACTION} 失败，第 {attempt}/{PROBE_ATTEMPTS} 次: {exc}")
            if attempt < PROBE_ATTEMPTS:
                await asyncio.sleep(PROBE_RETRY_INTERVAL_SEC)

    if last_error is not None:
        raise RuntimeError(f"无法通过对端 {PROBE_ACTION} 探测客户端类型: {last_error}") from last_error

    if not isinstance(version_info, Mapping):
        raise RuntimeError(f"对端 {PROBE_ACTION} 响应缺少 data 字段，无法判定客户端类型")

    app_name = str(version_info.get("app_name") or version_info.get("app") or "").strip()
    app_version = str(version_info.get("app_version") or version_info.get("version") or "").strip()
    client_type = detect_client_type_from_app_name(app_name)
    if client_type is None:
        raise RuntimeError(
            f"对端 app_name='{app_name or '<空>'}' 无法识别为 napcat 或 snowluma，"
            "请在 client.client_type 中显式指定，或确认对端为受支持的实现"
        )
    return client_type, app_name, app_version
