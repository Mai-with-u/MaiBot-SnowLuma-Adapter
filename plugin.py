from __future__ import annotations

from importlib import import_module
from io import BytesIO
from pathlib import Path
from shutil import which
from typing import Any, ClassVar, Dict, List, Literal, Mapping, Optional, Tuple
from urllib.parse import urlencode
from uuid import uuid4

from aiohttp import ClientSession, ClientTimeout, ClientWebSocketResponse, WSMsgType
from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType
from pydantic import field_validator

import asyncio
import base64
import hashlib
import json
import time

try:
    from .qq_face_map import QQ_FACE_DESCRIPTIONS, QQ_FACE_EMOJIS
except ImportError:
    from qq_face_map import QQ_FACE_DESCRIPTIONS, QQ_FACE_EMOJIS


SNOWLUMA_GATEWAY_NAME = "snowluma_gateway"
SUPPORTED_CONFIG_VERSION = "1.0.3"
DEFAULT_CHAT_LIST_TYPE = "whitelist"
PRIVATE_CHAT_TOOL_BYPASS_SECONDS = 15 * 60
VOICE_TRANSCODE_SAMPLE_RATE = 24000
VOICE_TRANSCODE_TIMEOUT_SECONDS = 15.0


def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """构造 WebUI 配置项多语言说明，保留外层中文字段兼容旧格式。"""

    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n


class SnowLumaPluginSection(PluginConfigBase):
    """插件开关配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用 SnowLuma 适配器。",
        json_schema_extra={
            "label": "启用适配器",
            "hint": "关闭时插件只注册消息网关，不会主动连接 SnowLuma。",
            "i18n": _schema_i18n(
                label_en="Enable adapter",
                label_ja="アダプターを有効化",
                hint_en="When disabled, the plugin only registers the message gateway and will not connect to SnowLuma.",
                hint_ja="無効にすると、プラグインはメッセージゲートウェイの登録のみを行い、SnowLuma へ接続しません。",
            ),
            "order": 0,
        },
    )
    enable_ada_debug_raw_message_log: bool = Field(
        default=False,
        description="是否启用 Ada 调试模式，记录 SnowLuma 入站原始消息段。",
        json_schema_extra={
            "label": "Ada 调试原始消息段",
            "hint": "仅排查消息段结构问题时开启；开启后会以 info 级别记录每条入站消息的原始 message 字段。",
            "i18n": _schema_i18n(
                label_en="Ada raw message debug",
                label_ja="Ada 生メッセージデバッグ",
                hint_en="Enable only while debugging segment structure; logs each inbound raw message field at info level.",
                hint_ja="セグメント構造を調査するときだけ有効にしてください。入站 message フィールドを info レベルで記録します。",
            ),
            "order": 1,
        },
    )
    enable_private_chat_tool: bool = Field(
        default=False,
        description="是否启用主动开启私聊工具。",
        json_schema_extra={
            "label": "启用主动私聊工具",
            "hint": "开启后，模型可调用工具向指定用户发送首条私聊消息，并在 15 分钟内绕过私聊名单过滤。",
            "i18n": _schema_i18n(
                label_en="Enable private chat tool",
                label_ja="個人チャット開始ツールを有効化",
                hint_en=(
                    "When enabled, the model can use a tool to send the first private message to a user "
                    "and bypass private chat-list filtering for 15 minutes."
                ),
                hint_ja=(
                    "有効にすると、モデルは指定ユーザーへ最初の個人メッセージを送信し、"
                    "15 分間だけ個人チャットリストのフィルターを回避できます。"
                ),
            ),
            "order": 2,
        },
    )
    qq_face_parse_mode: Literal["description", "emoji"] = Field(
        default="description",
        description="QQ 自带表情解析模式：转为中文描述或近似 Unicode emoji。",
        json_schema_extra={
            "label": "QQ 自带表情解析",
            "hint": "description 会把 [CQ:face,id=5] 转成 [流泪]；emoji 会优先转成近似 Unicode 表情。",
            "i18n": _schema_i18n(
                label_en="QQ face parsing",
                label_ja="QQ 標準顔文字の解析",
                hint_en=(
                    "description converts [CQ:face,id=5] to [流泪]; "
                    "emoji prefers an approximate Unicode emoji."
                ),
                hint_ja=(
                    "description は [CQ:face,id=5] を [流泪] に変換します。"
                    "emoji は近い Unicode 絵文字を優先します。"
                ),
            ),
            "order": 3,
        },
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "i18n": _schema_i18n(label_en="Config version", label_ja="設定バージョン"),
            "label": "配置版本",
            "order": 99,
        },
    )


class SnowLumaClientSection(PluginConfigBase):
    """SnowLuma WebSocket 连接配置。"""

    __ui_label__: ClassVar[str] = "SnowLuma 连接"
    __ui_order__: ClassVar[int] = 1

    server: str = Field(
        default="127.0.0.1",
        description="SnowLuma WebSocket 服务地址。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Server address",
                label_ja="サーバーアドレス",
                hint_en="Usually the host running SnowLuma. Defaults to the local loopback address.",
                hint_ja="通常は SnowLuma を実行しているホストです。既定ではローカルのループバックアドレスを使用します。",
                placeholder_en="127.0.0.1",
                placeholder_ja="127.0.0.1",
            ),
            "label": "服务地址",
            "order": 0,
            "placeholder": "127.0.0.1",
        },
    )
    port: int = Field(
        default=3001,
        description="SnowLuma WebSocket 服务端口。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Port",
                label_ja="ポート",
                hint_en="Keep this consistent with the SnowLuma WebSocket listening port.",
                hint_ja="SnowLuma WebSocket の待受ポートと一致させてください。",
            ),
            "label": "端口",
            "order": 1,
        },
    )
    token: str = Field(
        default="",
        description="SnowLuma 访问令牌。",
        json_schema_extra={
            "label": "访问令牌",
            "i18n": _schema_i18n(
                label_en="Access token",
                label_ja="アクセストークン",
                hint_en="If SnowLuma access token verification is enabled, enter the same token here.",
                hint_ja="SnowLuma でアクセストークン検証を有効にしている場合は、同じ token をここに入力してください。",
                placeholder_en="Optional",
                placeholder_ja="空欄可",
            ),
            "input_type": "password",
            "order": 2,
            "placeholder": "可留空",
        },
    )
    connection_id: str = Field(
        default="",
        description="可选连接标识，用于区分多条适配器链路。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Connection ID",
                label_ja="接続識別子",
                hint_en="When multiple SnowLuma connections exist, use this as the routing scope identifier.",
                hint_ja="複数の SnowLuma 接続がある場合、ルーティングスコープの識別子として使用できます。",
            ),
            "label": "连接标识",
            "order": 3,
        },
    )
    reconnect_delay_sec: float = Field(
        default=5.0,
        description="连接断开后的重连等待时间，单位为秒。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Reconnect delay (sec)",
                label_ja="再接続待機（秒）",
                hint_en="After a disconnect, wait this long before trying to reconnect.",
                hint_ja="接続が切断された後、再接続を試すまでこの時間待機します。",
            ),
            "label": "重连等待",
            "order": 4,
            "step": 1,
        },
    )
    action_timeout_sec: float = Field(
        default=10.0,
        description="调用 SnowLuma 动作接口的超时时间，单位为秒。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Action timeout (sec)",
                label_ja="アクションタイムアウト（秒）",
                hint_en="Actions such as sending messages or querying info fail after this timeout.",
                hint_ja="メッセージ送信や情報取得などのアクションは、この時間を超えるとエラーになります。",
            ),
            "label": "动作超时",
            "order": 5,
            "step": 1,
        },
    )

    def build_ws_url(self) -> str:
        """构造 SnowLuma WebSocket 地址。"""

        base_url = f"ws://{self.server}:{self.port}"
        if not self.token:
            return base_url
        return f"{base_url}?{urlencode({'access_token': self.token})}"


class SnowLumaChatSection(PluginConfigBase):
    """聊天名单过滤配置。"""

    __ui_label__: ClassVar[str] = "聊天过滤"
    __ui_order__: ClassVar[int] = 2

    enable_chat_list_filter: bool = Field(
        default=True,
        description="是否启用群聊与私聊名单过滤。",
        json_schema_extra={
            "hint": "关闭后将忽略 group_list 和 private_list，仅保留 ban_user_id 规则。",
            "i18n": _schema_i18n(
                label_en="Enable chat list filter",
                label_ja="チャットリストフィルターを有効化",
                hint_en="When disabled, group_list and private_list are ignored; only ban_user_id rules remain.",
                hint_ja="無効にすると、group_list と private_list を無視し、ban_user_id ルールのみを適用します。",
            ),
            "label": "启用聊天名单过滤",
            "order": 0,
        },
    )
    show_dropped_chat_list_messages: bool = Field(
        default=False,
        description="是否记录未通过聊天名单过滤而被丢弃的消息。",
        json_schema_extra={
            "hint": "关闭后不记录群聊/私聊名单丢弃日志，默认关闭以减少刷屏。",
            "i18n": _schema_i18n(
                label_en="Show dropped chat-list logs",
                label_ja="チャットリストで破棄されたログを表示",
                hint_en="When disabled, dropped group/private chat-list logs are not recorded. Default off to reduce log noise.",
                hint_ja="無効にすると、チャットリストで破棄されたグループ/個人チャットのログを記録しません。ログの増加を抑えるため既定ではオフです。",
            ),
            "label": "显示聊天名单丢弃日志",
            "order": 1,
        },
    )
    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="群聊名单模式。",
        json_schema_extra={
            "hint": "白名单模式只接收列表内群聊，黑名单模式则忽略列表内群聊。",
            "i18n": _schema_i18n(
                label_en="Group list mode",
                label_ja="グループリストモード",
                hint_en="Whitelist mode only accepts listed groups; blacklist mode ignores listed groups.",
                hint_ja="ホワイトリストではリスト内のグループのみ受信し、ブラックリストではリスト内のグループを無視します。",
            ),
            "label": "群聊名单模式",
            "order": 2,
        },
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="群聊名单中的群号列表。",
        json_schema_extra={
            "hint": "群号会被统一转换为字符串并自动去重。",
            "i18n": _schema_i18n(
                label_en="Group list",
                label_ja="グループリスト",
                hint_en="Group IDs are normalized to strings and deduplicated automatically.",
                hint_ja="グループ ID は文字列に正規化され、自動的に重複排除されます。",
                placeholder_en="Enter group ID",
                placeholder_ja="グループ ID を入力",
            ),
            "label": "群聊名单",
            "order": 3,
            "placeholder": "请输入群号",
        },
    )
    private_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="私聊名单模式。",
        json_schema_extra={
            "hint": "白名单模式只接收列表内私聊，黑名单模式则忽略列表内私聊。",
            "i18n": _schema_i18n(
                label_en="Private list mode",
                label_ja="個人チャットリストモード",
                hint_en="Whitelist mode only accepts listed private chats; blacklist mode ignores listed private chats.",
                hint_ja="ホワイトリストではリスト内の個人チャットのみ受信し、ブラックリストではリスト内の個人チャットを無視します。",
            ),
            "label": "私聊名单模式",
            "order": 4,
        },
    )
    private_list: List[str] = Field(
        default_factory=list,
        description="私聊名单中的用户 ID 列表。",
        json_schema_extra={
            "hint": "用户 ID 会被统一转换为字符串并自动去重。",
            "i18n": _schema_i18n(
                label_en="Private list",
                label_ja="個人チャットリスト",
                hint_en="User IDs are normalized to strings and deduplicated automatically.",
                hint_ja="ユーザー ID は文字列に正規化され、自動的に重複排除されます。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザー ID を入力",
            ),
            "label": "私聊名单",
            "order": 5,
            "placeholder": "请输入用户 ID",
        },
    )
    ban_user_id: List[str] = Field(
        default_factory=list,
        description="全局屏蔽的用户 ID 列表。",
        json_schema_extra={
            "hint": "这些用户的消息会在进入 Host 之前被直接丢弃。",
            "i18n": _schema_i18n(
                label_en="Globally blocked users",
                label_ja="全体ブロックユーザー",
                hint_en="Messages from these users are dropped before entering the Host.",
                hint_ja="これらのユーザーからのメッセージは Host に入る前に破棄されます。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザー ID を入力",
            ),
            "label": "全局屏蔽用户",
            "order": 6,
            "placeholder": "请输入用户 ID",
        },
    )
    ban_qq_bot: bool = Field(
        default=False,
        description="是否屏蔽 QQ 官方机器人消息。",
        json_schema_extra={
            "hint": "SnowLuma 推送中能识别出官方机器人标记时会丢弃对应消息。",
            "i18n": _schema_i18n(
                label_en="Block official bots",
                label_ja="公式 Bot をブロック",
                hint_en="When SnowLuma push events identify an official bot marker, matching messages are dropped.",
                hint_ja="SnowLuma のプッシュ内で公式 Bot のマーカーを識別できる場合、該当メッセージを破棄します。",
            ),
            "label": "屏蔽官方机器人",
            "order": 7,
        },
    )

    @field_validator("group_list_type", "private_list_type", mode="before")
    @classmethod
    def _normalize_list_types(cls, value: Any) -> Literal["whitelist", "blacklist"]:
        """规范化名单模式字段。"""

        normalized_value = str(value or DEFAULT_CHAT_LIST_TYPE).strip().lower()
        if normalized_value not in {"whitelist", "blacklist"}:
            return DEFAULT_CHAT_LIST_TYPE
        return normalized_value  # type: ignore[return-value]

    @field_validator("group_list", "private_list", "ban_user_id", mode="before")
    @classmethod
    def _normalize_id_lists(cls, value: Any) -> List[str]:
        """规范化 ID 列表字段。"""

        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        normalized_values: List[str] = []
        seen_values: set[str] = set()
        for raw_value in raw_values:
            normalized_value = str(raw_value or "").strip()
            if not normalized_value or normalized_value in seen_values:
                continue
            normalized_values.append(normalized_value)
            seen_values.add(normalized_value)
        return normalized_values


class SnowLumaFilterSection(PluginConfigBase):
    """消息过滤配置。"""

    __ui_label__: ClassVar[str] = "消息过滤"
    __ui_order__: ClassVar[int] = 3

    ignore_self_message: bool = Field(
        default=True,
        description="是否忽略机器人自身发送的消息。",
        json_schema_extra={
            "hint": "建议保持开启，避免机器人处理自己刚刚发出的消息。",
            "i18n": _schema_i18n(
                label_en="Ignore self messages",
                label_ja="自身のメッセージを無視",
                hint_en="Recommended on to avoid the bot processing messages it just sent.",
                hint_ja="Bot が自分で送信した直後のメッセージを処理しないよう、有効のままにすることを推奨します。",
            ),
            "label": "忽略自身消息",
            "order": 0,
        },
    )


class SnowLumaAdapterSettings(PluginConfigBase):
    """SnowLuma 适配器完整配置。"""

    plugin: SnowLumaPluginSection = Field(default_factory=SnowLumaPluginSection)
    luma_client: SnowLumaClientSection = Field(default_factory=SnowLumaClientSection)
    chat: SnowLumaChatSection = Field(default_factory=SnowLumaChatSection)
    filters: SnowLumaFilterSection = Field(default_factory=SnowLumaFilterSection)

    def should_connect(self) -> bool:
        """判断当前配置是否应该建立连接。"""

        return self.plugin.enabled


class SnowLumaAdapterPlugin(MaiBotPlugin):
    """SnowLuma 消息网关插件。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = SnowLumaAdapterSettings

    def __init__(self) -> None:
        """初始化 SnowLuma 适配器插件。"""

        super().__init__()
        self._session: Optional[ClientSession] = None
        self._ws: Optional[ClientWebSocketResponse] = None
        self._connection_task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._response_pool: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._connected_account_id: str = ""
        self._group_name_cache: Dict[str, str] = {}
        self._group_member_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
        self._private_chat_bypass_expires_at: Dict[str, float] = {}

    async def on_load(self) -> None:
        """插件加载后按配置启动连接。"""

        await self._sync_private_chat_tool_component_state()
        await self._restart_connection_if_needed()

    async def on_unload(self) -> None:
        """插件卸载前关闭连接。"""

        await self._stop_connection()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """配置更新后重启连接。"""

        if scope != "self":
            return

        self.set_plugin_config(config_data)
        if version:
            self.ctx.logger.debug(f"SnowLuma 适配器收到配置更新: {version}")
        await self._sync_private_chat_tool_component_state()
        await self._restart_connection_if_needed()

    @API("adapter.napcat.group.get_group_member_info", description="获取群成员信息", version="1", public=True)
    async def api_get_group_member_info(
        self,
        group_id: Any,
        user_id: Any,
        no_cache: bool = True,
    ) -> Dict[str, Any]:
        """获取群成员信息。"""

        return await self._call_action(
            "get_group_member_info",
            {
                "group_id": self._normalize_positive_id(group_id, "group_id"),
                "user_id": self._normalize_positive_id(user_id, "user_id"),
                "no_cache": bool(no_cache),
            },
        )

    @API("adapter.napcat.group.set_group_ban", description="设置群成员禁言", version="1", public=True)
    async def api_set_group_ban(self, group_id: Any, user_id: Any, duration: Any) -> Dict[str, Any]:
        """设置群成员禁言。"""

        normalized_duration = self._normalize_non_negative_int(duration, "duration")
        if normalized_duration > 2592000:
            raise ValueError("duration 不能超过 2592000 秒")
        return await self._call_action(
            "set_group_ban",
            {
                "group_id": self._normalize_positive_id(group_id, "group_id"),
                "user_id": self._normalize_positive_id(user_id, "user_id"),
                "duration": normalized_duration,
            },
        )

    # ================================================================
    # 发送 / 撤回 / 登录信息 公开 API
    # 供 ai_draw_plugin 等插件通过 SDK passthrough 调用，避免插件直连 NapCat。
    # 走 WebSocket 长连接（_call_action），回传 message_id 以支持精确撤回。
    # ================================================================

    def _action_result(self, response: Mapping[str, Any]) -> Dict[str, Any]:
        """统一封装动作响应：附带 message_id，保留原始 data/retcode。"""

        return {
            "status": str(response.get("status") or ""),
            "retcode": response.get("retcode"),
            "message_id": self._extract_action_message_id(response),
            "data": response.get("data"),
        }

    @API("adapter.napcat.message.send_group_msg", description="发送群消息", version="1", public=True)
    async def api_send_group_msg(self, **kwargs: Any) -> Dict[str, Any]:
        """发送群消息（OneBot message 段数组）。"""
        params = kwargs.get("params", kwargs)
        message = params.get("message")
        if not isinstance(message, list) or not message:
            raise ValueError("message 必须是非空的消息段数组")
        response = await self._call_action(
            "send_group_msg",
            {
                "group_id": self._normalize_positive_id(params.get("group_id"), "group_id"),
                "message": message,
            },
        )
        return self._action_result(response)

    @API("adapter.napcat.message.send_private_msg", description="发送私聊消息", version="1", public=True)
    async def api_send_private_msg(self, **kwargs: Any) -> Dict[str, Any]:
        """发送私聊消息（OneBot message 段数组）。"""
        params = kwargs.get("params", kwargs)
        message = params.get("message")
        if not isinstance(message, list) or not message:
            raise ValueError("message 必须是非空的消息段数组")
        response = await self._call_action(
            "send_private_msg",
            {
                "user_id": self._normalize_positive_id(params.get("user_id"), "user_id"),
                "message": message,
            },
        )
        return self._action_result(response)

    @API("adapter.napcat.message.send_group_forward_msg", description="发送群合并转发消息", version="1", public=True)
    async def api_send_group_forward_msg(self, **kwargs: Any) -> Dict[str, Any]:
        """发送群合并转发消息（OneBot node 段数组）。"""
        params = kwargs.get("params", kwargs)
        messages = params.get("messages") or params.get("message")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages 必须是非空的转发节点数组")
        response = await self._call_action(
            "send_group_forward_msg",
            {
                "group_id": self._normalize_positive_id(params.get("group_id"), "group_id"),
                "messages": messages,
            },
        )
        return self._action_result(response)

    @API("adapter.napcat.message.send_private_forward_msg", description="发送私聊合并转发消息", version="1", public=True)
    async def api_send_private_forward_msg(self, **kwargs: Any) -> Dict[str, Any]:
        """发送私聊合并转发消息（OneBot node 段数组）。"""
        params = kwargs.get("params", kwargs)
        messages = params.get("messages") or params.get("message")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages 必须是非空的转发节点数组")
        response = await self._call_action(
            "send_private_forward_msg",
            {
                "user_id": self._normalize_positive_id(params.get("user_id"), "user_id"),
                "messages": messages,
            },
        )
        return self._action_result(response)

    @API("adapter.napcat.message.delete_msg", description="撤回消息", version="1", public=True)
    async def api_delete_msg(self, **kwargs: Any) -> Dict[str, Any]:
        """撤回消息。message_id 允许为负（OneBot 32 位有符号回绕值）。"""
        params = kwargs.get("params", kwargs)
        return await self._call_action(
            "delete_msg",
            {"message_id": self._normalize_int(params.get("message_id"), "message_id")},
        )

    @API("adapter.napcat.message.get_group_msg_history", description="获取群消息历史", version="1", public=True)
    async def api_get_group_msg_history(self, **kwargs: Any) -> Dict[str, Any]:
        """获取群消息历史。"""
        params = kwargs.get("params", kwargs)
        return await self._call_action(
            "get_group_msg_history",
            {
                "group_id": self._normalize_positive_id(params.get("group_id"), "group_id"),
                "count": int(params.get("count", 20)),
            },
        )

    @API("adapter.napcat.message.get_friend_msg_history", description="获取私聊消息历史", version="1", public=True)
    async def api_get_friend_msg_history(self, **kwargs: Any) -> Dict[str, Any]:
        """获取私聊消息历史。"""
        params = kwargs.get("params", kwargs)
        return await self._call_action(
            "get_friend_msg_history",
            {
                "user_id": self._normalize_positive_id(params.get("user_id"), "user_id"),
                "count": int(params.get("count", 20)),
            },
        )

    @API("adapter.napcat.system.get_login_info", description="获取当前登录账号信息", version="1", public=True)
    async def api_get_login_info(self, **kwargs: Any) -> Dict[str, Any]:
        """获取 bot 自身 QQ 号与昵称（合并转发节点需要真实 uin）。"""
        del kwargs
        return await self._call_action("get_login_info", {})

    @Tool(
        "open_private_chat",
        description=(
            "向指定 QQ 用户发送一条私聊消息，用于主动开启私聊。"
            "仅在 SnowLuma 配置 enable_private_chat_tool=true 时可用；"
            "发送成功后，该用户在 15 分钟内的私聊入站消息会绕过私聊黑白名单过滤。"
        ),
        parameters=[
            ToolParameterInfo(
                name="user_id",
                param_type=ToolParamType.STRING,
                description="要开启私聊的 QQ 用户 ID，必须是正整数。",
                required=True,
            ),
            ToolParameterInfo(
                name="message",
                param_type=ToolParamType.STRING,
                description="要发送给该用户的第一条私聊消息。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_open_private_chat(
        self,
        user_id: Any = "",
        message: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """主动向指定用户发送私聊消息，并临时放行该私聊。"""

        del kwargs

        settings = self._load_settings()

        if self._ws is None:
            return {"success": False, "error": "SnowLuma WebSocket 尚未连接"}

        try:
            normalized_user_id_int = self._normalize_positive_id(user_id, "user_id")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        normalized_user_id = str(normalized_user_id_int)

        normalized_message = str(message or "").strip()
        if not normalized_message:
            return {"success": False, "error": "私聊消息不能为空"}

        open_session_result = await self.ctx.chat.open_session(
            platform="qq",
            chat_type="private",
            user_id=normalized_user_id,
            account_id=self._connected_account_id,
            scope=settings.luma_client.connection_id,
        )
        if not isinstance(open_session_result, Mapping) or not bool(open_session_result.get("success", False)):
            error = ""
            if isinstance(open_session_result, Mapping):
                error = str(open_session_result.get("error") or "").strip()
            return {
                "success": False,
                "error": error or "打开私聊会话失败",
                "open_session_result": open_session_result,
            }

        response = await self._call_action(
            "send_msg",
            {
                "message_type": "private",
                "user_id": normalized_user_id_int,
                "message": [{"type": "text", "data": {"text": normalized_message}}],
            },
        )
        send_error = self._extract_action_error(response)
        if send_error:
            return {
                "success": False,
                "error": send_error,
                "response": response,
            }

        expires_at = self._grant_private_chat_bypass(normalized_user_id)
        message_id = self._extract_action_message_id(response)
        self.ctx.logger.info(
            f"SnowLuma 已主动开启私聊: user_id={normalized_user_id} "
            f"message_id={message_id or '<unknown>'} bypass_seconds={PRIVATE_CHAT_TOOL_BYPASS_SECONDS}"
        )
        return {
            "success": True,
            "content": (
                f"已向用户 {normalized_user_id} 发送私聊消息，"
                f"并在 {PRIVATE_CHAT_TOOL_BYPASS_SECONDS // 60} 分钟内临时放行该私聊。"
            ),
            "user_id": normalized_user_id,
            "stream_id": str(open_session_result.get("session_id") or open_session_result.get("stream_id") or ""),
            "session": open_session_result.get("stream") or {},
            "message_id": message_id,
            "expires_at": expires_at,
            "bypass_seconds": PRIVATE_CHAT_TOOL_BYPASS_SECONDS,
        }

    @Tool(
        "get_qq_by_msg_id",
        description=(
            "根据当前聊天中的消息 ID 获取该消息发送者的 QQ 用户 ID。"
            "当只知道昵称或需要调用 open_private_chat 但缺少 user_id 时，先调用此工具。"
        ),
        parameters=[
            ToolParameterInfo(
                name="msg_id",
                param_type=ToolParamType.STRING,
                description="目标用户发送的消息 ID。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_get_qq_by_msg_id(
        self,
        msg_id: str = "",
        stream_id: str = "",
        chat_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """根据消息 ID 查询该消息发送者的 QQ 号。"""

        del kwargs

        normalized_msg_id = str(msg_id or "").strip()
        if not normalized_msg_id:
            return {"success": False, "error": "缺少目标消息 ID"}

        target_stream_id = str(stream_id or chat_id or "").strip()
        query_result = await self.ctx.message.get_by_id(
            normalized_msg_id,
            stream_id=target_stream_id,
            include_binary_data=False,
        )
        if not isinstance(query_result, Mapping):
            return {
                "success": False,
                "error": f"未找到消息: {normalized_msg_id}",
                "msg_id": normalized_msg_id,
            }

        user_info = self._extract_message_user_info(query_result)
        user_id = str(user_info.get("user_id") or "").strip()
        if not user_id:
            return {
                "success": False,
                "error": f"消息 {normalized_msg_id} 缺少发送者 QQ 号",
                "msg_id": normalized_msg_id,
            }

        user_nickname = str(user_info.get("user_nickname") or "").strip()
        user_cardname = str(user_info.get("user_cardname") or "").strip()
        display_name = user_cardname or user_nickname or user_id
        message_info = query_result.get("message_info", {})
        if not isinstance(message_info, Mapping):
            message_info = {}
        group_info = message_info.get("group_info", {})
        if not isinstance(group_info, Mapping):
            group_info = {}

        return {
            "success": True,
            "content": f"消息 {normalized_msg_id} 的发送者是 {display_name}，QQ 号为 {user_id}。",
            "msg_id": normalized_msg_id,
            "user_id": user_id,
            "qq": user_id,
            "user_nickname": user_nickname,
            "user_cardname": user_cardname,
            "display_name": display_name,
            "platform": str(query_result.get("platform") or "").strip(),
            "session_id": str(query_result.get("session_id") or target_stream_id or "").strip(),
            "group_id": str(group_info.get("group_id") or "").strip(),
            "group_name": str(group_info.get("group_name") or "").strip(),
        }

    @MessageGateway(
        name=SNOWLUMA_GATEWAY_NAME,
        route_type="duplex",
        platform="qq",
        protocol="snowluma",
        description="SnowLuma WebSocket 双工消息网关",
    )
    async def handle_snowluma_gateway(
        self,
        message: Dict[str, Any],
        route: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理 Host 出站消息并发送到 SnowLuma。"""

        del metadata
        del kwargs

        if self._ws is None:
            return {"success": False, "error": "SnowLuma WebSocket 尚未连接"}

        try:
            action_name, params = self._build_outbound_action(message, route or {})
            response = await self._call_action(action_name, params)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if not isinstance(response, Mapping):
            return {"success": False, "error": "SnowLuma 返回了无效响应"}

        status = str(response.get("status") or "").lower()
        retcode = response.get("retcode")
        if status and status != "ok":
            return {
                "success": False,
                "error": str(response.get("wording") or response.get("message") or "SnowLuma send failed"),
                "metadata": {"retcode": retcode},
            }
        if isinstance(retcode, int) and retcode not in {0, 1}:
            return {
                "success": False,
                "error": str(response.get("wording") or response.get("message") or "SnowLuma send failed"),
                "metadata": {"retcode": retcode},
            }

        response_data = response.get("data", {})
        internal_message_id = str(message.get("message_id") or "").strip()
        external_message_id = ""
        if isinstance(response_data, Mapping):
            external_message_id = str(response_data.get("message_id") or "")

        adapter_callbacks = []
        if internal_message_id and external_message_id and internal_message_id != external_message_id:
            adapter_callbacks.append(
                {
                    "name": "message_id_echo",
                    "payload": {
                        "content": {
                            "type": "echo",
                            "echo": internal_message_id,
                            "actual_id": external_message_id,
                        }
                    },
                }
            )

        return {
            "success": True,
            "external_message_id": external_message_id or None,
            "metadata": {
                "action": action_name,
                "adapter_callbacks": adapter_callbacks,
            },
        }

    def _load_settings(self) -> SnowLumaAdapterSettings:
        """返回当前强类型配置。"""

        return self.config  # type: ignore[return-value]

    async def _sync_private_chat_tool_component_state(self) -> None:
        """按配置同步主动私聊工具组件的启停状态。"""

        enabled = bool(self._load_settings().plugin.enable_private_chat_tool)
        tool_names = ("open_private_chat", "get_qq_by_msg_id")
        try:
            for tool_name in tool_names:
                if enabled:
                    result = await self.ctx.component.enable_component(tool_name, "TOOL")
                else:
                    result = await self.ctx.component.disable_component(tool_name, "TOOL")
                if isinstance(result, Mapping) and not bool(result.get("success", False)):
                    self.ctx.logger.warning(
                        f"SnowLuma 同步主动私聊工具启停状态失败: tool={tool_name} "
                        f"error={result.get('error') or result}"
                    )
        except Exception as exc:
            self.ctx.logger.warning(f"SnowLuma 同步主动私聊工具启停状态失败: {exc}")

    async def _restart_connection_if_needed(self) -> None:
        """根据当前配置重启连接循环。"""

        await self._stop_connection()
        settings = self._load_settings()
        if not settings.should_connect():
            self.ctx.logger.info("SnowLuma 适配器保持空闲状态，因为插件未启用")
            return

        self._stop_event = asyncio.Event()
        self._connection_task = asyncio.create_task(self._run_connection_loop(), name="snowluma-adapter-loop")

    async def _stop_connection(self) -> None:
        """停止连接循环并清理资源。"""

        if self._stop_event is not None:
            self._stop_event.set()

        task = self._connection_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._connection_task = None

        await self._disconnect()
        await self._report_gateway_ready(False)

    async def _run_connection_loop(self) -> None:
        """维持到 SnowLuma 的 WebSocket 连接。"""

        while self._stop_event is not None and not self._stop_event.is_set():
            settings = self._load_settings()
            try:
                await self._connect(settings)
                await self._bootstrap_runtime_state(settings)
                await self._listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ctx.logger.warning(f"SnowLuma 连接异常，稍后重试: {exc}")
            finally:
                await self._disconnect()
                await self._report_gateway_ready(False)

            if self._stop_event is None or self._stop_event.is_set():
                break
            await asyncio.sleep(max(1.0, settings.luma_client.reconnect_delay_sec))

    async def _connect(self, settings: SnowLumaAdapterSettings) -> None:
        """建立 WebSocket 连接。"""

        timeout = ClientTimeout(total=10)
        self._session = ClientSession(timeout=timeout)
        self._ws = await self._session.ws_connect(settings.luma_client.build_ws_url())
        self.ctx.logger.info(f"SnowLuma WebSocket 已连接: {settings.luma_client.build_ws_url()}")

    async def _disconnect(self) -> None:
        """关闭 WebSocket 和未完成动作。"""

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        if self._session is not None:
            await self._session.close()
            self._session = None

        for future in self._response_pool.values():
            if not future.done():
                future.cancel()
        self._response_pool.clear()
        self._connected_account_id = ""

    async def _bootstrap_runtime_state(self, settings: SnowLumaAdapterSettings) -> None:
        """连接建立后激活消息网关路由。"""

        await self._report_gateway_ready(True, settings=settings)

    async def _report_gateway_ready(
        self,
        ready: bool,
        *,
        account_id: str = "",
        settings: Optional[SnowLumaAdapterSettings] = None,
    ) -> bool:
        """向 Host 上报消息网关运行状态。"""

        metadata: Dict[str, Any] = {}
        scope = ""
        if settings is not None:
            metadata["ws_url"] = settings.luma_client.build_ws_url()
            scope = settings.luma_client.connection_id

        try:
            return await self.ctx.gateway.update_state(
                gateway_name=SNOWLUMA_GATEWAY_NAME,
                ready=ready,
                platform="qq",
                account_id=account_id,
                scope=scope,
                metadata=metadata,
            )
        except Exception as exc:
            self.ctx.logger.warning(f"SnowLuma 消息网关状态上报失败: {exc}")
            return False

    async def _listen(self) -> None:
        """监听 SnowLuma 推送。"""

        if self._ws is None:
            return

        async for ws_message in self._ws:
            if ws_message.type == WSMsgType.TEXT:
                await self._handle_text_payload(ws_message.data)
                continue
            if ws_message.type == WSMsgType.BINARY:
                self.ctx.logger.debug("SnowLuma 收到二进制消息，已忽略")
                continue
            if ws_message.type in {WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    async def _handle_text_payload(self, raw_payload: str) -> None:
        """处理 SnowLuma 文本载荷。"""

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            self.ctx.logger.warning(f"SnowLuma 收到非 JSON 文本: {raw_payload[:120]}")
            return

        if not isinstance(payload, dict):
            return

        echo = str(payload.get("echo") or "").strip()
        if echo:
            self._resolve_echo_response(echo, payload)
            return

        post_type = str(payload.get("post_type") or "").strip()
        if self_id := str(payload.get("self_id") or "").strip():
            await self._update_connected_account(self_id)
        if post_type == "message" or "message" in payload:
            asyncio.create_task(self._route_inbound_message(payload), name="snowluma-route-message")

    async def _update_connected_account(self, account_id: str) -> None:
        """从 SnowLuma 推送中更新当前账号 ID。"""

        if not account_id or account_id == self._connected_account_id:
            return
        self._connected_account_id = account_id
        await self._report_gateway_ready(True, account_id=account_id, settings=self._load_settings())

    def _resolve_echo_response(self, echo: str, payload: Dict[str, Any]) -> None:
        """回填动作调用响应。"""

        future = self._response_pool.pop(echo, None)
        if future is not None and not future.done():
            future.set_result(payload)

    async def _call_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用 SnowLuma OneBot 风格动作接口。"""

        if self._ws is None:
            raise RuntimeError("SnowLuma WebSocket 尚未连接")

        settings = self._load_settings()
        echo = uuid4().hex
        future: asyncio.Future[Dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._response_pool[echo] = future

        payload = {"action": action, "params": params, "echo": echo}
        await self._ws.send_str(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(future, timeout=max(1.0, settings.luma_client.action_timeout_sec))
        finally:
            self._response_pool.pop(echo, None)

    @staticmethod
    def _extract_action_error(response: Mapping[str, Any]) -> str:
        """从 SnowLuma 动作响应中提取错误信息；空字符串表示成功。"""

        status = str(response.get("status") or "").strip().lower()
        retcode = response.get("retcode")
        if status and status != "ok":
            return str(response.get("wording") or response.get("message") or "SnowLuma send failed")
        if isinstance(retcode, int) and retcode not in {0, 1}:
            return str(response.get("wording") or response.get("message") or "SnowLuma send failed")
        return ""

    @staticmethod
    def _extract_action_message_id(response: Mapping[str, Any]) -> str:
        """从 SnowLuma 动作响应中提取平台消息 ID。"""

        response_data = response.get("data", {})
        if not isinstance(response_data, Mapping):
            return ""
        return str(response_data.get("message_id") or "").strip()

    @staticmethod
    def _extract_message_user_info(message: Mapping[str, Any]) -> Mapping[str, Any]:
        """从序列化消息中提取发送者信息。"""

        message_info = message.get("message_info", {})
        if not isinstance(message_info, Mapping):
            return {}
        user_info = message_info.get("user_info", {})
        if not isinstance(user_info, Mapping):
            return {}
        return user_info

    def _grant_private_chat_bypass(self, user_id: str) -> float:
        """授予指定用户临时私聊名单放行窗口。"""

        self._purge_expired_private_chat_bypasses()
        expires_at = time.time() + PRIVATE_CHAT_TOOL_BYPASS_SECONDS
        self._private_chat_bypass_expires_at[user_id] = expires_at
        return expires_at

    def _get_private_chat_bypass_remaining_seconds(self, user_id: str) -> float:
        """获取指定用户临时私聊放行窗口的剩余秒数。"""

        self._purge_expired_private_chat_bypasses()
        expires_at = self._private_chat_bypass_expires_at.get(user_id, 0.0)
        return max(0.0, expires_at - time.time())

    def _has_active_private_chat_bypass(self, user_id: str) -> bool:
        """判断指定用户是否处于临时私聊名单放行窗口内。"""

        return self._get_private_chat_bypass_remaining_seconds(user_id) > 0

    def _purge_expired_private_chat_bypasses(self) -> None:
        """清理已过期的临时私聊名单放行记录。"""

        now = time.time()
        expired_user_ids = [
            user_id for user_id, expires_at in self._private_chat_bypass_expires_at.items() if expires_at <= now
        ]
        for user_id in expired_user_ids:
            self._private_chat_bypass_expires_at.pop(user_id, None)

    @staticmethod
    def _normalize_positive_id(value: Any, field_name: str) -> int:
        """规范化 QQ 号、群号等正整数标识。"""

        try:
            normalized_value = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是正整数") from exc
        if normalized_value <= 0:
            raise ValueError(f"{field_name} 必须是正整数")
        return normalized_value

    @staticmethod
    def _normalize_non_negative_int(value: Any, field_name: str) -> int:
        """规范化非负整数参数。"""

        try:
            normalized_value = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是非负整数") from exc
        if normalized_value < 0:
            raise ValueError(f"{field_name} 必须是非负整数")
        return normalized_value

    @staticmethod
    def _normalize_int(value: Any, field_name: str) -> int:
        """规范化任意整数（允许负数）。message_id 等可能是 32 位有符号回绕值。"""

        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是整数") from exc

    @staticmethod
    def _normalize_inbound_reply_id(value: Any) -> str:
        """规范化入站引用消息 ID，过滤 SnowLuma/OneBot 的空引用。"""

        normalized_value = str(value or "").strip()
        if not normalized_value:
            return ""
        try:
            reply_id = int(normalized_value)
        except ValueError:
            return normalized_value
        if reply_id == 0:
            return ""
        return str(reply_id)

    @staticmethod
    def _extract_reply_target_id(raw_message: List[Dict[str, Any]]) -> str:
        """从标准消息段中提取首个引用目标 ID。"""

        for segment in raw_message:
            if not isinstance(segment, dict) or segment.get("type") != "reply":
                continue
            data = segment.get("data")
            if isinstance(data, Mapping):
                target_message_id = str(data.get("target_message_id") or "").strip()
            else:
                target_message_id = str(data or "").strip()
            if target_message_id:
                return target_message_id
        return ""

    async def _route_inbound_message(self, payload: Dict[str, Any]) -> None:
        """将 SnowLuma 入站消息转换为 Host 标准消息并注入。"""

        if not self._is_inbound_message_allowed(payload):
            return

        try:
            message_dict = await self._build_inbound_message_dict(payload)
        except ValueError as exc:
            self.ctx.logger.warning(f"SnowLuma 入站消息格式不受支持，已丢弃: {exc}")
            return

        external_message_id = str(payload.get("message_id") or "").strip()
        route_metadata: Dict[str, Any] = {}
        if self._connected_account_id:
            route_metadata["self_id"] = self._connected_account_id
        if connection_id := self._load_settings().luma_client.connection_id:
            route_metadata["connection_id"] = connection_id

        accepted = await self.ctx.gateway.route_message(
            gateway_name=SNOWLUMA_GATEWAY_NAME,
            message=message_dict,
            route_metadata=route_metadata,
            external_message_id=external_message_id,
            dedupe_key=external_message_id,
        )
        if not accepted:
            self.ctx.logger.debug(f"Host 丢弃了 SnowLuma 入站消息: {external_message_id or '无消息 ID'}")

    def _is_inbound_message_allowed(self, payload: Mapping[str, Any]) -> bool:
        """检查入站消息是否通过聊天黑白名单过滤。"""

        settings = self._load_settings()
        sender = payload.get("sender", {})
        if not isinstance(sender, Mapping):
            sender = {}

        sender_user_id = str(payload.get("user_id") or sender.get("user_id") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        if not sender_user_id:
            return False

        if (
            settings.filters.ignore_self_message
            and self._connected_account_id
            and sender_user_id == self._connected_account_id
        ):
            return False

        if sender_user_id in settings.chat.ban_user_id:
            self.ctx.logger.warning(f"SnowLuma 用户 {sender_user_id} 在全局禁止名单中，消息已丢弃")
            return False

        if settings.chat.ban_qq_bot and self._is_official_qq_bot_payload(payload, sender):
            self.ctx.logger.debug(f"SnowLuma 官方机器人消息已丢弃: user_id={sender_user_id}")
            return False

        if not group_id and self._has_active_private_chat_bypass(sender_user_id):
            remaining_seconds = self._get_private_chat_bypass_remaining_seconds(sender_user_id)
            self.ctx.logger.debug(
                f"SnowLuma 私聊用户 {sender_user_id} 命中主动私聊临时放行，"
                f"剩余 {remaining_seconds:.0f} 秒"
            )
            return True

        if not settings.chat.enable_chat_list_filter:
            return True

        if group_id:
            allowed = self._is_id_allowed_by_list_policy(
                group_id,
                settings.chat.group_list_type,
                settings.chat.group_list,
            )
            if not allowed:
                self._log_chat_list_rejection(
                    settings.chat.show_dropped_chat_list_messages,
                    f"SnowLuma 群聊 {group_id} 未通过聊天名单过滤，消息已丢弃",
                )
            return allowed

        allowed = self._is_id_allowed_by_list_policy(
            sender_user_id,
            settings.chat.private_list_type,
            settings.chat.private_list,
        )
        if not allowed:
            self._log_chat_list_rejection(
                settings.chat.show_dropped_chat_list_messages,
                f"SnowLuma 私聊用户 {sender_user_id} 未通过聊天名单过滤，消息已丢弃",
            )
        return allowed

    def _log_chat_list_rejection(self, enabled: bool, message: str) -> None:
        """按配置决定是否记录聊天名单过滤丢弃日志。"""

        if enabled:
            self.ctx.logger.warning(message)

    @staticmethod
    def _is_id_allowed_by_list_policy(target_id: str, list_type: str, configured_ids: List[str]) -> bool:
        """根据白名单或黑名单规则判断目标 ID 是否允许通过。"""

        if list_type == "whitelist":
            return target_id in configured_ids
        return target_id not in configured_ids

    @staticmethod
    def _is_official_qq_bot_payload(payload: Mapping[str, Any], sender: Mapping[str, Any]) -> bool:
        """尽力识别 QQ 官方机器人或频道机器人消息。"""

        role_values = {
            str(payload.get("sub_type") or "").lower(),
            str(payload.get("message_sub_type") or "").lower(),
            str(sender.get("role") or "").lower(),
            str(sender.get("user_type") or "").lower(),
        }
        if role_values & {"qq_bot", "official_bot", "bot", "guild"}:
            return True

        sender_title = str(sender.get("title") or sender.get("card") or sender.get("nickname") or "").lower()
        return "官方机器人" in sender_title or "qq bot" in sender_title

    async def _build_inbound_message_dict(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """构造 Host 可接受的 MessageDict。"""

        sender = payload.get("sender", {})
        if not isinstance(sender, Mapping):
            sender = {}

        user_id = str(payload.get("user_id") or sender.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("缺少 user_id")

        message_type = str(payload.get("message_type") or "").strip()
        if message_type not in {"private", "group"}:
            raise ValueError(f"不支持或缺少 message_type: {message_type or '<empty>'}")
        group_id = str(payload.get("group_id") or "").strip()
        if message_type == "group" and not group_id:
            raise ValueError("群消息缺少 group_id")
        user_nickname = str(sender.get("nickname") or sender.get("card") or user_id).strip() or user_id
        user_cardname = str(sender.get("card") or "").strip() or None

        inbound_raw_message = payload.get("message")
        if self._load_settings().plugin.enable_ada_debug_raw_message_log:
            self.ctx.logger.info(
                "SnowLuma 入站原始消息段: "
                f"message_id={payload.get('message_id')!r} "
                f"message={json.dumps(inbound_raw_message, ensure_ascii=False, default=str)}"
            )

        raw_message, plain_text, is_at, is_picture = await self._convert_inbound_segments(inbound_raw_message)
        if not raw_message:
            raise ValueError("消息内容为空或没有可转换的消息段")

        timestamp_seconds = payload.get("time")
        if not isinstance(timestamp_seconds, (int, float)) or timestamp_seconds <= 0:
            timestamp_seconds = time.time()

        additional_config: Dict[str, Any] = {
            "self_id": self._connected_account_id,
            "snowluma_message_type": message_type,
        }
        if message_type == "group":
            additional_config["platform_io_target_group_id"] = group_id
        else:
            additional_config["platform_io_target_user_id"] = user_id

        message_info: Dict[str, Any] = {
            "user_info": {
                "user_id": user_id,
                "user_nickname": user_nickname,
                "user_cardname": user_cardname,
            },
            "additional_config": additional_config,
        }
        if message_type == "group":
            group_name = await self._resolve_group_name(payload, group_id)
            message_info["group_info"] = {"group_id": group_id, "group_name": group_name}

        message_id = str(payload.get("message_id") or "").strip()
        if not message_id:
            raise ValueError("缺少 message_id")
        message_dict: Dict[str, Any] = {
            "message_id": message_id,
            "timestamp": str(float(timestamp_seconds)),
            "platform": "qq",
            "message_info": message_info,
            "raw_message": raw_message,
            "is_mentioned": is_at,
            "is_at": is_at,
            "is_emoji": False,
            "is_picture": is_picture,
            "is_command": plain_text.startswith("/"),
            "is_notify": False,
            "session_id": "",
            "processed_plain_text": plain_text,
        }
        reply_to = self._extract_reply_target_id(raw_message)
        if reply_to:
            message_dict["reply_to"] = reply_to
        return message_dict

    async def _resolve_group_name(self, payload: Mapping[str, Any], group_id: str) -> str:
        """解析群名称，优先使用推送字段，缺失时查询 SnowLuma。"""

        raw_group_name = str(payload.get("group_name") or "").strip()
        if raw_group_name:
            self._group_name_cache[group_id] = raw_group_name
            return raw_group_name

        cached_group_name = self._group_name_cache.get(group_id, "")
        if cached_group_name:
            return cached_group_name

        try:
            response = await self._call_action("get_group_info", {"group_id": group_id})
        except Exception as exc:
            self.ctx.logger.debug(f"SnowLuma 查询群名称失败: group_id={group_id} error={exc}")
            return f"group_{group_id}"

        group_info = response.get("data", response)
        if isinstance(group_info, Mapping):
            resolved_group_name = str(group_info.get("group_name") or "").strip()
            if resolved_group_name:
                self._group_name_cache[group_id] = resolved_group_name
                return resolved_group_name

        return f"group_{group_id}"

    async def _resolve_group_member_names(self, group_id: str, user_id: str) -> Dict[str, str]:
        """通过 SnowLuma 查询群成员名片和昵称。"""

        normalized_group_id = str(group_id or "").strip()
        normalized_user_id = str(user_id or "").strip()
        if not normalized_group_id or not normalized_user_id:
            return {}

        cache_key = (normalized_group_id, normalized_user_id)
        if cache_key in self._group_member_cache:
            return self._group_member_cache[cache_key]

        try:
            response = await self._call_action(
                "get_group_member_info",
                {
                    "group_id": self._normalize_positive_id(normalized_group_id, "group_id"),
                    "user_id": self._normalize_positive_id(normalized_user_id, "user_id"),
                    "no_cache": True,
                },
            )
        except Exception as exc:
            self.ctx.logger.debug(
                "SnowLuma 查询转发节点发送者信息失败: "
                f"group_id={normalized_group_id} user_id={normalized_user_id} error={exc}"
            )
            self._group_member_cache[cache_key] = {}
            return {}

        if self._load_settings().plugin.enable_ada_debug_raw_message_log:
            self.ctx.logger.info(
                "SnowLuma 转发节点群成员信息响应: "
                f"group_id={normalized_group_id!r} user_id={normalized_user_id!r} "
                f"response={json.dumps(response, ensure_ascii=False, default=str)}"
            )

        member_info = response.get("data", response)
        if not isinstance(member_info, Mapping):
            self._group_member_cache[cache_key] = {}
            return {}

        resolved_names = self._extract_member_name_fields(member_info)
        self._group_member_cache[cache_key] = resolved_names
        return resolved_names

    @staticmethod
    def _extract_member_name_fields(member_info: Mapping[str, Any]) -> Dict[str, str]:
        """从 SnowLuma/NapCat 用户信息字段中提取名片和昵称。"""

        resolved_names: Dict[str, str] = {}
        cardname = str(member_info.get("card") or "").strip()
        nickname = str(member_info.get("nickname") or "").strip()
        if cardname:
            resolved_names["card"] = cardname
        if nickname:
            resolved_names["nickname"] = nickname
        return resolved_names

    async def _convert_inbound_segments(self, raw_message: Any) -> Tuple[List[Dict[str, Any]], str, bool, bool]:
        """转换 OneBot 消息段为 Host 消息段。"""

        if isinstance(raw_message, str):
            return ([{"type": "text", "data": raw_message}], raw_message, False, False)

        if not isinstance(raw_message, list):
            return ([], "", False, False)

        segments: List[Dict[str, Any]] = []
        plain_text_parts: List[str] = []
        is_at = False
        is_picture = False
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            item_type = str(item.get("type") or "").strip()
            item_data = item.get("data", {})
            if not isinstance(item_data, Mapping):
                item_data = {}

            if item_type == "text":
                text = str(item_data.get("text") or "")
                if text:
                    segments.append({"type": "text", "data": text})
                    plain_text_parts.append(text)
                continue

            if item_type == "at":
                target_user_id = str(item_data.get("qq") or "").strip()
                if target_user_id:
                    segments.append(
                        {
                            "type": "at",
                            "data": {
                                "target_user_id": target_user_id,
                                "target_user_nickname": None,
                                "target_user_cardname": None,
                            },
                        }
                    )
                    plain_text_parts.append(f"@{target_user_id}")
                    if self._connected_account_id and target_user_id == self._connected_account_id:
                        is_at = True
                continue

            if item_type == "reply":
                target_message_id = self._normalize_inbound_reply_id(item_data.get("id"))
                if target_message_id:
                    segments.append({"type": "reply", "data": {"target_message_id": target_message_id}})
                continue

            if item_type == "image":
                image_ref = str(item_data.get("url") or item_data.get("file") or "").strip()
                is_emoji_segment = self._is_emoji_image_segment(item_data)
                image_segment = await self._build_inbound_binary_segment(
                    "emoji" if is_emoji_segment else "image",
                    image_ref,
                    "[emoji]" if is_emoji_segment else "[image]",
                    item_data,
                )
                segments.append(image_segment)
                plain_text_parts.append("[image]")
                is_picture = True
                continue

            if item_type == "record":
                voice_ref = str(item_data.get("url") or item_data.get("file") or "").strip()
                voice_segment = await self._build_inbound_binary_segment("voice", voice_ref, "[voice]", item_data)
                segments.append(voice_segment)
                plain_text_parts.append("[voice]")
                continue

            if item_type == "file":
                file_text = self._build_inbound_file_text(item_data)
                segments.append(
                    {
                        "type": "dict",
                        "data": {
                            "type": "file",
                            "data": self._build_inbound_file_payload(item_data),
                        },
                    }
                )
                plain_text_parts.append(file_text)
                continue

            if item_type == "json":
                json_text = self._build_inbound_json_card_text(item_data)
                segments.append({"type": "text", "data": json_text})
                plain_text_parts.append(json_text)
                continue

            if item_type in {"face", "emoji"}:
                text = self._build_inbound_face_text(item_data)
                segments.append({"type": "text", "data": text})
                plain_text_parts.append(text)
                continue

            if item_type == "forward":
                forward_segment = await self._build_inbound_forward_segment(item_data)
                segments.append(forward_segment)
                plain_text_parts.append(self._build_forward_plain_text(forward_segment))
                continue

            unknown_type = item_type or "unknown"
            segments.append({"type": "dict", "data": {"type": unknown_type, "data": dict(item_data)}})
            plain_text_parts.append(f"[{unknown_type}]")

        return segments, "".join(plain_text_parts), is_at, is_picture

    def _build_inbound_face_text(self, segment_data: Mapping[str, Any]) -> str:
        """把 QQ 自带表情 face 段转成可读文本或近似 Unicode emoji。"""

        face_id = str(segment_data.get("id") or "").strip()
        if not face_id:
            return "[QQ表情]"

        settings = self._load_settings()
        if settings.plugin.qq_face_parse_mode == "emoji":
            emoji_text = QQ_FACE_EMOJIS.get(face_id)
            if emoji_text:
                return emoji_text

        description = QQ_FACE_DESCRIPTIONS.get(face_id)
        if description:
            return f"[{description}]"
        return f"[QQ表情:{face_id}]"

    @staticmethod
    def _build_inbound_file_text(segment_data: Mapping[str, Any]) -> str:
        """把 OneBot 文件段转成可读文本。"""

        file_name = str(
            segment_data.get("file")
            or segment_data.get("name")
            or segment_data.get("file_name")
            or segment_data.get("filename")
            or ""
        ).strip()
        file_size = str(segment_data.get("file_size") or segment_data.get("size") or "").strip()
        file_url = str(segment_data.get("url") or segment_data.get("file_url") or "").strip()

        text_parts: List[str] = []
        if file_name:
            text_parts.append(file_name)
        if file_size:
            text_parts.append(f"大小: {file_size}")

        file_text = "[文件]"
        if text_parts:
            file_text = f"[文件] {'，'.join(text_parts)}"
        if file_url:
            file_text = f"{file_text}，链接: {file_url}"
        return file_text

    @staticmethod
    def _build_inbound_file_payload(segment_data: Mapping[str, Any]) -> Dict[str, Any]:
        """保留 OneBot 文件段的结构化信息，供复杂消息工具展开。"""

        file_name = str(
            segment_data.get("file")
            or segment_data.get("name")
            or segment_data.get("file_name")
            or segment_data.get("filename")
            or ""
        ).strip()
        file_size = str(segment_data.get("file_size") or segment_data.get("size") or "").strip()
        file_url = str(segment_data.get("url") or segment_data.get("file_url") or "").strip()
        file_id = str(segment_data.get("file_id") or segment_data.get("id") or "").strip()

        payload: Dict[str, Any] = {}
        if file_name:
            payload["name"] = file_name
            payload["file"] = file_name
        if file_size:
            payload["size"] = file_size
            payload["file_size"] = file_size
        if file_url:
            payload["url"] = file_url
        if file_id:
            payload["file_id"] = file_id
        return payload

    def _build_inbound_json_card_text(self, segment_data: Mapping[str, Any]) -> str:
        """把 OneBot JSON 卡片转成可读文本摘要。"""

        raw_json = str(segment_data.get("data") or "").strip()
        if not raw_json:
            return "[json]"

        try:
            parsed_json = json.loads(raw_json)
        except Exception:
            return "[json]"

        if not isinstance(parsed_json, Mapping):
            return "[json]"

        prompt = str(parsed_json.get("prompt") or "").strip()
        app_name = str(parsed_json.get("app") or "").strip()
        meta = parsed_json.get("meta", {})
        if not isinstance(meta, Mapping):
            meta = {}

        card_parts = self._extract_json_card_parts(meta)
        title = card_parts.get("title", "")
        desc = card_parts.get("desc", "")
        url = card_parts.get("url", "")
        tag = card_parts.get("tag", "") or prompt or app_name or "json"

        text_parts: List[str] = [f"[卡片:{tag}]"]
        if title and title not in text_parts:
            text_parts.append(title)
        if desc and desc != title:
            text_parts.append(desc)
        if url:
            text_parts.append(f"链接: {url}")
        return " ".join(part for part in text_parts if part).strip() or "[json]"

    def _extract_json_card_parts(self, meta: Mapping[str, Any]) -> Dict[str, str]:
        """从常见 QQ JSON 卡片 meta 中提取标题、描述、链接。"""

        for nested_value in meta.values():
            if not isinstance(nested_value, Mapping):
                continue

            title = str(
                nested_value.get("title")
                or nested_value.get("name")
                or nested_value.get("prompt")
                or nested_value.get("text")
                or ""
            ).strip()
            desc = str(
                nested_value.get("desc")
                or nested_value.get("summary")
                or nested_value.get("forwardMessage")
                or nested_value.get("content")
                or ""
            ).strip()
            url = str(
                nested_value.get("url")
                or nested_value.get("jumpUrl")
                or nested_value.get("qqdocurl")
                or nested_value.get("musicUrl")
                or ""
            ).strip()
            tag = str(nested_value.get("tag") or nested_value.get("tagName") or "").strip()
            if title or desc or url or tag:
                return {"title": title, "desc": desc, "url": url, "tag": tag}

        return {"title": "", "desc": "", "url": "", "tag": ""}

    def _build_forward_plain_text(self, forward_segment: Mapping[str, Any]) -> str:
        """为合并转发构造可读摘要，避免上下文里只剩 ``[forward]``。"""

        if forward_segment.get("type") != "forward":
            return str(forward_segment.get("data") or "[forward]")

        raw_nodes = forward_segment.get("data")
        if not isinstance(raw_nodes, list) or not raw_nodes:
            return "[forward]"

        preview_lines: List[str] = ["【合并转发消息:"]
        for raw_node in raw_nodes[:8]:
            if not isinstance(raw_node, Mapping):
                continue

            sender_name = str(
                raw_node.get("user_cardname")
                or raw_node.get("user_nickname")
                or raw_node.get("user_id")
                or "未知用户"
            )
            content_text = self._build_forward_node_plain_text(raw_node.get("content"))
            preview_lines.append(f"【{sender_name}】: {content_text or '[empty]'}")

        total_count = len(raw_nodes)
        if total_count > 8:
            preview_lines.append(f"... 其余 {total_count - 8} 条已省略")
        preview_lines.append("】")
        return "\n".join(preview_lines)

    def _build_forward_node_plain_text(self, raw_content: Any) -> str:
        """把单个转发节点的 Host 消息段渲染成轻量文本。"""

        if not isinstance(raw_content, list):
            return ""

        text_parts: List[str] = []
        for segment in raw_content:
            if not isinstance(segment, Mapping):
                continue

            segment_type = str(segment.get("type") or "").strip()
            segment_data = segment.get("data")
            if segment_type == "text":
                text_parts.append(str(segment_data or ""))
                continue

            if segment_type == "at":
                if isinstance(segment_data, Mapping):
                    target_name = str(
                        segment_data.get("target_user_cardname")
                        or segment_data.get("target_user_nickname")
                        or segment_data.get("target_user_id")
                        or ""
                    ).strip()
                else:
                    target_name = str(segment_data or "").strip()
                if target_name:
                    text_parts.append(f"@{target_name}")
                continue

            if segment_type == "image":
                text_parts.append("[image]")
                continue

            if segment_type == "emoji":
                text_parts.append("[emoji]")
                continue

            if segment_type == "voice":
                text_parts.append("[voice]")
                continue

            if segment_type == "reply":
                text_parts.append("[reply]")
                continue

            if segment_type == "forward":
                text_parts.append("[forward]")
                continue

            if segment_type:
                text_parts.append(f"[{segment_type}]")

        return "".join(text_parts)

    async def _build_inbound_forward_segment(self, segment_data: Mapping[str, Any]) -> Dict[str, Any]:
        """展开 OneBot 合并转发消息段。"""

        messages = self._extract_forward_messages(segment_data)
        if messages is None:
            forward_id = str(segment_data.get("id") or "").strip()
            if not forward_id:
                return {"type": "text", "data": "[forward]"}

            try:
                response = await self._call_action("get_forward_msg", {"id": forward_id})
            except Exception as exc:
                self.ctx.logger.debug(f"SnowLuma 获取合并转发详情失败: id={forward_id} error={exc}")
                return {"type": "text", "data": "[forward]"}

            if self._load_settings().plugin.enable_ada_debug_raw_message_log:
                self.ctx.logger.info(
                    "SnowLuma 合并转发详情响应: "
                    f"id={forward_id!r} response={json.dumps(response, ensure_ascii=False, default=str)}"
                )

            messages = self._extract_forward_messages(response)

        if not isinstance(messages, list):
            return {"type": "text", "data": "[forward]"}

        forward_nodes = await self._build_inbound_forward_nodes(messages)
        if not forward_nodes:
            return {"type": "text", "data": "[forward]"}

        return {"type": "forward", "data": forward_nodes}

    def _extract_forward_messages(self, payload: Mapping[str, Any]) -> Optional[List[Any]]:
        """从合并转发载荷中提取节点列表。"""

        direct_messages = payload.get("messages")
        if isinstance(direct_messages, list):
            return direct_messages

        direct_content = payload.get("content")
        if isinstance(direct_content, list):
            return direct_content

        nested_data = payload.get("data")
        if isinstance(nested_data, Mapping):
            nested_messages = nested_data.get("messages")
            if isinstance(nested_messages, list):
                return nested_messages

            nested_content = nested_data.get("content")
            if isinstance(nested_content, list):
                return nested_content

        return None

    async def _build_inbound_forward_nodes(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """转换 SnowLuma/NapCat 返回的合并转发节点。"""

        forward_nodes: List[Dict[str, Any]] = []
        for forward_message in messages:
            if not isinstance(forward_message, Mapping):
                continue

            raw_content = self._extract_forward_node_content(forward_message)
            content_segments, _, _, _ = await self._convert_inbound_segments(raw_content)
            if not content_segments:
                continue

            sender = self._extract_forward_node_sender(forward_message)
            node_data = forward_message.get("data", {})
            if not isinstance(node_data, Mapping):
                node_data = {}

            node_payload = self._extract_forward_node_payload(forward_message)
            node_user_id = str(
                sender.get("user_id")
                or sender.get("uin")
                or sender.get("id")
                or node_payload.get("user_id")
                or node_payload.get("uin")
                or node_payload.get("id")
                or node_data.get("user_id")
                or node_data.get("uin")
                or node_data.get("id")
                or ""
            ).strip()
            node_cardname = str(sender.get("card") or node_payload.get("card") or node_data.get("card") or "").strip()
            node_nickname = str(
                sender.get("nickname")
                or sender.get("name")
                or node_payload.get("nickname")
                or node_payload.get("name")
                or node_data.get("nickname")
                or node_data.get("name")
                or ""
            ).strip()
            node_group_id = str(
                forward_message.get("group_id")
                or node_payload.get("group_id")
                or node_data.get("group_id")
                or ""
            ).strip()
            if node_user_id and node_group_id and (not node_cardname or not node_nickname):
                resolved_names = await self._resolve_group_member_names(node_group_id, node_user_id)
                node_cardname = node_cardname or resolved_names.get("card", "")
                node_nickname = node_nickname or resolved_names.get("nickname", "")

            forward_nodes.append(
                {
                    "user_id": node_user_id or None,
                    "user_nickname": node_nickname or node_user_id or "未知用户",
                    "user_cardname": node_cardname or None,
                    "message_id": str(
                        forward_message.get("message_id")
                        or forward_message.get("id")
                        or node_payload.get("message_id")
                        or node_payload.get("id")
                        or node_data.get("id")
                        or ""
                    ),
                    "content": content_segments,
                }
            )
        return forward_nodes

    @staticmethod
    def _extract_forward_node_payload(forward_message: Mapping[str, Any]) -> Mapping[str, Any]:
        """提取 OneBot ``node`` 段内层 ``data`` 作为节点主体。"""

        if str(forward_message.get("type") or "").strip() == "node":
            node_data = forward_message.get("data", {})
            if isinstance(node_data, Mapping):
                return node_data
        return forward_message

    @staticmethod
    def _extract_forward_node_content(forward_message: Mapping[str, Any]) -> Any:
        """提取单个合并转发节点中的消息段列表。"""

        direct_content = forward_message.get("content")
        if isinstance(direct_content, list):
            return direct_content

        direct_message = forward_message.get("message")
        if isinstance(direct_message, list):
            return direct_message

        node_data = forward_message.get("data", {})
        if not isinstance(node_data, Mapping):
            return []

        nested_content = node_data.get("content")
        if isinstance(nested_content, list):
            return nested_content

        nested_message = node_data.get("message")
        if isinstance(nested_message, list):
            return nested_message

        return []

    @staticmethod
    def _extract_forward_node_sender(forward_message: Mapping[str, Any]) -> Mapping[str, Any]:
        """提取单个合并转发节点的发送者信息。"""

        sender = forward_message.get("sender", {})
        if isinstance(sender, Mapping):
            return sender
        if isinstance(sender, str) and sender.strip():
            return {"nickname": sender.strip(), "name": sender.strip()}

        node_data = forward_message.get("data", {})
        if not isinstance(node_data, Mapping):
            return {}

        normalized_sender: Dict[str, Any] = {}
        user_id = str(node_data.get("user_id") or node_data.get("uin") or node_data.get("id") or "").strip()
        nickname = str(node_data.get("nickname") or node_data.get("name") or node_data.get("card") or "").strip()
        cardname = str(node_data.get("card") or "").strip()
        if user_id:
            normalized_sender["user_id"] = user_id
            normalized_sender["uin"] = user_id
        if nickname:
            normalized_sender["nickname"] = nickname
            normalized_sender["name"] = nickname
        if cardname:
            normalized_sender["card"] = cardname
        return normalized_sender

    async def _build_inbound_binary_segment(
        self,
        segment_type: str,
        file_reference: str,
        fallback_text: str,
        segment_data: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构造 Host 可识别的入站媒体段。"""

        if segment_type == "voice" and segment_data is not None:
            binary_data = await self._load_binary_from_segment_data(segment_type, segment_data)
            if not binary_data:
                binary_data = await self._load_binary_reference(file_reference)
        else:
            binary_data = await self._load_binary_reference(file_reference)
            if not binary_data and segment_data is not None:
                binary_data = await self._load_binary_from_segment_data(segment_type, segment_data)
        if not binary_data:
            self.ctx.logger.debug(f"SnowLuma 媒体下载失败，降级为文本: type={segment_type} ref={file_reference[:120]}")
            return {"type": "text", "data": fallback_text}
        if segment_type == "voice" and self._is_silk_voice_binary(binary_data):
            transcoded_binary = await self._transcode_silk_voice_binary(binary_data)
            if not transcoded_binary:
                self.ctx.logger.warning(
                    "SnowLuma 收到 Silk 语音数据，get_record 未返回通用音频，且本地 Silk 转码失败，已降级为文本占位"
                )
                return {"type": "text", "data": fallback_text}
            binary_data = transcoded_binary

        return {
            "type": segment_type,
            "data": "",
            "hash": self._hash_binary(binary_data),
            "binary_data_base64": self._encode_binary(binary_data),
        }

    async def _load_binary_reference(self, file_reference: str) -> bytes:
        """加载 OneBot 媒体引用中的二进制内容。"""

        normalized_reference = str(file_reference or "").strip()
        if not normalized_reference:
            return b""

        if normalized_reference.startswith("base64://"):
            try:
                return base64.b64decode(normalized_reference.removeprefix("base64://"))
            except Exception:
                return b""

        if normalized_reference.startswith(("http://", "https://")):
            session = self._session
            if session is None:
                return b""
            try:
                async with session.get(normalized_reference) as response:
                    if response.status >= 400:
                        return b""
                    return await response.read()
            except Exception as exc:
                self.ctx.logger.debug(f"SnowLuma 下载媒体失败: {exc}")
                return b""

        try:
            reference_path = Path(normalized_reference)
            if reference_path.is_file():
                return await asyncio.to_thread(reference_path.read_bytes)
        except Exception as exc:
            self.ctx.logger.debug(f"SnowLuma 读取本地媒体失败: path={normalized_reference[:120]} error={exc}")
            return b""

        return b""

    async def _load_binary_from_segment_data(self, segment_type: str, segment_data: Mapping[str, Any]) -> bytes:
        """从媒体段的标准引用字段或 OneBot 动作中加载二进制内容。"""

        if segment_type == "voice":
            binary_data = await self._load_binary_from_onebot_action(segment_type, segment_data)
            if binary_data:
                return binary_data

        for field_name in ("base64", "data"):
            raw_value = segment_data.get(field_name)
            if not isinstance(raw_value, str) or not raw_value.strip():
                continue
            normalized_value = raw_value.strip()
            if normalized_value.startswith("base64://"):
                normalized_value = normalized_value.removeprefix("base64://")
            try:
                return base64.b64decode(normalized_value, validate=True)
            except Exception:
                continue

        for field_name in ("url", "path", "file_path"):
            binary_data = await self._load_binary_reference(str(segment_data.get(field_name) or ""))
            if binary_data:
                return binary_data

        return await self._load_binary_from_onebot_action(segment_type, segment_data)

    async def _load_binary_from_onebot_action(self, segment_type: str, segment_data: Mapping[str, Any]) -> bytes:
        """通过 OneBot 动作加载媒体，语音交给 get_record 转码路径。"""

        if segment_type == "voice":
            return await self._load_voice_binary_from_onebot_action(segment_data)

        file_name = str(segment_data.get("file") or "").strip()
        if not file_name:
            return b""

        action_name = "get_image"
        params: Dict[str, Any] = {"file": file_name}

        try:
            response = await self._call_action(action_name, params)
        except Exception as exc:
            self.ctx.logger.debug(
                f"SnowLuma 通过动作加载媒体失败: action={action_name} type={segment_type} file={file_name} error={exc}"
            )
            return b""

        if self._load_settings().plugin.enable_ada_debug_raw_message_log:
            self.ctx.logger.info(
                "SnowLuma 媒体动作响应: "
                f"action={action_name!r} type={segment_type!r} file={file_name!r} "
                f"response={json.dumps(response, ensure_ascii=False, default=str)}"
            )

        return await self._extract_binary_from_action_response(response)

    async def _load_voice_binary_from_onebot_action(self, segment_data: Mapping[str, Any]) -> bytes:
        """通过 get_record 获取已转码语音。"""

        params = self._build_voice_record_action_params(segment_data)
        if params is None:
            return b""

        try:
            response = await self._call_action("get_record", params)
        except Exception as exc:
            self.ctx.logger.debug(f"SnowLuma 通过 get_record 加载语音失败: params={params} error={exc}")
            return b""

        if self._load_settings().plugin.enable_ada_debug_raw_message_log:
            self.ctx.logger.info(
                "SnowLuma 语音动作响应: "
                f"action='get_record' params={json.dumps(params, ensure_ascii=False, default=str)} "
                f"response={json.dumps(response, ensure_ascii=False, default=str)}"
            )

        binary_data = await self._extract_binary_from_action_response(response)
        if binary_data:
            if self._is_silk_voice_binary(binary_data):
                response_data = response.get("data", {})
                if not isinstance(response_data, Mapping):
                    response_data = {}
                returned_file = str(response_data.get("file") or "")[:120]
                returned_file_name = str(response_data.get("file_name") or "")
                self.ctx.logger.debug(
                    "SnowLuma get_record 返回的媒体仍是 Silk 原始数据: "
                    f"params={params} file_name={returned_file_name!r} file={returned_file!r}"
                )
            return binary_data
        return b""

    async def _extract_binary_from_action_response(self, response: Mapping[str, Any]) -> bytes:
        """从 OneBot 动作响应中提取二进制媒体内容。"""

        response_data = response.get("data", response)
        if not isinstance(response_data, Mapping):
            return b""

        return await self._load_binary_reference(str(response_data.get("file") or ""))

    @staticmethod
    def _build_voice_record_action_params(segment_data: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """构造 OneBot get_record 请求参数。"""

        file_name = str(segment_data.get("file") or "").strip()
        if not file_name:
            return None
        return {"file": file_name, "out_format": "mp3"}

    @staticmethod
    def _is_silk_voice_binary(binary_data: bytes) -> bool:
        """判断语音数据是否仍是 QQ Silk，避免误作为通用音频送入 ASR。"""

        return binary_data.startswith(b"#!SILK_V3") or binary_data.startswith(b"\x02#!SILK_V3")

    async def _transcode_silk_voice_binary(self, silk_binary: bytes) -> bytes:
        """把 QQ Silk 语音转成 ASR 更容易识别的 MP3。"""

        pcm_binary = await asyncio.to_thread(self._decode_silk_to_pcm_sync, silk_binary)
        if not pcm_binary:
            self.ctx.logger.warning("SnowLuma 本地 Silk 解码失败：请安装插件依赖 silk-python")
            return b""

        ffmpeg_path = which("ffmpeg")
        if not ffmpeg_path:
            self.ctx.logger.warning("SnowLuma 本地 Silk 转 MP3 失败：未找到 ffmpeg 可执行文件")
            return b""

        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
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
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            mp3_binary, stderr_binary = await asyncio.wait_for(
                process.communicate(pcm_binary),
                timeout=VOICE_TRANSCODE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            self.ctx.logger.warning("SnowLuma 本地 Silk 转 MP3 超时")
            return b""

        if process.returncode != 0:
            stderr_text = stderr_binary.decode("utf-8", errors="ignore").strip()
            self.ctx.logger.warning(f"SnowLuma 本地 Silk 转 MP3 失败: {stderr_text[:200]}")
            return b""

        if not mp3_binary:
            self.ctx.logger.warning("SnowLuma 本地 Silk 转 MP3 失败：ffmpeg 未输出音频数据")
            return b""
        return mp3_binary

    @staticmethod
    def _decode_silk_to_pcm_sync(silk_binary: bytes) -> bytes:
        """用 silk-python 解码 QQ Silk，返回 s16le PCM。"""

        try:
            pysilk = import_module("pysilk")
        except ImportError:
            return b""

        silk_buffer = BytesIO(silk_binary)
        pcm_buffer = BytesIO()
        try:
            pysilk.decode(silk_buffer, pcm_buffer, VOICE_TRANSCODE_SAMPLE_RATE)
        except Exception:
            return b""
        return pcm_buffer.getvalue()

    @staticmethod
    def _is_emoji_image_segment(segment_data: Mapping[str, Any]) -> bool:
        """判断 OneBot image 段是否更像表情包。"""

        raw_sub_type = str(segment_data.get("sub_type") or segment_data.get("subType") or "").strip()
        if raw_sub_type and raw_sub_type not in {"0", "4", "9", "normal"}:
            return True

        summary = str(segment_data.get("summary") or "").strip()
        if "表情" in summary or "emoji" in summary.lower():
            return True

        return False

    def _build_outbound_action(
        self,
        message: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """将 Host 出站消息转换为 SnowLuma 动作。"""

        message_info = message.get("message_info", {})
        if not isinstance(message_info, Mapping):
            message_info = {}

        group_info = message_info.get("group_info", {})
        if not isinstance(group_info, Mapping):
            group_info = {}

        additional_config = message_info.get("additional_config", {})
        if not isinstance(additional_config, Mapping):
            additional_config = {}

        segments = self._convert_outbound_segments(message.get("raw_message", []))
        if not segments:
            raise ValueError("出站消息没有可转换的 OneBot 消息段")
        target_group_id = str(
            group_info.get("group_id")
            or additional_config.get("platform_io_target_group_id")
            or route.get("group_id")
            or route.get("target_group_id")
            or ""
        ).strip()
        if target_group_id:
            return "send_msg", {"message_type": "group", "group_id": target_group_id, "message": segments}

        target_user_id = str(
            additional_config.get("platform_io_target_user_id")
            or additional_config.get("target_user_id")
            or route.get("user_id")
            or route.get("target_user_id")
            or ""
        ).strip()
        if not target_user_id:
            raise ValueError("出站私聊消息缺少 target_user_id")

        return "send_msg", {"message_type": "private", "user_id": target_user_id, "message": segments}

    def _convert_outbound_segments(self, raw_message: Any) -> List[Dict[str, Any]]:
        """将 Host 消息段转换为 OneBot 消息段。"""

        if not isinstance(raw_message, list):
            return []

        segments: List[Dict[str, Any]] = []
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            item_type = str(item.get("type") or "").strip()
            item_data = item.get("data")
            if item_type == "text":
                segments.append({"type": "text", "data": {"text": str(item_data or "")}})
                continue

            if item_type == "at" and isinstance(item_data, Mapping):
                target_user_id = str(item_data.get("target_user_id") or "").strip()
                if target_user_id:
                    segments.append({"type": "at", "data": {"qq": target_user_id}})
                continue

            if item_type == "reply":
                target_message_id = ""
                if isinstance(item_data, Mapping):
                    target_message_id = str(item_data.get("target_message_id") or "").strip()
                else:
                    target_message_id = str(item_data or "").strip()
                normalized_reply_id = self._normalize_outbound_reply_id(target_message_id)
                if normalized_reply_id is not None:
                    segments.append({"type": "reply", "data": {"id": normalized_reply_id}})
                elif target_message_id:
                    self.ctx.logger.debug(f"SnowLuma 跳过无效回复目标消息 ID: {target_message_id}")
                continue

            if item_type in {"image", "emoji"}:
                image_segment = self._build_media_segment("image", item)
                if image_segment:
                    segments.append(image_segment)
                continue

            if item_type == "voice":
                voice_segment = self._build_media_segment("record", item)
                if voice_segment:
                    segments.append(voice_segment)
                continue

            self.ctx.logger.debug(f"SnowLuma 跳过无法转换的出站消息段: type={item_type or 'unknown'}")
        return segments

    @staticmethod
    def _build_media_segment(segment_type: str, item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """构造 OneBot 媒体消息段。"""

        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if binary_base64:
            return {"type": segment_type, "data": {"file": f"base64://{binary_base64}"}}

        item_data = item.get("data")
        file_reference = ""
        if isinstance(item_data, Mapping):
            file_reference = str(item_data.get("file") or item_data.get("url") or "").strip()
        else:
            file_reference = str(item_data or "").strip()

        if not file_reference:
            return None

        if not file_reference.startswith(("base64://", "file://", "http://", "https://")):
            file_reference = f"file://{file_reference}"
        return {"type": segment_type, "data": {"file": file_reference}}

    @staticmethod
    def _normalize_outbound_reply_id(message_id: str) -> Optional[str]:
        """把内部回复目标 ID 转成 SnowLuma 可接受的 OneBot 消息 ID。"""

        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id or normalized_message_id.startswith("snowluma-"):
            return None

        try:
            reply_id = int(normalized_message_id)
        except ValueError:
            return None

        if reply_id == 0:
            return None
        return normalized_message_id

    @staticmethod
    def _encode_binary(binary_data: bytes) -> str:
        """保留给后续二进制媒体扩展使用。"""

        return base64.b64encode(binary_data).decode("utf-8")

    @staticmethod
    def _hash_binary(binary_data: bytes) -> str:
        """保留给后续二进制媒体扩展使用。"""

        return hashlib.sha256(binary_data).hexdigest()


def create_plugin() -> SnowLumaAdapterPlugin:
    """创建 SnowLuma 适配器插件实例。"""

    return SnowLumaAdapterPlugin()
