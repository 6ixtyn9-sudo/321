from typing import Dict, Type
from .base import BaseCollector

_COLLECTORS: Dict[str, Type[BaseCollector]] = {}

def register_collector(name: str):
    def decorator(cls: Type[BaseCollector]):
        _COLLECTORS[name] = cls
        return cls
    return decorator

def get_collector(name: str) -> Type[BaseCollector]:
    if name not in _COLLECTORS:
        raise ValueError(f"Collector '{name}' not found in registry.")
    return _COLLECTORS[name]
