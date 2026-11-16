"""
Population layer for "people living along the river": GHS-POP R2023A, epoch 2025, 30 arcsec (~1 km), WGS84, CC BY 4.0
(Schiavina et al. 2023, doi:10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE).

Aggregates 3 x 3 cells to 0.025 deg (~2.8 km at the equator), keeps cells with >= 1 person and writes the cell centres
as gzip CSV for the PostGIS table `pop` (sql/03_live.sql). The trace API sums every cell within 5 km of the path.

Run: .venv/Scripts/python build/build_pop.py
"""
import csv
import gzip
import pathlib

import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = pathlib.Path(__file__).resolve().parents[1]
ZIP = ROOT / "data" / "raw" / "GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip"
OUT = ROOT / "data" / "processed" / "pg" / "pop.csv.gz"
F = 3            # aggregation factor (30 arcsec * 3 = 90 arcsec = 0.025 deg)
STRIP = 600      # source rows per read (multiple of F)


def main():
    with rasterio.open(f"zip://{ZIP.as_posix()}!GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.tif") as src:
        H, W = src.height, src.width
        t = src.transform
        nodata = src.nodata
        print(W, "x", H, "cells,", t.a, "deg, nodata", nodata)
        n = total = 0
        with gzip.open(OUT, "wt", newline="", compresslevel=5) as f:
            w = csv.writer(f)
            for r0 in range(0, H - H % F, STRIP):
                rows = min(STRIP, H - H % F - r0)
                a = src.read(1, window=Window(0, r0, W - W % F, rows)).astype("float64")
                if nodata is not None:
                    a[a == nodata] = 0
                a[a < 0] = 0
                total += a.sum()
                b = a.reshape(rows // F, F, (W - W % F) // F, F).sum(axis=(1, 3))
                ys, xs = np.nonzero(b >= 1)
                lon = t.c + (xs * F + F / 2) * t.a
                lat = t.f + (r0 + ys * F + F / 2) * t.e
                for x, y, p in zip(lon, lat, b[ys, xs]):
                    w.writerow((round(float(x), 4), round(float(y), 4), round(float(p), 1)))
                n += len(xs)
        print(f"{n:,} cells, {total / 1e9:.3f} billion people in the grid, {OUT.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
