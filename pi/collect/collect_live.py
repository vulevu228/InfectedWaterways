"""Infected Waterways - Milestone 2 collector (runs daily on the Pi, waterways-collect.timer).

Sources (all open, no key):
  cholera  WHO Global Cholera and AWD dashboard: weekly cases + deaths by country since 2023
           https://who.maps.arcgis.com/sharing/rest/content/items/6d435a537d534bac95b072fd6d999355/data
  don      WHO Disease Outbreak News API, every report since 1996 (incremental after the first run)
           https://www.who.int/api/news/diseaseoutbreaknews
  floods   GDACS flood events, last 120 days
           https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=FL
  wash     WHO Global Health Observatory: share of each country's population using at least basic / safely managed
           drinking-water services (WSH_WATER_BASIC, WSH_WATER_SAFELY_MANAGED; JMP data, latest year per country)
           https://ghoapi.azureedge.net/api/WSH_WATER_BASIC
  flow     Open-Meteo Flood API (GloFAS v4 river discharge, CC BY 4.0, non-commercial) at one virtual gauge near the
           mouth of each of the 150 largest river systems: last 30 days + 7-day forecast, and the same +-15 day window
           in each of the previous 5 years as the "normal" baseline.

Run:  python3 collect_live.py [cholera] [don] [floods] [wash] [flow] [--setup-gauges]   (no args = all five)
"""
import csv
import datetime as dt
import html
import io
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import psycopg

DSN = os.environ.get("IW_DSN", "dbname=waterways")
UA = {"User-Agent": "InfectedWaterways/1.0 (private research map)"}
CHOLERA_CSV = "https://who.maps.arcgis.com/sharing/rest/content/items/6d435a537d534bac95b072fd6d999355/data"
DON_API = "https://www.who.int/api/news/diseaseoutbreaknews"
GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
FLOOD = "https://flood-api.open-meteo.com/v1/flood"
GHO = "https://ghoapi.azureedge.net/api/"
N_GAUGES = 150
BASE_YEARS = 5
WINDOW = 15            # +- days around today's date in each baseline year
BATCH = 25             # coordinates per Open-Meteo request
PAUSE = 7              # s between Open-Meteo requests (600 weighted calls / minute limit)
WATERBORNE = re.compile(r"cholera|acute watery diarrh|typhoid|paratyphoid|hepatitis e\b|hepatitis a\b|shigell|dysenter|"
                        r"e\.? ?coli|haemolytic uraemic|hemolytic uremic|leptospir|cryptosporid|rotavirus|norovirus|"
                        r"diarrho?eal|enteric fever", re.I)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("waterways-collect")


def get(url, timeout=120, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            log.warning("retry %s: %s", url[:100], e)
            time.sleep(10 * (i + 1))


# ----------------------------------------------------------------------------------------------------- cholera
def cholera(c):
    rows = list(csv.DictReader(io.StringIO(get(CHOLERA_CSV).decode("utf-8-sig"))))
    data = [(r["iso_3_code"], r["adm0_viz_n"] or r["adm0_name"].title(), r["date_wk"], int(float(r["cases"] or 0)),
             int(float(r["deaths"] or 0)), r["who_region"], float(r["center_lon"] or 0), float(r["center_lat"] or 0))
            for r in rows if r["iso_3_code"] and r["date_wk"]]
    with c.transaction():
        c.execute("DELETE FROM cholera_week")   # WHO revises past weeks; the file is small, so replace it
        with c.cursor().copy("COPY cholera_week (iso3, country, week, cases, deaths, who_region, lon, lat) FROM STDIN") as cp:
            for d in data:
                cp.write_row(d)
    log.info("cholera: %d country-weeks, latest %s", len(data), max(d[2] for d in data))


# ----------------------------------------------------------------------------------------------------- DON
ALIASES = {"drc": "COD", "democratic republic of the congo": "COD", "congo": "COG", "republic of the congo": "COG",
           "united republic of tanzania": "TZA", "tanzania": "TZA", "türkiye": "TUR", "turkey": "TUR",
           "côte d'ivoire": "CIV", "cote d'ivoire": "CIV", "lao people's democratic republic": "LAO", "viet nam": "VNM",
           "syrian arab republic": "SYR", "iran (islamic republic of)": "IRN", "bolivia (plurinational state of)": "BOL",
           "venezuela (bolivarian republic of)": "VEN", "republic of korea": "KOR", "russian federation": "RUS",
           "united states of america": "USA", "united kingdom": "GBR", "kingdom of saudi arabia": "SAU", "eswatini": "SWZ",
           "zaire": "COD", "uk": "GBR", "tadjikistan": "TJK", "the philipines": "PHL", "philipines": "PHL",
           "côte d'ivoir": "CIV", "the gambia": "GMB", "gambia": "GMB", "south sudan": "SSD", "republic of south sudan": "SSD"}


def parse_title(t):
    t = re.sub(r"\s+", " ", html.unescape(t)).strip()
    t = re.sub(r"^\d{4}\s*-\s*", "", t)                    # old style "2010 - Cholera in Haiti - update"
    t = re.sub(r"\s*[-–—]\s*update\s*\d*\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*\((new outbreak|update)\)\s*$", "", t, flags=re.I)
    t = re.sub(r"^(\w[\w ]*?)\s*-\s*(?=[A-Z])", lambda m: m.group(1) + " – ", t) if " – " not in t and " in " not in t else t   # "Cholera- Haiti"
    if re.match(r"^[\w ]+, [A-Z]", t) and " – " not in t and " in " not in t:   # "Cholera, Comoros"
        dis, _, ctry = t.partition(", ")
    elif " – " in t or " — " in t:
        dis, _, ctry = re.split(r"( – | — )", t, maxsplit=1)
    elif " in " in t:
        dis, _, ctry = t.partition(" in ")
    elif " - " in t:
        dis, _, ctry = t.partition(" - ")
    else:
        dis, ctry = t, ""
    return dis.strip(), re.sub(r"\s*\(.*?update.*?\)\s*$", "", ctry, flags=re.I).strip(" .")


def don(c):
    names = {n.lower(): i for i, n in c.execute("SELECT iso3, name FROM countries")}
    names.update(ALIASES)
    known = {r[0] for r in c.execute("SELECT url_name FROM don_reports")}
    skip, new = 0, 0
    while True:
        q = urllib.parse.urlencode({"$orderby": "PublicationDateAndTime desc", "$top": 100, "$skip": skip,
                                    "$select": "Title,PublicationDateAndTime,UrlName,Summary"})
        page = json.loads(get(f"{DON_API}?{q}"))["value"]
        if not page:
            break
        fresh = [p for p in page if p["UrlName"] not in known]
        for p in fresh:
            dis, ctry = parse_title(p["Title"] or "")
            iso = names.get(ctry.lower())
            if not iso:   # "Cholera – Global situation", multi-country titles, small spelling differences
                iso = next((v for k, v in names.items() if len(k) > 4 and k in ctry.lower()), None)
            summ = re.sub(r"<[^>]+>", " ", html.unescape(p.get("Summary") or ""))
            c.execute("""INSERT INTO don_reports (url_name, published, title, disease, country, iso3, kind, summary)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (url_name) DO NOTHING""",
                      (p["UrlName"], p["PublicationDateAndTime"], p["Title"], dis, ctry, iso,
                       "waterborne" if WATERBORNE.search(p["Title"] or "") else "other", re.sub(r"\s+", " ", summ).strip()[:600]))
            new += 1
        if known and len(fresh) < len(page):   # reached reports we already have
            break
        skip += 100
        time.sleep(1)
    log.info("don: %d new reports", new)


# ----------------------------------------------------------------------------------------------------- floods
def floods(c):
    today = dt.date.today()
    feats = []
    for page in range(1, 30):   # 100 events per page; green alerts are hidden unless asked for
        q = urllib.parse.urlencode({"eventlist": "FL", "fromdate": str(today - dt.timedelta(days=120)), "todate": str(today),
                                    "alertlevel": "green;orange;red", "pagenumber": page})
        got = json.loads(get(f"{GDACS}?{q}")).get("features") or []
        feats += got
        if len(got) < 100:
            break
        time.sleep(1)
    feats = list({f["properties"]["eventid"]: f for f in feats}.values())
    for f in feats:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        c.execute("""INSERT INTO floods (eventid, episodeid, name, country, iso3, alert, alertscore, from_date, to_date, is_current,
                                          source, report_url, geom, props, updated)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,ST_SetSRID(ST_Point(%s,%s),4326),%s,now())
                     ON CONFLICT (eventid) DO UPDATE SET episodeid=EXCLUDED.episodeid, name=EXCLUDED.name, alert=EXCLUDED.alert,
                       alertscore=EXCLUDED.alertscore, to_date=EXCLUDED.to_date, is_current=EXCLUDED.is_current,
                       geom=EXCLUDED.geom, props=EXCLUDED.props, updated=now()""",
                  (p["eventid"], p.get("episodeid"), p.get("name"), p.get("country"), (p.get("iso3") or "")[:3] or None,
                   p.get("alertlevel"), p.get("alertscore"), p.get("fromdate"), p.get("todate"),
                   str(p.get("iscurrent")).lower() == "true", p.get("source"), (p.get("url") or {}).get("report"),
                   lon, lat, json.dumps(p)))
    # events that dropped out of the 120-day list are no longer current
    c.execute("UPDATE floods SET is_current = false WHERE updated < now() - interval '2 days'")
    log.info("floods: %d events, %d current", len(feats), sum(str(f["properties"].get("iscurrent")).lower() == "true" for f in feats))


# ----------------------------------------------------------------------------------------------------- flow
def flood_api(coords, **params):
    q = urllib.parse.urlencode({"latitude": ",".join(f"{y:.3f}" for _, y in coords), "longitude": ",".join(f"{x:.3f}" for x, _ in coords),
                                "daily": "river_discharge", "cell_selection": "nearest", **params})
    d = json.loads(get(f"{FLOOD}?{q}"))
    time.sleep(PAUSE)
    return d if isinstance(d, list) else [d]


def setup_gauges(c):
    """Pick a point on the main stem of the N largest systems (~8 % of the length, max 150 km, above the mouth) and snap
    it to the GloFAS cell with the largest discharge in a 5 x 5 window (raw nearest cells often sit beside the channel)."""
    rows = c.execute("""
        SELECT m.main_riv, coalesce(nullif(m.name, ''), 'Unnamed river'), r.hyriv_id, r.dis_av_cms, r.dist_dn_km,
               ST_X(ST_LineInterpolatePoint(ST_GeometryN(r.geom, 1), 0.5)), ST_Y(ST_LineInterpolatePoint(ST_GeometryN(r.geom, 1), 0.5))
        FROM (SELECT * FROM mainstems ORDER BY dis_cms DESC LIMIT %s) m
        CROSS JOIN LATERAL (SELECT * FROM rivers r WHERE r.main_riv = m.main_riv AND r.dist_dn_km >= least(150, 0.08 * m.len_km)
                            ORDER BY r.upland_skm DESC LIMIT 1) r""", (N_GAUGES,)).fetchall()
    done = {r[0] for r in c.execute("SELECT main_riv FROM gauges WHERE glon IS NOT NULL")}
    for main, name, hid, dis, ddn, lon, lat in rows:
        if main in done:
            continue
        cells = [(lon + dx * 0.05, lat + dy * 0.05) for dy in range(-2, 3) for dx in range(-2, 3)]
        res = flood_api(cells, past_days=30, forecast_days=1)
        best = max(zip(cells, res), key=lambda t: sum(v or 0 for v in t[1]["daily"]["river_discharge"]))
        qs = [v for v in best[1]["daily"]["river_discharge"] if v is not None]
        c.execute("""INSERT INTO gauges VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (main_riv) DO UPDATE SET
                     glon=EXCLUDED.glon, glat=EXCLUDED.glat, snap_q=EXCLUDED.snap_q""",
                  (main, name, hid, dis, ddn, lon, lat, best[0][0], best[0][1], sum(qs) / max(len(qs), 1)))
        log.info("gauge %-28s HydroRIVERS %8.0f m3/s, GloFAS 30-day mean %8.0f m3/s", name, dis, sum(qs) / max(len(qs), 1))


def store(c, mains, res):
    with c.cursor() as cur:
        for m, r in zip(mains, res):
            cur.executemany("""INSERT INTO gauge_flow VALUES (%s,%s,%s) ON CONFLICT (main_riv, day) DO UPDATE SET q = EXCLUDED.q""",
                            [(m, t, q) for t, q in zip(r["daily"]["time"], r["daily"]["river_discharge"]) if q is not None])


def wash(c):
    """Drinking-water service coverage per country (WHO GHO / JMP). Latest year per country, totals only (not urban/rural).

    The outbreak scenario needs the share of people who rely on unimproved or surface water: 100 - "at least basic".
    """
    cols = {"basic_pct": "WSH_WATER_BASIC", "safe_pct": "WSH_WATER_SAFELY_MANAGED"}
    best: dict[str, dict] = {}
    for col, ind in cols.items():
        rows = json.loads(get(GHO + ind))["value"]
        n = 0
        for r in rows:
            if r["SpatialDimType"] != "COUNTRY" or r.get("Dim1") != "RESIDENCEAREATYPE_TOTL" or r["NumericValue"] is None:
                continue
            k, y = r["SpatialDim"], int(r["TimeDim"])
            e = best.setdefault(k, {})
            if y >= e.get(col + "_y", 0):
                e[col], e[col + "_y"] = round(float(r["NumericValue"]), 1), y
                n += 1
        log.info("wash: %s -> %d country-year rows kept", ind, n)
    rows = [(k, v.get("basic_pct"), v.get("safe_pct"), max(v.get("basic_pct_y", 0), v.get("safe_pct_y", 0)) or None)
            for k, v in best.items() if v.get("basic_pct") is not None]
    with c.cursor() as cur:
        cur.executemany("""INSERT INTO wash (iso3, basic_pct, safe_pct, year) VALUES (%s, %s, %s, %s)
                           ON CONFLICT (iso3) DO UPDATE SET basic_pct = EXCLUDED.basic_pct,
                           safe_pct = EXCLUDED.safe_pct, year = EXCLUDED.year""", rows)
    log.info("wash: %d countries stored", len(rows))


def flow(c):
    g = c.execute("SELECT main_riv, glon, glat FROM gauges WHERE glon IS NOT NULL ORDER BY main_riv").fetchall()
    if not g:
        log.warning("flow: no gauges, run --setup-gauges first")
        return
    today = dt.date.today()
    batches = [g[i:i + BATCH] for i in range(0, len(g), BATCH)]
    for b in batches:   # current: last 30 days + 7-day forecast (GloFAS v4 forecast run, revised every day)
        store(c, [x[0] for x in b], flood_api([(x[1], x[2]) for x in b], past_days=30, forecast_days=7))
    for y in range(1, BASE_YEARS + 1):   # baseline: same calendar window in each of the previous years, only missing days
        try:
            mid = today.replace(year=today.year - y)
        except ValueError:   # 29 February
            mid = today.replace(year=today.year - y, day=28)
        lo, hi = mid - dt.timedelta(days=WINDOW), mid + dt.timedelta(days=WINDOW)
        have = dict(c.execute("SELECT day, count(*) FROM gauge_flow WHERE day BETWEEN %s AND %s GROUP BY day", (lo, hi)).fetchall())
        missing = [lo + dt.timedelta(days=i) for i in range((hi - lo).days + 1) if have.get(lo + dt.timedelta(days=i), 0) < len(g)]
        if not missing:
            continue
        for b in batches:
            store(c, [x[0] for x in b], flood_api([(x[1], x[2]) for x in b], start_date=str(min(missing)), end_date=str(max(missing))))
    log.info("flow: %d gauges updated", len(g))


def main(argv):
    c = psycopg.connect(DSN, autocommit=True)
    if "--setup-gauges" in argv:
        setup_gauges(c)
        return
    jobs = [a for a in argv if not a.startswith("-")] or ["cholera", "don", "floods", "wash", "flow"]
    failed = []
    for j in jobs:
        try:
            {"cholera": cholera, "don": don, "floods": floods, "wash": wash, "flow": flow}[j](c)
        except Exception:  # noqa: BLE001  one broken source must not stop the others
            log.exception("%s failed", j)
            failed.append(j)
    c.execute("CREATE TABLE IF NOT EXISTS collect_log (ts timestamptz DEFAULT now(), jobs text[], failed text[])")
    c.execute("INSERT INTO collect_log (jobs, failed) VALUES (%s, %s)", (jobs, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
