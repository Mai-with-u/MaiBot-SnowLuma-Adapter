"""由官方适配器持续续期的收发暂停租约，绝不写入配置或数据库。"""

from typing import Any, Dict, List

import time


IDENTITY_ONLY_TTL = 15.0


class IdentityOnlyLease:
    """仅保存一个账号和持有者；进程重启、断连、停用或超时均恢复普通投递。"""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self._account_id = ""
        self._owner = ""
        self._expires_at = 0.0

    def active(self, account_id: str) -> bool:
        if time.monotonic() >= self._expires_at:
            self.clear()
        return bool(self._owner and self._account_id == account_id)

    def status_badges(self, account_id: str) -> List[Dict[str, Any]]:
        """用实际租约剩余时间生成通用标记，查询自身不会续期。"""
        if not self.active(account_id):
            return []
        return [{"id": "identity_only", "label": "仅身份查询",
                 "expires_at": time.time() + max(0.0, self._expires_at - time.monotonic())}]

    def remaining(self, account_id: str) -> float:
        return max(0.0, self._expires_at - time.monotonic()) if self.active(account_id) else 0.0

    def update(self, account_id: str, owner: str, enabled: bool) -> Dict[str, Any]:
        if not account_id.isdecimal() or not owner or len(owner) > 128:
            raise ValueError("租约账号或持有者无效")
        active = self.active(account_id)
        if not enabled:
            # 旧实例的延迟释放不能解除新实例持有的租约。
            if self._account_id == account_id and self._owner == owner:
                self.clear()
            return {"active": self.active(account_id), "ttl": IDENTITY_ONLY_TTL}
        if self._owner and (not active or self._owner != owner):
            raise ValueError("身份查询模式正由另一个官方适配器实例持有，请等待租约过期")
        self._account_id = account_id
        self._owner = owner
        self._expires_at = time.monotonic() + IDENTITY_ONLY_TTL
        return {"active": True, "ttl": IDENTITY_ONLY_TTL}
