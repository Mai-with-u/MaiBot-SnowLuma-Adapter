from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class BaseComponent:
    def to_dict(self):
        """将消息组件转换为字典格式"""
        return self.__dict__

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典格式创建消息组件实例"""
        for field in cls.__dataclass_fields__:
            if field not in data:
                raise ValueError(f"缺少字段: {field}")
        for key in data:
            if key not in cls.__dataclass_fields__:
                raise ValueError(f"未知字段: {key}")
        return cls(**data)
