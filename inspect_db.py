import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent / "blood_prediction.db"
connection = sqlite3.connect(db_path)

tables = connection.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()

for (table_name,) in tables:
    print(f"\nTABLE: {table_name}")

    safe_name = table_name.replace('"', '""')
    columns = connection.execute(
        f'PRAGMA table_info("{safe_name}")'
    ).fetchall()

    print("COLUMNS:", [column[1] for column in columns])

connection.close()