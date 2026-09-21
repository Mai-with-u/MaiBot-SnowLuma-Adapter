"""SnowLuma 适配器内部共享类型。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional, TypeAlias

from typing_extensions import NotRequired, TypedDict


class QQIncomingSegment(TypedDict):
    """NapCat / OneBot 入站消息段结构。"""

    type: str
    data: Mapping[str, Any]


class QQHostMessageSegment(TypedDict):
    """适配器转换后写入 Host 的消息段结构。"""

    type: str
    data: Any
    hash: NotRequired[str]
    binary_data_base64: NotRequired[str]


QQActionParams: TypeAlias = Mapping[str, Any]
QQActionParamsInput: TypeAlias = Optional[Mapping[str, Any]]
QQActionResponse: TypeAlias = Dict[str, Any]
QQIdInput: TypeAlias = int | str
QQMutablePayload: TypeAlias = MutableMapping[str, Any]
QQOptionalIdInput: TypeAlias = int | str | None
QQPayload: TypeAlias = Mapping[str, Any]
QQPayloadDict: TypeAlias = Dict[str, Any]
QQPayloadList: TypeAlias = List[Dict[str, Any]]
QQIncomingSegments: TypeAlias = List[QQIncomingSegment]
QQSegment: TypeAlias = QQHostMessageSegment
QQSegments: TypeAlias = List[QQHostMessageSegment]
