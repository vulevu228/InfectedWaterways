"""
Lakes layer -> web/data/lakes.geojson
Uses HydroLAKES v1.0 polygons (CC BY 4.0) if data/raw/HydroLAKES_polys_v10_shp.zip is there (lakes >= MIN_KM2,
with volume, depth, discharge, residence time), else Natural Earth 10m lakes (public domain, names only).

Run: .venv/Scripts/python build/build_lakes.py
"""
import pathlib

import pyogrio

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "data" / "lakes.geojson"
MIN_KM2 = 100


def main():
    hl = RAW / "HydroLAKES_polys_v10_shp.zip"
    if hl.exists() and hl.stat().st_size > 500_000_000:
        p = f"/vsizip/{hl.as_posix()}/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp"
        g = pyogrio.read_dataframe(p, columns=["Hylak_id", "Lake_name", "Country", "Lake_type", "Lake_area",
                                               "Vol_total", "Depth_avg", "Dis_avg", "Res_time"],
                                   where=f"Lake_area >= {MIN_KM2}")
        g = g.rename(columns={"Hylak_id": "id", "Lake_name": "name", "Country": "country", "Lake_type": "type",
                              "Lake_area": "area", "Vol_total": "vol", "Depth_avg": "depth", "Dis_avg": "dis",
                              "Res_time": "res_days"})
        # Lake_type: 1 lake, 2 reservoir, 3 lake control (regulated natural lake)
        g["type"] = g["type"].map({1: "lake", 2: "reservoir", 3: "regulated lake"})
        g["src"] = "HydroLAKES v1.0"
        g["geometry"] = g.geometry.simplify(0.005, preserve_topology=True)
    else:
        p = f"/vsizip/{RAW.as_posix()}/ne_10m_lakes.zip/ne_10m_lakes.shp"
        g = pyogrio.read_dataframe(p, columns=["name_en", "name", "featurecla", "scalerank"])
        g["name"] = g["name_en"].fillna(g["name"])
        g = g[["name", "featurecla", "scalerank", "geometry"]]
        g["src"] = "Natural Earth 10m"
    if OUT.exists():
        OUT.unlink()
    pyogrio.write_dataframe(g, OUT, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": 3, "RFC7946": "YES"})
    print(g["src"].iloc[0], len(g), "lakes", round(OUT.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
