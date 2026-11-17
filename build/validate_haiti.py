"""Milestone 4 - out-of-sample validation: Haiti 2010, cholera from Meille down the Artibonite River.

Haiti was NOT used to fit the travel-time model (build_events.py calibrates on spills only), so this is a real test.
The pass/fail criteria are fixed below before the numbers are looked at; the result, pass or fail, is written to
docs/VALIDATION.md and web/data/validation.json as it comes out.

Observed facts (Piarroux et al. 2011, Emerg Infect Dis 17(7):1161-8, doi:10.3201/eid1707.110059):
  - Release: MINUSTAH camp at Meille, 2 km south of Mirebalais, above a stream flowing into the Artibonite.
    Newly arriving soldiers on Oct 9, 12 and 16; a sewage pipe into the stream; Meille cases with onset Oct 14-19.
  - Lower Artibonite: "No cholera cases had been reported in the Lower Artibonite area before October 19."
    First alert Oct 19; within the next 24 h alerts from >10 health centres "from Desarmes (a locality 30 km from
    the sea) to the seashore". Oct 21 noon: 3,020 cases, 129 deaths. Peak within 2 days.
  - Between Mirebalais and the delta (Saut d'Eau, Boucan Carre, La Chapelle): 0, 0 and 2 cases on Oct 20-21;
    "population density on its banks is low".
  - "the Artibonite River ... usually flows >100 m3/s in October".
  - Regression: downstream of Meille RR 4.91, coastal plain RR 4.60, distance to Mirebalais not significant.
Incubation of cholera (Azman et al. 2013, J Infect 66:432-8): 5 % by 0.5 d, median 1.4 d, 95 % by 4.4 d.

Run: .venv/Scripts/python build/validate_haiti.py [api base, default http://100.108.59.90:8796]
"""
import datetime as dt
import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = sys.argv[1] if len(sys.argv) > 1 else "http://100.108.59.90:8796"

ORIGIN = ("Meille (UN camp stream)", -72.105, 18.815)
# OpenStreetMap / Nominatim positions of the places the paper names (town centres)
PLACES = {
    "Mirebalais": (-72.1048, 18.8344), "Boucan-Carre": (-72.1475, 18.9245), "Saut-d'Eau": (-72.2004, 18.8162),
    "La Chapelle": (-72.3120, 18.9116), "Desarmes": (-72.3913, 18.9948), "Verrettes": (-72.4674, 19.0508),
    "Petite-Riviere-de-l'Artibonite": (-72.4798, 19.1228), "Pont-Sonde": (-72.6156, 19.1495),
    "Dessalines": (-72.5170, 19.2613), "Saint-Marc": (-72.6995, 19.1020), "Desdunes": (-72.6460, 19.2955),
    "L'Estere": (-72.6102, 19.3032), "Grande Saline": (-72.7738, 19.2461),
}
DELTA_START = "Desarmes"            # "from Desarmes (a locality 30 km from the sea) to the seashore"
MIDDLE = ["Boucan-Carre", "Saut-d'Eau", "La Chapelle"]
INC = (0.5, 1.4, 4.4)               # cholera incubation, days: 5th percentile, median, 95th percentile
DELTA_ONSET = dt.date(2010, 10, 19)
CONTAMINATION = (dt.date(2010, 10, 12), dt.date(2010, 10, 19))   # camp demonstrably contaminating: 2nd troop arrival -> field visit

# pass/fail criteria, fixed before running
CRIT = {
    "P1": "Timing: the release dates the model implies for a delta onset on Oct 19 (incubation 0.5-4.4 d, travel x/÷ "
          "the calibration error) overlap the window in which the camp was demonstrably contaminating (Oct 12-19).",
    "P2": "Simultaneity: the model front reaches every point from Desarmes to the sea within 1 day "
          "(observed: alerts from Desarmes to the seashore within 24 h).",
    "P3": "Exposure contrast: people per river-km within 5 km are at least 3x higher in the delta (Desarmes -> sea) "
          "than on the middle stretch (Mirebalais -> Desarmes), where almost no cases were reported.",
    "P4": "Flow: the model's mean flow at the mouth is above 100 m3/s (paper: usually >100 m3/s in October).",
}


def get(path):
    with urllib.request.urlopen(API + path, timeout=90) as r:
        return json.load(r)


def hav(lon1, lat1, lon2, lat2):
    r = math.radians
    a = math.sin(r(lat2 - lat1) / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def main():
    vel = json.loads((ROOT / "web/data/velocity.json").read_text(encoding="utf-8"))
    err = math.exp(vel["loo_rms_log"])                    # typical out-of-sample factor (x1.17)
    tr = get(f"/api/trace?lon={ORIGIN[1]}&lat={ORIGIN[2]}")
    feats, summ = tr["features"], tr["summary"]
    reaches = []
    for i, f in enumerate(feats):
        p = f["properties"]
        km1 = feats[i + 1]["properties"]["km0"] if i + 1 < len(feats) else summ["km"]
        h1 = feats[i + 1]["properties"]["h0"] if i + 1 < len(feats) else summ["hours"]
        cs = f["geometry"]["coordinates"] if f["geometry"]["type"] == "LineString" else sum(f["geometry"]["coordinates"], [])
        reaches.append({"km0": p["km0"], "km1": km1, "h0": p["h0"], "h1": h1, "q": p["q"], "pop": p["pop"], "cs": cs})

    def locate(lon, lat):
        best = None
        for r in reaches:
            for j, (x, y) in enumerate(r["cs"]):
                d = hav(lon, lat, x, y)
                if best is None or d < best[0]:
                    frac = j / max(1, len(r["cs"]) - 1)
                    best = (d, r["km0"] + frac * (r["km1"] - r["km0"]), r["h0"] + frac * (r["h1"] - r["h0"]))
        return best

    places = []
    for name, (lon, lat) in PLACES.items():
        d, km, h = locate(lon, lat)
        places.append({"name": name, "dist_km": round(d, 1), "river_km": round(km, 1), "days": round(h / 24, 2)})
    places.sort(key=lambda p: p["river_km"])
    P = {p["name"]: p for p in places}

    # P1 timing
    t_delta = P[DELTA_START]["days"]
    lo_travel, hi_travel = t_delta / err ** 2, t_delta * err ** 2           # ~95 % band of the calibration error
    latest = DELTA_ONSET - dt.timedelta(days=lo_travel + INC[0])
    earliest = DELTA_ONSET - dt.timedelta(days=hi_travel + INC[2])
    central = DELTA_ONSET - dt.timedelta(days=t_delta + INC[1])
    p1 = earliest <= CONTAMINATION[1] and latest >= CONTAMINATION[0]
    # the slowest travel time that would still pass: release on Oct 12 at the earliest
    max_travel = (DELTA_ONSET - CONTAMINATION[0]).days - INC[0]

    # P2 simultaneity
    t_end = summ["days"]
    spread = t_end - t_delta
    p2 = spread <= 1.0

    # P3 exposure contrast
    km_d = P[DELTA_START]["river_km"]
    km_m = P["Mirebalais"]["river_km"] + 2.0                                 # leave the Mirebalais town reaches out of the middle
    def density(a, b):
        ppl = sum(r["pop"] for r in reaches if a <= (r["km0"] + r["km1"]) / 2 < b)
        return ppl, b - a, ppl / max(b - a, 1e-9)
    mid = density(km_m, km_d)
    dlt = density(km_d, summ["km"] + 0.01)
    ratio = dlt[2] / mid[2] if mid[2] else float("inf")
    p3 = ratio >= 3

    # P4 flow
    p4 = summ["q_end"] > 100

    res = {
        "updated": str(dt.date.today()), "origin": ORIGIN[0], "velocity": {"a": vel["a"], "b": vel["b"], "err_factor": round(err, 2)},
        "trace": {"km": summ["km"], "days": summ["days"], "q_start": summ["q_start"], "q_end": summ["q_end"],
                  "dilution": summ["dilution"], "pop_5km": summ["pop_5km"]},
        "places": places,
        "tests": {
            "P1": {"pass": p1, "criterion": CRIT["P1"], "travel_to_delta_days": t_delta,
                   "implied_release": [str(earliest), str(central), str(latest)], "max_travel_that_passes_days": max_travel},
            "P2": {"pass": p2, "criterion": CRIT["P2"], "arrival_desarmes_days": t_delta, "arrival_sea_days": t_end,
                   "spread_days": round(spread, 2), "speed_needed_factor": round(spread / 1.0, 2)},
            "P3": {"pass": p3, "criterion": CRIT["P3"], "middle": {"people": mid[0], "km": round(mid[1], 1), "per_km": round(mid[2])},
                   "delta": {"people": dlt[0], "km": round(dlt[1], 1), "per_km": round(dlt[2])}, "ratio": round(ratio, 2)},
            "P4": {"pass": p4, "criterion": CRIT["P4"], "q_end": summ["q_end"]},
        },
    }
    (ROOT / "web/data/validation.json").write_text(json.dumps({"haiti2010": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(res)
    for k, t in res["tests"].items():
        print(k, "PASS" if t["pass"] else "FAIL", {x: y for x, y in t.items() if x not in ("criterion", "pass")})


def write_md(r):
    t = r["tests"]
    ok = lambda b: "**PASS**" if b else "**FAIL**"
    L = ["# Validation: Haiti 2010 (out of sample)", "",
         f"Generated {r['updated']} by `build/validate_haiti.py`. Haiti was not used to fit the travel-time model "
         f"(v = {r['velocity']['a']:.2f} · Q^{r['velocity']['b']:.2f}, calibrated on spills only - see CALIBRATION.md), "
         "and the pass/fail criteria were fixed in the script before the run.", "",
         "Observed facts: Piarroux et al. 2011, *Emerging Infectious Diseases* 17(7), doi:10.3201/eid1707.110059. "
         "Incubation: Azman et al. 2013, *J Infect* 66:432-8 (5 % by 0.5 d, median 1.4 d, 95 % by 4.4 d).", "",
         f"Trace from {r['origin']}: {r['trace']['km']} km to the sea in {r['trace']['days']} d, mean flow "
         f"{r['trace']['q_start']} -> {r['trace']['q_end']} m³/s (dilution ×{r['trace']['dilution']}), "
         f"{r['trace']['pop_5km']:,} people within 5 km.", "",
         "| Test | Result | What the model says |", "|---|---|---|",
         f"| P1 timing | {ok(t['P1']['pass'])} | front reaches Desarmes after {t['P1']['travel_to_delta_days']} d; a delta onset on Oct 19 "
         f"implies a release between {t['P1']['implied_release'][0]} and {t['P1']['implied_release'][2]} "
         f"(central {t['P1']['implied_release'][1]}); the camp was contaminating Oct 12-19. Any travel time up to "
         f"{t['P1']['max_travel_that_passes_days']} d would pass, so this test only rules out a much slower river. |",
         f"| P2 simultaneity | {ok(t['P2']['pass'])} | front at Desarmes after {t['P2']['arrival_desarmes_days']} d, at the sea after "
         f"{t['P2']['arrival_sea_days']} d: a spread of {t['P2']['spread_days']} d across the delta, observed ≤ 1 d. |",
         f"| P3 exposure contrast | {ok(t['P3']['pass'])} | {t['P3']['delta']['per_km']:,} people per river-km in the delta vs "
         f"{t['P3']['middle']['per_km']:,} on the middle stretch: ×{t['P3']['ratio']} (needed ×3; observed cases: thousands vs 0-2). |",
         f"| P4 flow | {ok(t['P4']['pass'])} | mean flow at the mouth {t['P4']['q_end']} m³/s (paper: usually >100 m³/s in October). |",
         "", "## Criteria (fixed before the run)", ""]
    L += [f"- **{k}** {v['criterion']}" for k, v in t.items()]
    L += ["", "## Places along the trace", "", "| Place | Distance to the traced river | River km from Meille | Model arrival |", "|---|---|---|---|"]
    L += [f"| {p['name']} | {p['dist_km']} km | {p['river_km']} | {p['days']} d |" for p in r["places"]]
    struck = ["Saint-Marc", "Dessalines", "Desdunes", "Grande Saline", "L'Estere", "Petite-Riviere-de-l'Artibonite", "Verrettes"]
    far = [p for p in r["places"] if p["name"] in struck and p["dist_km"] > 5]
    L += ["", "## What this means", "",
          "- Path: the trace runs from Meille past Mirebalais, through the thinly settled middle valley, into the delta and out "
          "at Grande Saline, the coastal commune the paper names; every delta place lies along it in the right order.",
          f"- Timing ({'passed' if t['P1']['pass'] else 'failed'}) is only a weak test, because the release date is not known to the day: "
          f"anything up to {t['P1']['max_travel_that_passes_days']} d would have passed."]
    if not t["P2"]["pass"]:
        L.append(f"- Simultaneity failed: one channel's front needs {t['P2']['spread_days']} d to cross the delta, but the delta fell ill "
                 "within a day. In the delta, irrigation canals take river water to rice fields and villages at the same time "
                 "(67 % of early patients drank untreated river or canal water, CDC MMWR 2010), which a single-channel model cannot show.")
    if not t["P3"]["pass"]:
        L.append(f"- Exposure contrast failed (×{t['P3']['ratio']}, needed ×3): a flat 5 km band does not capture who drinks the river. "
                 f"{len(far)} of the 7 struck delta communes have their town {min(p['dist_km'] for p in far) if far else 0:g}-"
                 f"{max(p['dist_km'] for p in far) if far else 0:g} km from the main channel ({', '.join(p['name'] for p in far)}), "
                 "outside the band, while hill villages inside the band on the middle stretch stayed almost free of cases. "
                 "The paper's own risk factor is 'coastal plain' (RR 4.60).")
    L.append("- Consequence for the map: path and travel time are shown as tested; exposure is shown only as a relative index "
             "with ranges and its known blind spots (canals, floodplains), never as a count of the ill or the dead.")
    (ROOT / "docs/VALIDATION.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
