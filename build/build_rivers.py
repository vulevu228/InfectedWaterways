"""
Build the web-map river layers from HydroRIVERS v1.0 (CC BY 4.0, Lehner & Grill 2013).

HydroRIVERS has no names but gives every segment its discharge (DIS_AV_CMS, long-term average, m3/s)
and a flow-order class ORD_FLOW (log10 classes: 1 = >=100,000 m3/s, 2 = >=10,000, 3 = >=1,000,
4 = >=100, 5 = >=10, 6 = >=1 ...).

Tiers written to web/data/:
  rivers_t1.geojson         ORD_FLOW <= 3  (mainstreams, >= 1,000 m3/s)  - global, always on
  rivers_t2.geojson         ORD_FLOW == 4  (major rivers, >= 100 m3/s)  - global
  rivers_t3_<region>.geojson ORD_FLOW == 5 (rivers, >= 10 m3/s)         - per region, loaded on zoom
  rivers_index.json         region bounding boxes + counts

Segments are merged per (MAIN_RIV, ORD_FLOW) so one river system at one flow class is one feature,
then simplified. MAIN_RIV = id of the segment where the whole river system reaches the sea or an inland sink.

Run: .venv/Scripts/python build/build_rivers.py [region ...]
"""
import json
import pathlib
import sys
import time

import geopandas as gpd
import pyogrio
import shapely

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "data"
TMP = ROOT / "data" / "processed"
REGIONS = {"af": "Africa", "ar": "North American Arctic", "as": "Asia", "au": "Australasia",
           "eu": "Europe & Middle East", "na": "North & Central America", "sa": "South America", "si": "Siberia"}
COLS = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM", "ENDORHEIC", "DIS_AV_CMS",
        "ORD_STRA", "ORD_FLOW"]
TOL = {1: 0.01, 2: 0.01, 3: 0.006}   # simplify tolerance in degrees (~1 km / ~0.6 km at the equator)


def tier(of):
    return 1 if of <= 3 else (2 if of == 4 else 3)


def load(region):
    shp = f"/vsizip/{RAW.as_posix()}/HydroRIVERS_v10_{region}_shp.zip/HydroRIVERS_v10_{region}_shp/HydroRIVERS_v10_{region}.shp"
    return pyogrio.read_dataframe(shp, columns=COLS, where="ORD_FLOW <= 5")


def merge(df, region):
    df["tier"] = df["ORD_FLOW"].map(tier)
    # whole-system stats (outlet = MAIN_RIV segment, it has the largest discharge of its system)
    sys_stats = df.groupby("MAIN_RIV").agg(sys_dis=("DIS_AV_CMS", "max"), sys_area=("UPLAND_SKM", "max"),
                                           endo=("ENDORHEIC", "max"))
    out = []
    for (main, of), g in df.groupby(["MAIN_RIV", "ORD_FLOW"], sort=False):
        geom = shapely.line_merge(shapely.union_all(g.geometry.values))
        t = tier(of)
        geom = shapely.simplify(geom, TOL[t], preserve_topology=False)
        if geom.is_empty:
            continue
        s = sys_stats.loc[main]
        out.append({"main": int(main), "of": int(of), "t": t, "r": region,
                    "dis": round(float(g["DIS_AV_CMS"].max()), 1),
                    "len": round(float(g["LENGTH_KM"].sum()), 1),
                    "sdis": round(float(s.sys_dis), 1), "sarea": int(s.sys_area), "endo": int(s.endo),
                    "geometry": geom})
    return gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")


def write(gdf, path):
    if path.exists():
        path.unlink()
    pyogrio.write_dataframe(gdf, path, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": 3,
                                                                       "RFC7946": "YES"})


def main(regions):
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    index = {}
    for r in regions:
        t0 = time.time()
        df = load(r)
        g = merge(df, r)
        g.to_parquet(TMP / f"rivers_merged_{r}.parquet")
        t3 = g[g.t == 3]
        write(t3, OUT / f"rivers_t3_{r}.geojson")
        b = [round(v, 2) for v in t3.total_bounds] if len(t3) else None
        index[r] = {"name": REGIONS[r], "bbox": b, "segments": len(df), "features": len(g),
                    "t3_features": len(t3), "t3_kb": round((OUT / f"rivers_t3_{r}.geojson").stat().st_size / 1024)}
        print(r, index[r], f"{time.time() - t0:.0f}s", flush=True)
    # global tiers from all merged regions available
    parts = [gpd.read_parquet(p) for p in sorted(TMP.glob("rivers_merged_*.parquet"))]
    allg = gpd.GeoDataFrame(__import__("pandas").concat(parts, ignore_index=True), crs="EPSG:4326")
    for t in (1, 2):
        write(allg[allg.t == t], OUT / f"rivers_t{t}.geojson")
        print(f"t{t}", (allg.t == t).sum(), "features", round((OUT / f"rivers_t{t}.geojson").stat().st_size / 1024), "KB")
    idx_path = OUT / "rivers_index.json"
    old = json.loads(idx_path.read_text()) if idx_path.exists() else {}
    old.update(index)
    idx_path.write_text(json.dumps(old, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or list(REGIONS))
