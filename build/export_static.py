"""Static copy of the Pi API for the public GitHub Pages map (web/data/static/).

The map on GitHub Pages cannot reach the Pi, so it reads:
  health.json    /api/health
  live.json      /api/live  (fallback; the Pi publishes a fresh one daily to the live-data branch, see pi/publish/)
  examples.json  the precomputed release points (name, lon, lat, km, days)
  traces/<id>.json  /api/trace for each example
Run from a machine on the tailnet:  python build/export_static.py [api base, default http://skysea-pi:8796]
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data" / "static"
API = sys.argv[1] if len(sys.argv) > 1 else "http://skysea-pi:8796"

# The river-mode historic events (same start points as web/data/events.geojson) plus big rivers worth exploring
EXAMPLES = [
    ("haiti2010", "Cholera, Haiti (Artibonite, 2010)", -72.105, 18.815),
    ("baiamare2000", "Cyanide spill, Baia Mare (2000)", 23.47, 47.665),
    ("songhua2005", "Benzene spill, Songhua River (2005)", 126.5, 43.92),
    ("mariana2015", "Tailings dam collapse, Rio Doce (2015)", -43.468, -20.207),
    ("sandoz1986", "Sandoz chemical fire, Rhine (1986)", 7.675, 47.535),
    ("rhine-basel", "Rhine at Basel", 7.59, 47.56),
    ("danube-passau", "Danube at Passau", 13.47, 48.57),
    ("volga-tver", "Volga at Tver", 35.9, 56.86),
    ("ganges-haridwar", "Ganges at Haridwar", 78.16, 29.95),
    ("brahmaputra-dibrugarh", "Brahmaputra at Dibrugarh", 94.9, 27.48),
    ("indus-attock", "Indus at Attock", 72.25, 33.9),
    ("mekong-jinghong", "Lancang–Mekong at Jinghong", 100.8, 22.0),
    ("yangtze-chongqing", "Yangtze at Chongqing", 106.55, 29.56),
    ("nile-khartoum", "Nile at Khartoum", 32.53, 15.62),
    ("niger-bamako", "Niger at Bamako", -8.0, 12.63),
    ("congo-kisangani", "Congo at Kisangani", 25.19, 0.52),
    ("zambezi-falls", "Zambezi at Victoria Falls", 25.86, -17.93),
    ("amazon-iquitos", "Amazon at Iquitos", -73.25, -3.75),
    ("mississippi-minneapolis", "Mississippi at Minneapolis", -93.26, 44.98),
]


def get(path):
    with urllib.request.urlopen(API + path, timeout=180) as r:
        return json.loads(r.read())


def main():
    (OUT / "traces").mkdir(parents=True, exist_ok=True)
    vel = json.loads((ROOT / "web" / "data" / "velocity.json").read_text())
    for name in ("health", "live"):
        (OUT / f"{name}.json").write_text(json.dumps(get(f"/api/{name}"), separators=(",", ":")), encoding="utf-8")
    out = []
    for eid, label, lon, lat in EXAMPLES:
        q = urllib.parse.urlencode({"lon": lon, "lat": lat, "a": vel["a"], "b": vel["b"]})
        d = get(f"/api/trace?{q}")
        if d.get("error"):
            print(f"  skip {eid}: {d['error']}")
            continue
        (OUT / "traces" / f"{eid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        s = d["summary"]
        out.append({"id": eid, "name": label, "lon": lon, "lat": lat, "system": s.get("system"),
                    "km": s["km"], "days": round(s["days"], 2)})
        print(f"{eid:24s} {s.get('system') or '-':14s} {s['km']:7.0f} km {s['days']:6.1f} d")
    (OUT / "examples.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(out), "traces")


if __name__ == "__main__":
    main()
