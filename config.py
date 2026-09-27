"""SnowLuma 适配器（统一 QQ 连接器）配置模型。

同一套配置同时支撑 SnowLuma 与 NapCat 两类客户端：
[client].client_type 决定连接画像（auto 表示连接后自动判定），
会话黑白名单交给宿主 adapter_policy，发送者黑名单由适配器过滤。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Dict, List, Literal, Optional

import logging

from maibot_sdk import Field, PluginConfigBase
from pydantic import ValidationInfo, field_validator, model_validator

from .constants import (
    DEFAULT_ACTION_TIMEOUT_SEC,
    DEFAULT_CLIENT_HOST,
    DEFAULT_CLIENT_PORT,
    DEFAULT_HEARTBEAT_INTERVAL_SEC,
    DEFAULT_RECONNECT_DELAY_SEC,
    SUPPORTED_CONFIG_VERSION,
)

LOGGER = logging.getLogger("snowluma_adapter.config")

CLIENT_TYPE_VALUES = Literal["auto", "napcat", "snowluma"]


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


def _notice_field(
    *,
    label: str,
    description: str,
    order: int,
    label_en: str,
    label_ja: str,
) -> Any:
    """构造通知事件开关字段，统一默认放行与 WebUI 多语言标签。"""

    return Field(
        default=True,
        description=description,
        json_schema_extra={
            "hint": description,
            "i18n": _schema_i18n(label_en=label_en, label_ja=label_ja),
            "label": label,
            "order": order,
        },
    )


class QQPluginOptions(PluginConfigBase):
    """插件级配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用适配器。",
        json_schema_extra={
            "hint": "关闭后插件会保持空闲，不会主动建立 WebSocket 连接。",
            "i18n": _schema_i18n(
                label_en="Enable adapter",
                label_ja="アダプターを有効化",
                hint_en="When disabled, the plugin stays idle and will not open a WebSocket connection.",
                hint_ja="無効にすると、プラグインは待機状態のままになり、WebSocket 接続を開始しません。",
            ),
            "label": "启用适配器",
            "order": 0,
        },
    )
    enable_private_chat_tool: bool = Field(
        default=False,
        description="是否启用主动开启私聊工具。",
        json_schema_extra={
            "hint": "开启后，模型可向指定 QQ 用户发送首条私聊消息；请在宿主适配器策略中放行该私聊。",
            "i18n": _schema_i18n(
                label_en="Enable private chat tool",
                label_ja="個人チャット開始ツールを有効化",
                hint_en=(
                    "When enabled, the model can send the first private message to a user; "
                    "grant the chat in the host adapter policy."
                ),
                hint_ja=(
                    "有効にすると、モデルは指定ユーザーへ最初の個人メッセージを送信できます；"
                    "ホスト側のアダプターポリシーでその個人チャットを許可してください。"
                ),
            ),
            "label": "启用主动私聊工具",
            "order": 1,
        },
    )
    qq_face_parse_mode: Literal["description", "emoji"] = Field(
        default="description",
        description="QQ 自带表情解析模式：转为中文描述或近似 Unicode emoji。",
        json_schema_extra={
            "label": "QQ表情解析模式",
            "hint": "[description]模式会把表情转成[流泪]这种形式[emoji]会转成近似emoji表情。",
            "i18n": _schema_i18n(
                label_en="QQ face parsing",
                label_ja="QQ 標準顔文字の解析",
                hint_en=(
                    "description converts face segments to [流泪]-style text; "
                    "emoji prefers an approximate Unicode emoji."
                ),
                hint_ja=(
                    "description は顔文字を [流泪] 形式のテキストに変換し、"
                    "emoji は近い Unicode 絵文字を優先します。"
                ),
            ),
            "order": 2,
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

    def should_connect(self) -> bool:
        """判断当前配置下是否应当启动连接。

        Returns:
            bool: 若插件连接已启用，则返回 ``True``。
        """

        return self.enabled

    @field_validator("config_version", mode="before")
    @classmethod
    def _normalize_config_version(cls, value: Any) -> str:
        """规范化配置版本字段。

        Args:
            value: 原始配置值。

        Returns:
            str: 去除首尾空白后的配置版本；若为空则回退到当前支持版本。
        """

        normalized_value = _normalize_string(value)
        return normalized_value or SUPPORTED_CONFIG_VERSION


class QQDebugConfig(PluginConfigBase):
    """消息调试配置，各开关默认关闭。"""

    __ui_label__: ClassVar[str] = "调试"
    __ui_order__: ClassVar[int] = 4

    enable_ada_debug_raw_message_log: bool = Field(
        default=False,
        description="调试模式：记录入站原始消息段。",
        json_schema_extra={
            "label": "显示原始消息段",
            "hint": "仅排查消息段结构问题时开启；开启后会记录每条入站消息的原始 message 字段。",
            "i18n": _schema_i18n(
                label_en="Raw inbound debug",
                label_ja="生メッセージデバッグ",
                hint_en="Enable only while debugging segment structure; logs each inbound raw message field at info level.",
                hint_ja="セグメント構造を調査するときだけ有効にしてください。入站 message フィールドを info レベルで記録します。",
            ),
            "order": 0,
        },
    )
    enable_ada_debug_raw_outbound_message_log: bool = Field(
        default=False,
        description="调试模式：记录出站原始发送段。",
        json_schema_extra={
            "label": "显示原始发送段",
            "hint": "仅排查发送消息段结构问题时开启；开启后会记录每条出站消息实际调用的 action 和 params。",
            "i18n": _schema_i18n(
                label_en="Raw outbound debug",
                label_ja="生送信デバッグ",
                hint_en=(
                    "Enable only while debugging outbound segment structure; logs the action and params "
                    "actually sent for each outbound message."
                ),
                hint_ja=(
                    "送信セグメント構造を調査するときだけ有効にしてください。"
                    "各送信メッセージで実際に渡す action と params を記録します。"
                ),
            ),
            "order": 1,
        },
    )

    ignore_self_message: bool = Field(
        default=False,
        description="是否忽略机器人自身发送的消息。",
        json_schema_extra={
            "hint": "开启后会忽略机器人自身发送的消息。",
            "i18n": _schema_i18n(
                label_en="Ignore self messages",
                label_ja="自身のメッセージを無視",
                hint_en="When enabled, messages sent by the bot itself are ignored.",
                hint_ja="有効にすると、Bot 自身が送信したメッセージを無視します。",
            ),
            "label": "忽略自身消息",
            "order": 2,
        },
    )


class QQServerConfig(PluginConfigBase):
    """正向 WebSocket 连接配置（SnowLuma / NapCat 通用）。"""

    __ui_label__: ClassVar[str] = "客户端连接"
    __ui_order__: ClassVar[int] = 1

    client_type: CLIENT_TYPE_VALUES = Field(
        default="auto",
        description="对端客户端类型：auto 连接后自动判定，也可固定为 napcat 或 snowluma。",
        json_schema_extra={
            "hint": "auto模式会自动确定连接的客户端类型",
            "i18n": _schema_i18n(
                label_en="Client type",
                label_ja="クライアント種別",
                hint_en=(
                    "auto detects the peer via get_version_info after each connect; "
                    "a fixed value is cross-checked against the detected implementation."
                ),
                hint_ja=(
                    "auto は接続後に get_version_info で対向を判定します；"
                    "固定値の場合は判定結果と一致するか検証します。"
                ),
            ),
            "label": "客户端类型",
            "order": 0,
        },
    )
    server: str = Field(
        default=DEFAULT_CLIENT_HOST,
        description="OneBot WebSocket 服务主机地址。",
        json_schema_extra={
            "hint": "通常为运行 SnowLuma / 对端的宿主机地址，默认使用本机回环地址。",
            "i18n": _schema_i18n(
                label_en="Server address",
                label_ja="サーバーアドレス",
                hint_en="Usually the host running SnowLuma or NapCat. Defaults to the local loopback address.",
                hint_ja="通常は SnowLuma / NapCat を実行しているホストです。既定ではローカルのループバックアドレスを使用します。",
                placeholder_en="127.0.0.1",
                placeholder_ja="127.0.0.1",
            ),
            "label": "服务地址",
            "order": 1,
            "placeholder": "127.0.0.1",
        },
    )
    port: int = Field(
        default=DEFAULT_CLIENT_PORT,
        description="OneBot WebSocket 服务端口。",
        json_schema_extra={
            "hint": "与对端正向 WebSocket 服务监听端口保持一致。",
            "i18n": _schema_i18n(
                label_en="Port",
                label_ja="ポート",
                hint_en="Keep this consistent with the forward WebSocket listening port.",
                hint_ja="対向の正方向 WebSocket 待受ポートと一致させてください。",
            ),
            "label": "端口",
            "order": 2,
        },
    )
    token: str = Field(
        default="",
        description="访问令牌，未启用鉴权时可留空。",
        json_schema_extra={
            "hint": "若对端开启了访问令牌校验，请在这里填写相同的 token。",
            "i18n": _schema_i18n(
                label_en="Access token",
                label_ja="アクセストークン",
                hint_en="If access token verification is enabled, enter the same token here.",
                hint_ja="アクセストークン検証を有効にしている場合は、同じ token をここに入力してください。",
                placeholder_en="Optional",
                placeholder_ja="空欄可",
            ),
            "input_type": "password",
            "label": "访问令牌",
            "order": 3,
            "placeholder": "可留空",
        },
    )
    heartbeat_interval: float = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SEC,
        description="协议层心跳保活间隔，单位为秒。",
        json_schema_extra={
            "hint": "用于 WebSocket 协议级 ping 保活，必须大于 0。",
            "i18n": _schema_i18n(
                label_en="Heartbeat interval (sec)",
                label_ja="ハートビート間隔（秒）",
                hint_en="Protocol-level WebSocket ping keepalive interval. Must be greater than 0.",
                hint_ja="WebSocket プロトコルレベルの ping 保活間隔です。0 より大きい値にしてください。",
            ),
            "label": "心跳间隔（秒）",
            "order": 4,
            "step": 1,
        },
    )
    reconnect_delay_sec: float = Field(
        default=DEFAULT_RECONNECT_DELAY_SEC,
        description="连接断开后的重连等待时间，单位为秒。",
        json_schema_extra={
            "hint": "连接断开后会等待该时长再尝试重新连接。",
            "i18n": _schema_i18n(
                label_en="Reconnect delay (sec)",
                label_ja="再接続待機（秒）",
                hint_en="After a disconnect, wait this long before trying to reconnect.",
                hint_ja="接続が切断された後、再接続を試すまでこの時間待機します。",
            ),
            "label": "重连等待（秒）",
            "order": 5,
            "step": 1,
        },
    )
    action_timeout_sec: float = Field(
        default=DEFAULT_ACTION_TIMEOUT_SEC,
        description="调用 OneBot 动作接口的超时时间，单位为秒。",
        json_schema_extra={
            "hint": "发送消息、查询信息等动作会在超时后报错。",
            "i18n": _schema_i18n(
                label_en="Action timeout (sec)",
                label_ja="アクションタイムアウト（秒）",
                hint_en="Actions such as sending messages or querying info fail after this timeout.",
                hint_ja="メッセージ送信や情報取得などのアクションは、この時間を超えるとエラーになります。",
            ),
            "label": "动作超时（秒）",
            "order": 6,
            "step": 1,
        },
    )
    connection_id: str = Field(
        default="",
        description="可选连接标识，用于区分多条适配器链路。",
        json_schema_extra={
            "hint": "当存在多条连接时，可用它作为路由作用域标识。",
            "i18n": _schema_i18n(
                label_en="Connection ID",
                label_ja="接続識別子",
                hint_en="When multiple connections exist, use this as the routing scope identifier.",
                hint_ja="複数の接続がある場合、ルーティングスコープの識別子として使用できます。",
                placeholder_en="For example: primary",
                placeholder_ja="例：primary",
            ),
            "label": "连接标识",
            "order": 7,
            "placeholder": "例如：primary",
        },
    )

    def build_ws_url(self) -> str:
        """构造正向 WebSocket 地址（不含鉴权参数，鉴权在传输层按画像附加）。

        Returns:
            str: 供适配器作为客户端连接的 WebSocket 地址。
        """

        return f"ws://{self.server}:{self.port}"

    @field_validator("client_type", mode="before")
    @classmethod
    def _normalize_client_type(cls, value: Any) -> CLIENT_TYPE_VALUES:
        """规范化客户端类型字段。

        Args:
            value: 原始配置值。

        Returns:
            CLIENT_TYPE_VALUES: 合法的客户端类型；非法时回退到 auto。
        """

        normalized_value = _normalize_string(value).lower()
        if normalized_value in {"auto", "napcat", "snowluma"}:
            return normalized_value  # type: ignore[return-value]
        if normalized_value:
            LOGGER.warning(f"无效的 client_type 值 '{value}'，已回退到 'auto'")
        return "auto"

    @field_validator("server", mode="before")
    @classmethod
    def _normalize_server(cls, value: Any) -> str:
        """规范化服务地址字段。

        Args:
            value: 原始配置值。

        Returns:
            str: 去除首尾空白后的服务地址；若为空则回退到默认主机。
        """

        normalized_value = _normalize_string(value)
        return normalized_value or DEFAULT_CLIENT_HOST

    @field_validator("port", mode="before")
    @classmethod
    def _normalize_port(cls, value: Any) -> int:
        """规范化端口字段。

        Args:
            value: 原始配置值。

        Returns:
            int: 合法的正整数端口；非法时回退到默认端口。
        """

        return _normalize_positive_int(value, DEFAULT_CLIENT_PORT)

    @field_validator("token", "connection_id", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        """规范化文本字段。

        Args:
            value: 原始配置值。

        Returns:
            str: 去除首尾空白后的字符串值。
        """

        return _normalize_string(value)

    @field_validator(
        "heartbeat_interval",
        "reconnect_delay_sec",
        "action_timeout_sec",
        mode="before",
    )
    @classmethod
    def _normalize_positive_float_fields(cls, value: Any, info: ValidationInfo) -> float:
        """规范化正浮点数字段。

        Args:
            value: 原始配置值。
            info: Pydantic 字段校验上下文。

        Returns:
            float: 合法的正浮点数；非法时回退到对应默认值。
        """

        default_values: Dict[str, float] = {
            "action_timeout_sec": DEFAULT_ACTION_TIMEOUT_SEC,
            "heartbeat_interval": DEFAULT_HEARTBEAT_INTERVAL_SEC,
            "reconnect_delay_sec": DEFAULT_RECONNECT_DELAY_SEC,
        }
        return _normalize_positive_float(value, default_values[str(info.field_name)])


class QQFilterConfig(PluginConfigBase):
    """消息过滤配置。"""

    __ui_label__: ClassVar[str] = "消息过滤"
    __ui_order__: ClassVar[int] = 2

    ban_user_id: List[str] = Field(
        default_factory=list,
        description="用户黑名单，拦截指定 QQ 用户的群聊和私聊消息。",
        json_schema_extra={
            "label": "用户黑名单",
            "hint": "每项填写一个 QQ 号；消息在解析前丢弃，不传入麦麦。空列表表示不屏蔽。",
            "order": 6,
            "i18n": _schema_i18n(
                label_en="User blacklist",
                label_ja="ユーザーブラックリスト",
                hint_en="One QQ ID per entry. Group and private messages are dropped before parsing. Empty means no blocking.",
                hint_ja="各項目に QQ 番号を入力します。対象ユーザーのグループ・個人メッセージを解析前に破棄します。空の場合はブロックしません。",
            ),
        },
    )
    ban_qq_bot: bool = Field(
        default=False,
        description="是否屏蔽 QQ 官方机器人消息。",
        json_schema_extra={
            "hint": "开启后会忽略来自 QQ 官方机器人或频道机器人的消息。",
            "i18n": _schema_i18n(
                label_en="Block official bots",
                label_ja="公式 Bot をブロック",
                hint_en="When enabled, messages from QQ official bots or channel bots are ignored.",
                hint_ja="有効にすると、QQ 公式 Bot またはチャンネル Bot からのメッセージを無視します。",
            ),
            "label": "屏蔽官方机器人",
            "order": 5,
        },
    )
    regex_filter_enabled: bool = Field(
        default=False,
        description="是否启用正则表达式消息过滤。",
        json_schema_extra={
            "hint": "开启后将根据正则表达式规则过滤入站消息。",
            "label": "启用正则过滤",
            "order": 1,
        },
    )
    regex_filter_mode: Literal["blacklist", "whitelist"] = Field(
        default="blacklist",
        description="正则过滤模式。blacklist 匹配则丢弃，whitelist 仅放行匹配的消息。",
        json_schema_extra={
            "hint": "黑名单模式下匹配正则的消息会被丢弃；白名单模式下仅匹配正则的消息会被放行。",
            "label": "正则过滤模式",
            "order": 2,
        },
    )
    regex_filter_patterns: List[str] = Field(
        default_factory=list,
        description="正则表达式列表，支持 Python re 模块语法。",
        json_schema_extra={
            "hint": "每条规则为一个 Python 正则表达式，消息文本将逐条匹配。无效的正则表达式会在启动时记录警告并跳过。",
            "label": "正则表达式列表",
            "order": 3,
            "placeholder": r"例如：^广告.*|spam",
        },
    )
    regex_filter_show_dropped: bool = Field(
        default=False,
        description="是否显示未通过正则过滤而被丢弃的消息日志。",
        json_schema_extra={
            "hint": "关闭后不会记录因正则过滤而被丢弃的日志，默认关闭以减少刷屏。",
            "label": "显示正则过滤丢弃日志",
            "order": 4,
        },
    )

    @field_validator("ban_user_id", mode="before")
    @classmethod
    def _normalize_ban_user_id(cls, value: Any) -> List[str]:
        """接受整数或字符串 QQ 号列表，校验后统一为字符串并去重。"""
        if not isinstance(value, list):
            raise ValueError("ban_user_id 必须是 QQ 号列表")
        user_ids: List[str] = []
        for item in value:
            text = str(item).strip()
            if not isinstance(item, (int, str)) or not text.isascii() or not text.isdecimal() or int(text) <= 0:
                raise ValueError("ban_user_id 中的 QQ 号必须是正整数")
            user_id = str(int(text))
            if user_id not in user_ids:
                user_ids.append(user_id)
        return user_ids

    @field_validator("regex_filter_mode", mode="before")
    @classmethod
    def _normalize_regex_filter_mode(cls, value: Any) -> Literal["whitelist", "blacklist"]:
        """规范化正则过滤模式字段。"""
        normalized_value = _normalize_string(value)
        if normalized_value == "whitelist":
            return "whitelist"
        if normalized_value not in ("whitelist", "blacklist"):
            LOGGER.warning(f"无效的 regex_filter_mode 值 '{value}'，已回退到 'blacklist'")
        return "blacklist"

    @field_validator("regex_filter_patterns", mode="before")
    @classmethod
    def _normalize_regex_filter_patterns(cls, value: Any) -> List[str]:
        """规范化正则表达式列表字段。"""
        return _normalize_string_list(value)


class QQNoticeConfig(PluginConfigBase):
    """通知事件传递配置。

    采用白名单式开关：仅明确启用的通知类型会注入 Host，
    未在此处列出的通知类型（如输入状态 notify.input_status）默认丢弃。
    """

    __ui_label__: ClassVar[str] = "通知事件"
    __ui_order__: ClassVar[int] = 3

    enabled: bool = Field(
        default=True,
        description="是否将适配器推送的通知事件转发给 Host。",
        json_schema_extra={
            "hint": "关闭后，戳一戳、禁言、撤回、入群退群等所有通知事件都不会传入 Host。",
            "i18n": _schema_i18n(
                label_en="Enable notice events",
                label_ja="通知イベントを有効化",
                hint_en="When disabled, poke, ban, recall, member change and all other notice events are not routed to the Host.",
                hint_ja="無効にすると、poke、禁言、撤回、メンバー変更などすべての通知イベントは Host に転送されません。",
            ),
            "label": "启用通知事件",
            "order": 0,
        },
    )
    enable_poke: bool = _notice_field(
        label="传递戳一戳",
        description="是否传递戳一戳通知。",
        order=1,
        label_en="Route poke",
        label_ja="poke を転送",
    )
    enable_friend_recall: bool = _notice_field(
        label="传递好友撤回",
        description="是否传递好友消息撤回通知。",
        order=2,
        label_en="Route friend recall",
        label_ja="友達の撤回を転送",
    )
    enable_group_recall: bool = _notice_field(
        label="传递群消息撤回",
        description="是否传递群消息撤回通知。",
        order=3,
        label_en="Route group recall",
        label_ja="グループ撤回を転送",
    )
    enable_group_ban: bool = _notice_field(
        label="传递禁言",
        description="是否传递群禁言和解除禁言通知。",
        order=4,
        label_en="Route group ban",
        label_ja="グループ禁言を転送",
    )
    enable_group_msg_emoji_like: bool = _notice_field(
        label="传递消息表情回应",
        description="是否传递群消息表情回应通知。",
        order=5,
        label_en="Route emoji reactions",
        label_ja="絵文字リアクションを転送",
    )
    enable_group_upload: bool = _notice_field(
        label="传递群文件上传",
        description="是否传递群文件上传通知。",
        order=6,
        label_en="Route group uploads",
        label_ja="グループファイルを転送",
    )
    enable_group_increase: bool = _notice_field(
        label="传递入群",
        description="是否传递群成员增加通知。",
        order=7,
        label_en="Route member joins",
        label_ja="参加通知を転送",
    )
    enable_group_decrease: bool = _notice_field(
        label="传递退群",
        description="是否传递群成员减少通知。",
        order=8,
        label_en="Route member leaves",
        label_ja="退出通知を転送",
    )
    enable_group_admin: bool = _notice_field(
        label="传递管理员变动",
        description="是否传递群管理员变动通知。",
        order=9,
        label_en="Route admin changes",
        label_ja="管理者変更を転送",
    )
    enable_essence: bool = _notice_field(
        label="传递精华消息",
        description="是否传递精华消息变动通知。",
        order=10,
        label_en="Route essence changes",
        label_ja="精華メッセージを転送",
    )
    enable_group_name: bool = _notice_field(
        label="传递群名变更",
        description="是否传递群名称变更通知。",
        order=11,
        label_en="Route group name changes",
        label_ja="グループ名変更を転送",
    )


class QQPluginSettings(PluginConfigBase):
    """SnowLuma 适配器（统一 QQ 连接器）完整配置。"""

    plugin: QQPluginOptions = Field(default_factory=QQPluginOptions)
    client: QQServerConfig = Field(default_factory=QQServerConfig)
    notice: QQNoticeConfig = Field(default_factory=QQNoticeConfig)
    filters: QQFilterConfig = Field(default_factory=QQFilterConfig)
    debug: QQDebugConfig = Field(default_factory=QQDebugConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_config(cls, raw_config: Any) -> Dict[str, Any]:
        """将旧版 SnowLuma / 旧版 NapCat 旧配置结构迁移为当前配置模型。

        Args:
            raw_config: Runner 注入的原始配置内容。

        Returns:
            Dict[str, Any]: 适配到当前配置模型后的字典结构。
        """

        raw_mapping = _as_mapping(raw_config)
        plugin_section = _as_mapping(raw_mapping.get("plugin"))
        debug_section = _as_mapping(raw_mapping.get("debug"))
        # 调试项从插件设置移到独立分类；保留旧配置的显式值，新分类的值优先。
        for field_name in QQDebugConfig.model_fields:
            if field_name in plugin_section:
                legacy_value = plugin_section.pop(field_name)
                if field_name not in debug_section:
                    debug_section[field_name] = legacy_value
        chat_section = _as_mapping(raw_mapping.get("chat"))
        filters_section = _as_mapping(raw_mapping.get("filters"))
        # 自身消息过滤同样归入调试分类，保留旧配置的显式选择。
        if "ignore_self_message" in filters_section:
            legacy_ignore_self = filters_section.pop("ignore_self_message")
            if "ignore_self_message" not in debug_section:
                debug_section["ignore_self_message"] = legacy_ignore_self
        notice_section = _as_mapping(raw_mapping.get("notice"))
        if "ban_qq_bot" not in filters_section and "ban_qq_bot" in chat_section:
            filters_section["ban_qq_bot"] = chat_section["ban_qq_bot"]

        client_section = _as_mapping(raw_mapping.get("client"))
        legacy_sources: List[tuple[str, Mapping[str, Any]]] = []
        luma_section = _as_mapping(raw_mapping.get("luma_client"))
        napcat_section = _as_mapping(raw_mapping.get("napcat_server"))
        legacy_connection_section = _as_mapping(raw_mapping.get("connection"))
        if luma_section and not client_section:
            legacy_sources.append(("luma_client", luma_section))
        if napcat_section and not client_section:
            legacy_sources.append(("napcat_server", napcat_section))
        if legacy_connection_section and not client_section:
            legacy_sources.append(("connection", legacy_connection_section))

        if legacy_sources:
            source_name, source_section = legacy_sources[0]
            LOGGER.warning(f"SnowLuma 适配器检测到旧版 [{source_name}] 配置段，已自动迁移到 [client]")
            client_section = dict(source_section)
            # 旧 SnowLuma 配置使用 server 字段；旧 NapCat 配置使用 host 字段，统一映射为 server。
            legacy_host = _normalize_string(client_section.get("host"))
            if legacy_host and not _normalize_string(client_section.get("server")):
                client_section["server"] = legacy_host
            legacy_access_token = _normalize_string(client_section.get("access_token"))
            if legacy_access_token and not _normalize_string(client_section.get("token")):
                client_section["token"] = legacy_access_token

        # 旧配置携带历史版本号时会触发版本校验失败；迁移时统一改写为当前版本。
        if _normalize_string(plugin_section.get("config_version")) not in {"", SUPPORTED_CONFIG_VERSION}:
            plugin_section["config_version"] = SUPPORTED_CONFIG_VERSION

        return {
            "client": client_section,
            "debug": debug_section,
            "filters": filters_section,
            "notice": notice_section,
            "plugin": plugin_section,
        }

    @classmethod
    def from_mapping(cls, raw_config: Mapping[str, Any], logger: Any) -> "QQPluginSettings":
        """从 Runner 注入的原始配置字典解析插件配置。

        Args:
            raw_config: Runner 注入的原始配置内容。
            logger: 兼容旧调用签名保留的日志对象，当前不直接使用。

        Returns:
            QQPluginSettings: 规范化后的插件配置模型。
        """

        del logger
        return cls.model_validate(dict(raw_config))

    def should_connect(self) -> bool:
        """判断当前配置下是否应当启动连接。

        Returns:
            bool: 若插件连接已启用，则返回 ``True``。
        """

        return self.plugin.should_connect()

    def validate_runtime_config(self, logger: Any) -> bool:
        """校验当前配置是否满足启动连接的前提条件。

        Args:
            logger: 插件日志对象。

        Returns:
            bool: 若配置满足启动连接的前提条件，则返回 ``True``。
        """

        config_version = self.plugin.config_version
        if not config_version:
            logger.error(f"适配器配置缺少 plugin.config_version，当前插件要求版本 {SUPPORTED_CONFIG_VERSION}")
            return False

        if config_version != SUPPORTED_CONFIG_VERSION:
            logger.error(
                f"适配器配置版本不兼容: 当前为 {config_version}，当前插件要求 {SUPPORTED_CONFIG_VERSION}"
            )
            return False

        if not self.client.server:
            logger.warning("适配器已启用，但 client.server 为空")
            return False

        if self.client.port <= 0:
            logger.warning("适配器已启用，但 client.port 不是正整数")
            return False

        return True


def _as_mapping(value: Any) -> Dict[str, Any]:
    """将任意值安全转换为字典。

    Args:
        value: 待转换的值。

    Returns:
        Dict[str, Any]: 若原值是映射，则返回普通字典；否则返回空字典。
    """

    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_positive_float(value: Any, default: float) -> float:
    """规范化正浮点数配置值。

    Args:
        value: 原始配置值。
        default: 非法取值时使用的默认值。

    Returns:
        float: 合法的正浮点数；非法时回退到默认值。
    """

    if isinstance(value, (int, float)) and float(value) > 0:
        return float(value)

    if isinstance(value, str):
        try:
            parsed_value = float(value.strip())
        except ValueError:
            return default
        if parsed_value > 0:
            return parsed_value

    return default


def _normalize_positive_int(value: Any, default: int) -> int:
    """规范化正整数配置值。

    Args:
        value: 原始配置值。
        default: 非法取值时使用的默认值。

    Returns:
        int: 合法的正整数；非法时回退到默认值。
    """

    if isinstance(value, int) and value > 0:
        return value

    if isinstance(value, str):
        normalized_value = value.strip()
        if normalized_value.isdigit():
            parsed_value = int(normalized_value)
            if parsed_value > 0:
                return parsed_value

    return default


def _normalize_string(value: Any) -> str:
    """规范化字符串配置值。

    Args:
        value: 原始配置值。

    Returns:
        str: 去除首尾空白后的字符串；若值为空则返回空字符串。
    """

    return "" if value is None else str(value).strip()


def _normalize_string_list(value: Any) -> List[str]:
    """规范化字符串列表配置值。

    Args:
        value: 原始配置值。

    Returns:
        List[str]: 去除空白与重复项后的字符串列表。
    """

    if not isinstance(value, list):
        return []

    normalized_values: List[str] = []
    seen_values = set()
    for item in value:
        item_text = _normalize_string(item)
        if not item_text or item_text in seen_values:
            continue
        seen_values.add(item_text)
        normalized_values.append(item_text)
    return normalized_values
