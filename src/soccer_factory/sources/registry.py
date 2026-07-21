from typing import Dict, Type, Callable, TypeVar
from .base import BaseCollector

T = TypeVar("T", bound=BaseCollector)

_COLLECTORS: Dict[str, Type[BaseCollector]] = {}

def register_collector(name: str) -> Callable[[Type[T]], Type[T]]:
    def decorator(cls: Type[T]) -> Type[T]:
        _COLLECTORS[name] = cls
        return cls
    return decorator

def get_collector(name: str) -> Type[BaseCollector]:
    if name not in _COLLECTORS:
        raise ValueError(f"Collector '{name}' not found in registry.")
    return _COLLECTORS[name]
