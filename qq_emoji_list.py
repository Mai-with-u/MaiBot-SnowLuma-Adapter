"""QQ 原生表情映射表，与普通消息及表情回应共用数据。"""

from typing import Dict

from .qq_face_map import QQ_FACE_DESCRIPTIONS


QQ_FACE: Dict[str, str] = {
    face_id: f"[表情：{description}]" for face_id, description in QQ_FACE_DESCRIPTIONS.items()
}
