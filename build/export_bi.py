"""Exports the bi.* views (sql/04_bi.sql) from the Pi to powerbi/data/*.csv for the Power BI report.

The Pi's Postgres listens on localhost only, so the report reads CSV snapshots instead of a live connection.
Refresh = run this, then Refresh in Power BI Desktop.   python build/export_bi.py
"""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi" / "data"
VIEWS = ["cholera_week", "dim_week", "country", "flood", "flood_lag", "don"]

OUT.mkdir(parents=True, exist_ok=True)
for v in VIEWS:
    sql = f"COPY (SELECT * FROM bi.{v}) TO STDOUT WITH (FORMAT csv, HEADER)"
    data = subprocess.run(["ssh", "pi", f'psql -d waterways -X -q -c "{sql}"'], capture_output=True, check=True).stdout
    (OUT / f"{v}.csv").write_bytes(data)
    print(f"{v:14s} {data.count(b'\n') - 1:6d} rows")
