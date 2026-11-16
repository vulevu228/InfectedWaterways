"""
KPI "people living within 5 km of a river with a mean flow >= 1 m3/s", computed on the PC (not on the Pi: the same
spatial join in PostGIS hung the 1 GB Pi 4 on 2026-11-16).

Method: densify every HydroRIVERS reach with ORD_FLOW <= 6 to points every ~0.005 deg (~0.5 km), mark every 0.025 deg
population cell whose centre lies within 5 km of such a point (haversine on cell centres), then sum GHS-POP 2025 over the
marked cells (data/processed/pg/pop.csv.gz from build_pop.py). Prints the SQL that stores the result in table meta.

Run: .venv/Scripts/python build/people_near_rivers.py
"""
import csv
import gzip
import math
import pathlib

import numpy as np
import pyogrio
import shapely

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
POP = ROOT / "data" / "processed" / "pg" / "pop.csv.gz"
REGIONS = ["af", "ar", "as", "au", "eu", "na", "sa", "si"]
CELL = 0.025
NX, NY = int(360 / CELL), int(180 / CELL)
R_KM = 5.0


def main():
    mask = np.zeros((NY, NX), dtype=bool)
    for r in REGIONS:
        shp = f"/vsizip/{RAW.as_posix()}/HydroRIVERS_v10_{r}_shp.zip/HydroRIVERS_v10_{r}_shp/HydroRIVERS_v10_{r}.shp"
        g = pyogrio.read_dataframe(shp, columns=["ORD_FLOW"], where="ORD_FLOW <= 6").geometry.values
        xy = shapely.get_coordinates(shapely.segmentize(g, 0.005))
        lon, lat = xy[:, 0], xy[:, 1]
        cx = np.floor((lon + 180) / CELL).astype(np.int64)
        cy = np.floor((90 - lat) / CELL).astype(np.int64)
        coslat = np.maximum(np.cos(np.radians(lat)), 0.05)
        ky = int(math.ceil(R_KM / (111.32 * CELL))) + 1
        kx_pt = np.ceil(ky / coslat).astype(np.int64)          # cells needed east/west depends on latitude
        for kx in np.unique(kx_pt):
            sel = kx_pt == kx
            plon, plat, pcos, pcx, pcy = lon[sel], lat[sel], coslat[sel], cx[sel], cy[sel]
            for dy in range(-ky, ky + 1):
                for dx in range(-int(kx), int(kx) + 1):
                    ccx, ccy = pcx + dx, pcy + dy
                    clon = -180 + (ccx + 0.5) * CELL
                    clat = 90 - (ccy + 0.5) * CELL
                    # equirectangular distance is accurate to < 1 % at 5 km
                    d = 111.32 * np.hypot((clon - plon) * pcos, clat - plat)
                    ok = (d <= R_KM) & (ccy >= 0) & (ccy < NY)
                    mask[ccy[ok], ccx[ok] % NX] = True
        print(r, f"{len(xy):,} points, {mask.sum():,} cells marked", flush=True)
    near = total = 0.0
    with gzip.open(POP, "rt") as f:
        for lon, lat, p in csv.reader(f):
            p = float(p)
            total += p
            ix, iy = int((float(lon) + 180) / CELL), int((90 - float(lat)) / CELL)
            if 0 <= iy < NY and mask[iy, ix % NX]:
                near += p
    print(f"people within {R_KM:g} km of a river >= 1 m3/s: {near / 1e9:.3f} bn of {total / 1e9:.3f} bn ({near / total * 100:.1f} %)")
    print(f"INSERT INTO meta VALUES ('people_5km', '{round(near)}') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;")


if __name__ == "__main__":
    main()
