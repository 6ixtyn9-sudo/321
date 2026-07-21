from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple
from datetime import datetime

class BaseCollector(ABC):
    
    @abstractmethod
    def fetch(self, url: str) -> Tuple[int, bytes, Dict[str, str], Optional[str]]:
        """
        Fetch URL.
        Returns:
            (status_code, content, headers, http_error)
        """
        pass
        
class BaseParser(ABC):
    
    @abstractmethod
    def parse_matches(self, content: bytes, collected_at: datetime) -> list[object]:
        pass
        
    @abstractmethod
    def parse_predictions(self, content: bytes, collected_at: datetime) -> list[object]:
        pass
