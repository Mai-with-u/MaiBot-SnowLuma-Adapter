"""供官方适配器静默配对的短期消息指纹；不保存聊天正文。"""

from collections import OrderedDict
from hashlib import sha256
from typing import Any, Dict, List, Mapping
from typing import OrderedDict as OrderedDictType

import math
import time
import unicodedata


OBSERVATION_TTL = 120.0
MAX_OBSERVATIONS = 2000
MAX_GROUP_OBSERVATIONS = 128


def text_fingerprint(segments: List[Dict[str, Any]]) -> str:
    """协议 v1：只匹配足够长的纯文本，忽略两端表示不同的 @ 和引用段。"""
    if any(segment.get("type") not in {"text", "at", "reply"} for segment in segments):
        return ""
    parts = [segment["data"] for segment in segments if segment.get("type") == "text"]
    if not all(isinstance(part, str) for part in parts):
        return ""
    text = "".join(parts)
    if len(text) > 2048:
        return ""
    text = " ".join(unicodedata.normalize("NFKC", text).split())
    if len(text) < 8 or len(set(text)) < 4 or text.startswith("/"):
        return ""
    return sha256(text.encode("utf-8")).hexdigest()


class IdentityObservations:
    """每群与全局双重限额；连接断开时由路由器清空。"""

    def __init__(self) -> None:
        self._rows: OrderedDictType[str, Dict[str, Any]] = OrderedDict()

    def clear(self) -> None:
        self._rows.clear()

    def _prune(self, now: float) -> None:
        for key, row in list(self._rows.items()):
            if now - row["received_at"] >= OBSERVATION_TTL:
                del self._rows[key]

    def observe(self, message: Mapping[str, Any]) -> None:
        info = message["message_info"]
        group = info.get("group_info")
        if not group:
            return
        account = str(message["account_id"])
        group_id = str(group["group_id"])
        user = info["user_info"]
        user_id = str(user["user_id"])
        if not account.isdecimal() or not group_id.isdecimal() or not user_id.isdecimal():
            return
        timestamp = float(message["timestamp"])
        if not math.isfinite(timestamp) or abs(time.time() - timestamp) > OBSERVATION_TTL:
            return
        now = time.monotonic()
        self._prune(now)
        # 重复投递不得刷新接收时间，也不得成为第二条匹配证据。
        key = f"{account}:{group_id}:{message['message_id']}"
        if key in self._rows:
            return
        self._rows[key] = {
            "key": key,
            "account_id": account,
            "group_id": group_id,
            "user_id": user_id,
            "timestamp": timestamp,
            "fingerprint": text_fingerprint(message["raw_message"]),
            "nickname": str(user.get("user_nickname") or "")[:128],
            "cardname": str(user.get("user_cardname") or "")[:128],
            "received_at": now,
        }
        group_keys = [key for key, row in self._rows.items()
                      if (row["account_id"], row["group_id"]) == (account, group_id)]
        for old_key in group_keys[:-MAX_GROUP_OBSERVATIONS]:
            del self._rows[old_key]
        while len(self._rows) > MAX_OBSERVATIONS:
            self._rows.popitem(last=False)

    def snapshot(self, account_id: str, group_ids: List[str]) -> Dict[str, Any]:
        if len(group_ids) > 128:
            raise ValueError("一次最多查询 128 个群")
        self._prune(time.monotonic())
        groups = set(group_ids)
        # 不跨进程传递 monotonic 时间，接收方只使用平台时间和本地等待窗口。
        return {"protocol": 1, "observations": [
            {key: value for key, value in row.items() if key != "received_at"}
            for row in self._rows.values()
            if row["account_id"] == account_id and row["group_id"] in groups
        ]}
