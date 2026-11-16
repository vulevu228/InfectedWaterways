"""
Export HydroRIVERS segments with ORD_FLOW <= 6 (long-term mean discharge >= 1 m3/s; 2,369,127 segments worldwide)
as gzip CSV for COPY into PostGIS (table rivers, see sql/01_schema.sql). Geometry = hex EWKB, SRID 4326.
Flow order only grows downstream, so this subset is closed under NEXT_DOWN: every downstream trace stays complete.

Output: data/processed/pg/rivers_<region>.csv.gz
Run:    .venv/Scripts/python build/export_pg.py [region ...]
"""
import csv
import gzip
import pathlib
import sys

import pyogrio
import shapely

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "pg"
REGIONS = ["af", "ar", "as", "au", "eu", "na", "sa", "si"]
COLS = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "DIST_DN_KM", "DIST_UP_KM", "UPLAND_SKM", "DIS_AV_CMS",
        "ORD_STRA", "ORD_CLAS", "ORD_FLOW", "ENDORHEIC", "HYBAS_L12"]


def main(regions):
    OUT.mkdir(parents=True, exist_ok=True)
    for r in regions:
        shp = f"/vsizip/{RAW.as_posix()}/HydroRIVERS_v10_{r}_shp.zip/HydroRIVERS_v10_{r}_shp/HydroRIVERS_v10_{r}.shp"
        df = pyogrio.read_dataframe(shp, columns=COLS, where="ORD_FLOW <= 6")
        geom = shapely.set_precision(df.geometry.values, 1e-5)   # ~1 m
        wkb = shapely.to_wkb(geom, hex=True, include_srid=False)
        p = OUT / f"rivers_{r}.csv.gz"
        with gzip.open(p, "wt", newline="", compresslevel=5, encoding="utf-8") as f:
            w = csv.writer(f)
            for row, g in zip(df[COLS].itertuples(index=False), wkb):
                w.writerow([*row, r, g])
        print(r, len(df), "segments", round(p.stat().st_size / 1e6, 1), "MB", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or REGIONS)
