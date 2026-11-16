"""
Side tables for PostGIS as gzip CSV (hex EWKB geometry): places, countries, lakes (HydroLAKES >= 1 km2), mainstems.
Output: data/processed/pg/{places,countries,lakes,mainstems}.csv.gz
Run:    .venv/Scripts/python build/export_layers.py
"""
import csv
import gzip
import pathlib

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "pg"


def ewkb(geoms):
    g = shapely.set_srid(shapely.set_precision(geoms, 1e-5), 4326)
    return shapely.to_wkb(g, hex=True, include_srid=True)


def multi(geoms):
    return [shapely.MultiPolygon([g]) if g.geom_type == "Polygon" else g for g in geoms]


def write(name, rows):
    p = OUT / f"{name}.csv.gz"
    with gzip.open(p, "wt", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(name, round(p.stat().st_size / 1e6, 1), "MB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pp = pyogrio.read_dataframe(f"/vsizip/{RAW.as_posix()}/ne_10m_populated_places.zip/ne_10m_populated_places.shp",
                                columns=["NAME_EN", "NAME", "ADM0NAME", "ADM0_A3", "POP_MAX", "SCALERANK", "FEATURECLA"])
    pp["nm"] = pp["NAME_EN"].fillna(pp["NAME"])
    cap = pp["FEATURECLA"].str.startswith("Admin-0 capital", na=False).map({True: "capital", False: ""})   # national capitals only
    write("places", zip(pp["nm"], pp["ADM0NAME"], pp["ADM0_A3"], pp["POP_MAX"].astype("int64"), pp["SCALERANK"], cap,
                        ewkb(pp.geometry.values)))

    co = pyogrio.read_dataframe(f"/vsizip/{RAW.as_posix()}/ne_10m_admin_0_countries.zip/ne_10m_admin_0_countries.shp",
                                columns=["ADM0_A3", "NAME_EN", "NAME"])
    co["nm"] = co["NAME_EN"].fillna(co["NAME"])
    write("countries", zip(co["ADM0_A3"], co["nm"], ewkb(multi(co.geometry.values))))

    lk = pyogrio.read_dataframe(f"/vsizip/{RAW.as_posix()}/HydroLAKES_polys_v10_shp.zip/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp",
                                columns=["Hylak_id", "Lake_name", "Country", "Lake_type", "Lake_area", "Vol_total",
                                         "Depth_avg", "Dis_avg", "Res_time"], where="Lake_area >= 1")
    lk["type"] = lk["Lake_type"].map({1: "lake", 2: "reservoir", 3: "regulated lake"})
    geoms = shapely.simplify(lk.geometry.values, 0.0005, preserve_topology=True)
    write("lakes", zip(lk["Hylak_id"], lk["Lake_name"].fillna(""), lk["Country"], lk["type"], lk["Lake_area"],
                       lk["Vol_total"], lk["Depth_avg"], lk["Dis_avg"], lk["Res_time"], ewkb(multi(geoms))))

    ms = pd.concat([gpd.read_parquet(p) for p in sorted((ROOT / "data" / "processed").glob("mainstems_*.parquet"))])
    write("mainstems", zip(ms["main"], ms["name"].fillna(""), ms["len"], ms["dis"], ms["area"], ms["sink"]))


if __name__ == "__main__":
    main()
