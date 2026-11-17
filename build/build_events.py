"""
History layer + travel-time calibration.

1. Reads build/events.json (hand-checked outbreaks and river contamination events, with sources).
2. For every 'river' event, asks the Pi's trace API for the downstream path from the origin.
3. Calibrates the reach velocity v = a * Q^b (m/s, Q = long-term mean discharge in m3/s) against the reported
   arrival dates of the spill fronts (checkpoints): grid search over a and b, minimising the mean squared
   log error of travel time. Writes docs/CALIBRATION.md and web/data/velocity.json.
4. Writes web/data/events.geojson (origin points) and web/data/event_paths.geojson (downstream paths, with the
   calibrated arrival time per reach).

Run: .venv/Scripts/python build/build_events.py [api base, default http://skysea-pi:8796]
"""
import datetime as dt
import json
import math
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = sys.argv[1] if len(sys.argv) > 1 else "http://skysea-pi:8796"
OUT = ROOT / "web" / "data"


def get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.load(r)


def hav(lon1, lat1, lon2, lat2):
    r = math.radians
    a = math.sin(r(lat2 - lat1) / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def reach_table(tr):
    """[(length_km, q)] in path order, plus each reach's coordinates for checkpoint matching."""
    f = tr["features"]
    rows = []
    for i, x in enumerate(f):
        nxt = f[i + 1]["properties"]["km0"] if i + 1 < len(f) else tr["summary"]["km"]
        coords = x["geometry"]["coordinates"] if x["geometry"]["type"] == "LineString" else sum(x["geometry"]["coordinates"], [])
        rows.append((nxt - x["properties"]["km0"], x["properties"]["q"], coords))
    return rows


def hours_to(rows, idx, a, b):
    return sum(L * 1000 / (a * q ** b) / 3600 for L, q, _ in rows[:idx])


def match(rows, lon, lat):
    best = (1e9, None)
    for i, (_, _, cs) in enumerate(rows):
        for x, y in cs[:: max(1, len(cs) // 6)]:
            d = hav(lon, lat, x, y)
            if d < best[0]:
                best = (d, i)
    return best


def main():
    ev = json.loads((ROOT / "build" / "events.json").read_text(encoding="utf-8"))
    traces, obs = {}, []
    for e in ev["events"]:
        if e["mode"] != "river":
            continue
        o = e["origin"]
        tr = get(f"/api/trace?lon={o['lon']}&lat={o['lat']}")
        if "error" in tr:
            print(e["id"], tr["error"])
            continue
        traces[e["id"]] = tr
        rows = reach_table(tr)
        print(e["id"], tr["summary"]["system"], tr["summary"]["km"], "km, snapped", tr["summary"]["snap_km"], "km")
        t0 = dt.date.fromisoformat(e.get("release", e["from"][:10] if len(e["from"]) == 10 else e["from"] + "-01"))
        for name, lon, lat, day in e.get("checkpoints", []):
            d_km, idx = match(rows, lon, lat)
            days = (dt.date.fromisoformat(day) - t0).days
            ok = d_km <= 15
            print(f"   {name}: path passes {d_km:.1f} km away, observed {days} d" + ("" if ok else "  -> NOT on path, skipped"))
            if ok:
                obs.append({"event": e["id"], "name": e["name"], "checkpoint": name, "obs_days": days, "rows": rows, "idx": idx,
                            "km": round(sum(L for L, _, _ in rows[:idx]))})
    # reference transit times that are not spills (e.g. how long Rhine water takes from Rheinfelden to Lobith)
    for ref in ev.get("references", []):
        o = ref["origin"]
        tr = get(f"/api/trace?lon={o['lon']}&lat={o['lat']}")
        rows = reach_table(tr)
        name, lon, lat = ref["checkpoint"]
        d_km, idx = match(rows, lon, lat)
        print(ref["id"], f"{name}: path passes {d_km:.1f} km away, observed {ref['days']} d")
        if d_km <= 15:
            obs.append({"event": ref["id"], "name": ref["name"] + " (reference)", "checkpoint": name, "obs_days": ref["days"], "rows": rows,
                        "idx": idx, "km": round(sum(L for L, _, _ in rows[:idx]))})
    # grid search; model choice by leave-one-out cross-validation (each checkpoint predicted by a fit without it)
    def sqerr(o, a, b):
        return math.log(hours_to(o["rows"], o["idx"], a, b) / 24 / o["obs_days"]) ** 2

    def fit(pts, free):
        grid = [(ai / 100, bi / 100) for ai in range(5, 301) for bi in (range(0, 61) if free else [10])]
        return min(grid, key=lambda ab: sum(sqerr(o, *ab) for o in pts))

    loo = {}
    for free in (False, True):
        errs = []
        for k, o in enumerate(obs):
            a_, b_ = fit(obs[:k] + obs[k + 1:], free)
            errs.append(sqerr(o, a_, b_))
        loo[free] = math.sqrt(sum(errs) / len(errs))
    a_free, b_free = fit(obs, True)
    a_one, b_one = fit(obs, False)
    err_free = sum(sqerr(o, a_free, b_free) for o in obs) / len(obs)
    err_one = sum(sqerr(o, a_one, b_one) for o in obs) / len(obs)
    use_free = loo[True] < loo[False]
    a, b, err = (a_free, b_free, err_free) if use_free else (a_one, b_one, err_one)
    lines = ["# Travel-time calibration", "",
             f"Generated {dt.date.today()} by `build/build_events.py` from the reported arrival dates in `build/events.json`.", "",
             "Reach velocity model: **v = a · Q^b** (m/s), Q = long-term mean discharge of the reach (HydroRIVERS, m³/s);",
             "travel time = Σ reach length / v. Downstream hydraulic geometry (Leopold & Maddock 1953) gives b ≈ 0.1.", "",
             f"**Used by the map: a = {a:.2f}, b = {b:.2f}** - in-sample RMS log error {math.sqrt(err):.3f} "
             f"(typical factor {math.exp(math.sqrt(err)):.2f} between model and observed).", "",
             "Model choice by leave-one-out cross-validation (each checkpoint predicted by a fit made without it):", "",
             "| Model | Parameters (all points) | In-sample factor | Leave-one-out factor |", "|---|---|---|---|",
             f"| b fixed at 0.1 (textbook downstream exponent) | a = {a_one:.2f} | ×{math.exp(math.sqrt(err_one)):.2f} | ×{math.exp(loo[False]):.2f} |",
             f"| a and b free | a = {a_free:.2f}, b = {b_free:.2f} | ×{math.exp(math.sqrt(err_free)):.2f} | ×{math.exp(loo[True]):.2f} |", "",
             f"Chosen: **{'a and b free' if use_free else 'b fixed at 0.1'}** (lower leave-one-out error).", "",
             f"| Event | Checkpoint | Distance along river | Observed | Model (a={a:.2f}, b={b:.2f}) | Model (uncalibrated a=0.30, b=0.10) |",
             "|---|---|---|---|---|---|"]
    for o in obs:
        m = hours_to(o["rows"], o["idx"], a, b) / 24
        m0 = hours_to(o["rows"], o["idx"], 0.30, 0.10) / 24
        lines.append(f"| {o['name']} | {o['checkpoint']} | {o['km']:,} km | {o['obs_days']} d | {m:.1f} d | {m0:.1f} d |")
    lines += ["", f"Caveats: only {len(obs)} checkpoints (3 spills + 1 reference transit time). The Songhua slick moved under forming ice; the Rio Doce mud was a dense",
              "tailings flow held back by hydropower reservoirs (Candonga); dates are front arrivals reported to the day.",
              "Mean-flow speeds ignore floods, tides and lakes (lake residence time is listed, not added).",
              "Treat every trace time as an order-of-magnitude estimate, not a forecast."]
    (ROOT / "docs" / "CALIBRATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[6:]))
    (OUT / "velocity.json").write_text(json.dumps({"a": a, "b": b, "rms_log": round(math.sqrt(err), 3), "loo_rms_log": round(loo[use_free], 3),
                                                   "n_checkpoints": len(obs), "updated": str(dt.date.today())}))
    # outputs for the map
    pts, paths = [], []
    for e in ev["events"]:
        o = e["origin"]
        props = {k: e.get(k) for k in ("id", "kind", "mode", "name", "agent", "from", "to", "cases", "deaths", "count_note", "water")}
        props["place"] = o["place"]
        props["sources"] = json.dumps(e["sources"])
        tr = traces.get(e["id"])
        if tr:
            rows = reach_table(tr)
            t = 0.0
            for (L, q, _), f in zip(rows, tr["features"]):
                paths.append({"type": "Feature", "geometry": f["geometry"],
                              "properties": {"id": e["id"], "kind": e["kind"], "d": round(t / 24, 2), "q": q}})
                t += L * 1000 / (a * q ** b) / 3600
            s = tr["summary"]
            props.update({"path_km": s["km"], "path_days": round(t / 24, 1), "system": s["system"] or e.get("river"), "ends": s["ends"],
                          "countries": json.dumps([c["name"] for c in tr["countries"]])})
            cps = []
            for name, lon, lat, day in e.get("checkpoints", []):
                ob = next((x for x in obs if x["event"] == e["id"] and x["checkpoint"] == name), None)
                if ob:
                    cps.append([name, lon, lat, ob["obs_days"], round(hours_to(ob["rows"], ob["idx"], a, b) / 24, 1)])
            props["checkpoints"] = json.dumps(cps)
        pts.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [o["lon"], o["lat"]]}, "properties": props})
    (OUT / "events.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pts}, ensure_ascii=False), encoding="utf-8")
    (OUT / "event_paths.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": paths}), encoding="utf-8")
    print(len(pts), "events,", len(paths), "path reaches")


if __name__ == "__main__":
    main()
