import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class Quarantine:
    def __init__(self, quarantine_dir: str = "data/quarantine"):
        self.quarantine_dir = Path(quarantine_dir)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        
    def quarantine_match(self, match_data: Dict[str, Any], reason: str) -> str:
        """Quarantine a match that could not be confidently resolved."""
        quarantine_id = f"q_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(str(match_data)) % 10000}"
        
        record = {
            "quarantine_id": quarantine_id,
            "quarantined_at": datetime.now().isoformat(),
            "reason": reason,
            "match_data": match_data
        }
        
        file_path = self.quarantine_dir / f"{quarantine_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            
        return str(file_path)
