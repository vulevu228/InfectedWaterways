"""
Main stems: for every river system whose outlet carries >= 100 m3/s (HydroRIVERS DIS_AV_CMS), walk upstream from
the outlet, always taking the upstream segment with the largest upstream area (UPLAND_SKM), until the source.
Writes web/data/mainstems.geojson with: name (Natural Earth, majority vote along the stem), length_km,
outlet discharge, basin area, region, sink (sea / inland).

Names: Natural Earth 10m rivers + lake centrelines (public domain). For each stem, sample points along it,
take the nearest named NE line within ~5 km, majority vote.

Run: .venv/Scripts/python build/build_mainstems.py [region ...]
"""
import collections
import json
import pathlib
import sys

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "data"
TMP = ROOT / "data" / "processed"
REGIONS = ["af", "ar", "as", "au", "eu", "na", "sa", "si"]
MIN_OUTLET = 100.0   # m3/s
# manual names where the lower course has no Natural Earth line (checked against the outlet position)
OVERRIDES = {70367865: "St. Lawrence",   # outlet at Quebec City; the Great Lakes stretch has no NE river line
             60545016: "Tocantins"}      # the stem follows the Araguaia branch, but the system and its mouth are the Tocantins
COLS = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM", "ENDORHEIC", "DIS_AV_CMS", "ORD_FLOW"]


def ne_names():
    p = f"/vsizip/{RAW.as_posix()}/ne_10m_rivers_lake_centerlines.zip/ne_10m_rivers_lake_centerlines.shp"
    ne = pyogrio.read_dataframe(p, columns=["name_en", "name", "featurecla"])
    ne["nm"] = ne["name_en"].fillna(ne["name"])
    ne = ne[ne["nm"].notna() & (ne["nm"] != "")]
    return ne[["nm", "geometry"]].reset_index(drop=True)


def stems(region, ne):
    shp = f"/vsizip/{RAW.as_posix()}/HydroRIVERS_v10_{region}_shp.zip/HydroRIVERS_v10_{region}_shp/HydroRIVERS_v10_{region}.shp"
    df = pyogrio.read_dataframe(shp, columns=COLS, where="ORD_FLOW <= 7")
    df = df.set_index("HYRIV_ID")
    up = collections.defaultdict(list)
    for sid, nd, ua in zip(df.index.values, df["NEXT_DOWN"].values, df["UPLAND_SKM"].values):
        if nd:
            up[nd].append((ua, sid))
    outlets = df[(df["NEXT_DOWN"] == 0) & (df["DIS_AV_CMS"] >= MIN_OUTLET)]
    rows = []
    for oid, o in outlets.iterrows():
        path, cur = [oid], oid
        while up.get(cur):
            cur = max(up[cur])[1]
            path.append(cur)
        seg = df.loc[path]
        geom = shapely.line_merge(shapely.union_all(seg.geometry.values))
        ox, oy = shapely.get_coordinates(o.geometry)[-1]
        rows.append({"main": int(oid), "r": region, "ox": float(ox), "oy": float(oy), "len": round(float(seg["LENGTH_KM"].sum())),
                     "dis": round(float(o["DIS_AV_CMS"]), 1), "area": int(o["UPLAND_SKM"]),
                     "sink": "inland" if o["ENDORHEIC"] else "sea", "geometry": geom})
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    # name by majority vote of nearest NE line along the stem (metric CRS for the 5 km threshold)
    pts = []
    for i, geom in enumerate(g.geometry):
        n = max(5, int(geom.length / 0.2))
        for k in range(n + 1):
            pts.append((i, geom.interpolate(k / n, normalized=True)))
    pg = gpd.GeoDataFrame({"i": [p[0] for p in pts]}, geometry=[p[1] for p in pts], crs="EPSG:4326")
    # distance of each sample to its system's outlet -> rank; the lower 30 % of the stem names the river
    pg["d"] = [((pt.x - g.at[i, "ox"]) ** 2 + (pt.y - g.at[i, "oy"]) ** 2) ** .5 for i, pt in zip(pg["i"], pg.geometry)]
    pg["low"] = pg.groupby("i")["d"].rank(pct=True) <= 0.3
    j = gpd.sjoin_nearest(pg.to_crs(3857), ne.to_crs(3857), max_distance=5000, how="left")
    j = j[~j.index.duplicated()]
    def pick(s):
        s = s.dropna()
        return s.value_counts().index[0] if len(s) else None
    low = j[j["low"]].groupby("i")["nm"].agg(pick)
    allv = j.groupby("i")["nm"].agg(pick)
    share = j.groupby("i")["nm"].apply(lambda s: s.notna().mean())
    lowshare = j[j["low"]].groupby("i")["nm"].apply(lambda s: s.notna().mean())
    # the name near the mouth wins when it covers >= 30 % of the lower stem; else the whole-stem vote if >= 25 % covered
    g["name"] = [low.get(i) if lowshare.get(i, 0) >= 0.3 and low.get(i) else (allv.get(i) if share.get(i, 0) >= 0.25 else None)
                 for i in range(len(g))]
    g = g.drop(columns=["ox", "oy"])
    g["geometry"] = g.geometry.simplify(0.005, preserve_topology=False)
    return g


def main(regions):
    ne = ne_names()
    for r in regions:
        g = stems(r, ne)
        g.to_parquet(TMP / f"mainstems_{r}.parquet")
        top = g.sort_values("dis", ascending=False).head(5)
        print(r, len(g), "stems;", list(zip(top["name"], top["len"], top["dis"])), flush=True)
    allg = pd.concat([gpd.read_parquet(p) for p in sorted(TMP.glob("mainstems_*.parquet"))], ignore_index=True)
    allg = gpd.GeoDataFrame(allg, crs="EPSG:4326").sort_values("dis", ascending=False)
    for k, v in OVERRIDES.items():
        allg.loc[allg["main"] == k, "name"] = v
    p = OUT / "mainstems.geojson"
    if p.exists():
        p.unlink()
    pyogrio.write_dataframe(allg, p, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": 3, "RFC7946": "YES"})
    print("mainstems", len(allg), round(p.stat().st_size / 1024), "KB")
    # label lines: named stems only, heavily smoothed so along-line text fits the curves
    lab = allg[allg["name"].notna()][["name", "dis", "main", "geometry"]].copy()
    lab["geometry"] = lab.geometry.simplify(0.25, preserve_topology=False)
    lp = OUT / "mainstem_labels.geojson"
    if lp.exists():
        lp.unlink()
    pyogrio.write_dataframe(lab, lp, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": 3, "RFC7946": "YES"})


if __name__ == "__main__":
    main(sys.argv[1:] or REGIONS)
