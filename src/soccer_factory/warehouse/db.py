import duckdb
from pathlib import Path
from typing import Optional

class Warehouse:
    def __init__(self, db_path: str = "data/warehouse/soccer_factory.duckdb"):
        self.db_path = db_path
        self._ensure_db_dir()
        self.conn = self._init_db()

    def _ensure_db_dir(self) -> None:
        path = Path(self.db_path)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(self.db_path)
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            conn.execute(schema_path.read_text())
        return conn

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return self.conn

    def close(self) -> None:
        self.conn.close()

def get_warehouse(db_path: Optional[str] = None) -> Warehouse:
    if db_path:
        return Warehouse(db_path)
    return Warehouse()
