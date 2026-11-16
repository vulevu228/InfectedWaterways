"""Infected Waterways - private map + trace API on the Pi (stdlib http.server + psycopg 3).

Serves /mnt/ssd/waterways/web/site (pushed from the PC by scripts/push_to_pi.ps1) on
    127.0.0.1:8796           (ssh tunnel / local)
    <Tailscale IPv4>:8796    (own devices only)
Never on the LAN or the internet. Same pattern as The Count Down (countdown-web.service).

API
  GET /api/trace?lon=..&lat=..[&a=..&b=..]
      Snap to the nearest river reach with mean discharge >= 1 m3/s (max 25 km away), follow next_down to the mouth
      or inland sink, and return the path as GeoJSON with distance, mean discharge and travel time per reach,
      plus the cities (Natural Earth, <= 8 km from the river), countries and lakes (HydroLAKES) on the way.
      Travel time per reach = length / v, with v = a * Q^b (m/s, Q = mean discharge m3/s): downstream hydraulic
      geometry (Leopold & Maddock 1953). a, b come from the calibration in docs/CALIBRATION.md.
  GET /api/live      KPIs + layers for "the world now": WHO cholera (weekly), WHO DON waterborne reports, GDACS floods,
                     river flow vs the same season of the last 5 years (GloFAS). Cached 10 minutes. Filled by collect_live.py.
  GET /api/health
"""
import datetime as dt
import gzip
import http.server
import ipaddress
import json
import logging
import mimetypes
import os
import socketserver
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

import psycopg

ROOT = Path(os.environ.get("IW_WEB_ROOT", "/mnt/ssd/waterways/web/site")).resolve()
PORT = int(os.environ.get("IW_WEB_PORT", "8796"))
DSN = os.environ.get("IW_DSN", "dbname=waterways")
A_DEFAULT = float(os.environ.get("IW_V_A", 0.10))
B_DEFAULT = float(os.environ.get("IW_V_B", 0.30))
SNAP_KM = 25
TYPES = {".json": "application/json", ".geojson": "application/geo+json", ".html": "text/html; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png"}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("waterways-web")
_local = threading.local()


def db():
    c = getattr(_local, "conn", None)
    if c is None or c.closed:
        c = psycopg.connect(DSN, autocommit=True)
        c.execute("SET statement_timeout = '20s'")
        _local.conn = c
    return c


SQL_SNAP = """
SELECT hyriv_id, ST_Distance(geom::geography, p::geography) / 1000 AS km
FROM rivers, ST_SetSRID(ST_Point(%(lon)s, %(lat)s), 4326) p
ORDER BY geom <-> p LIMIT 8
"""
SQL_PATH = """
WITH RECURSIVE d AS (
  SELECT hyriv_id, next_down, 1 AS n FROM rivers WHERE hyriv_id = %(id)s
  UNION ALL
  SELECT r.hyriv_id, r.next_down, d.n + 1 FROM rivers r JOIN d ON r.hyriv_id = d.next_down WHERE d.n < 30000
)
SELECT d.n, r.hyriv_id, r.length_km, r.dis_av_cms, r.upland_skm, r.main_riv, r.endorheic,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(r.geom, 0.0005), 5) AS g
FROM d JOIN rivers r USING (hyriv_id) ORDER BY d.n
"""
SQL_NEAR = """
WITH path AS (SELECT n, geom FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY u(id, n) JOIN rivers r ON r.hyriv_id = u.id)
SELECT DISTINCT ON (pl.id) pl.name, pl.country, pl.pop_max, pl.capital, path.n,
       ST_X(pl.geom), ST_Y(pl.geom), ST_Distance(pl.geom::geography, path.geom::geography) / 1000 AS km
FROM path JOIN places pl ON ST_DWithin(pl.geom, path.geom, 0.08)
WHERE ST_DWithin(pl.geom::geography, path.geom::geography, 8000)
ORDER BY pl.id, path.n
"""
SQL_COUNTRIES = """
WITH path AS (SELECT n, geom FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY u(id, n) JOIN rivers r ON r.hyriv_id = u.id),
pt AS (SELECT n, ST_LineInterpolatePoint(ST_GeometryN(geom, 1), 0.5) AS p FROM path)
SELECT pt.n, array_agg(DISTINCT c.iso3 ORDER BY c.iso3), array_agg(DISTINCT c.name ORDER BY c.name)
FROM pt JOIN countries_sub c ON ST_DWithin(c.geom, pt.p, 0.025)
GROUP BY pt.n ORDER BY pt.n
"""
SQL_LAKES = """
WITH path AS (SELECT n, geom FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY u(id, n) JOIN rivers r ON r.hyriv_id = u.id)
SELECT DISTINCT ON (l.hylak_id) l.name, l.type, l.area_km2, l.res_days, path.n
FROM path JOIN lakes_sub s ON ST_Intersects(s.geom, path.geom) JOIN lakes l USING (hylak_id)
ORDER BY l.hylak_id, path.n
"""

SQL_POP = """
WITH path AS (SELECT n, geom FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY u(id, n) JOIN rivers r ON r.hyriv_id = u.id)
SELECT n, sum(pop::float8) FROM (
  SELECT DISTINCT ON (p.id) p.id, p.pop, path.n
  FROM path JOIN pop p ON ST_DWithin(p.geom, path.geom, 0.09)
  WHERE ST_DWithin(p.geom::geography, path.geom::geography, 5000)
  ORDER BY p.id, path.n) x
GROUP BY n
"""

SANDWICH_KM = 220
NOISE_KM = 12   # runs shorter than this are absorbed into the previous run (river lines wobble around borders)


def countries_along(rows, cum, total_km):
    """Countries along the path. A reach whose midpoint has two countries within ~2.5 km is a border river."""
    runs = []
    for n, isos, names in rows:
        key = "/".join(isos[:2])
        if runs and runs[-1]["key"] == key:
            continue
        nm = " / ".join(sorted(names)[:2]) + " border river" if len(isos) > 1 else names[0]
        runs.append({"key": key, "name": nm, "border": len(isos) > 1, "km": cum[n][0], "h": cum[n][1]})
    for i, r in enumerate(runs):
        r["end"] = runs[i + 1]["km"] if i + 1 < len(runs) else total_km
    out = []
    for r in runs:
        if out and (r["end"] - r["km"] < NOISE_KM or out[-1]["key"] == r["key"]):
            out[-1]["end"] = r["end"]
        else:
            out.append(r)
    # border - (one of its two countries, < SANDWICH_KM) - same border: the river stayed on the border, the line wobbled
    i = 1
    while i < len(out) - 1:
        p, m, nx = out[i - 1], out[i], out[i + 1]
        if p["border"] and nx["key"] == p["key"] and not m["border"] and m["key"] in p["key"].split("/")                 and m["end"] - m["km"] < SANDWICH_KM:
            p["end"] = nx["end"]
            del out[i:i + 2]
        else:
            i += 1
    return [{"name": r["name"], "iso3": r["key"], "border": r["border"], "km": round(r["km"], 1), "h": round(r["h"], 2),
             "len_km": round(r["end"] - r["km"], 1)} for r in out]


def q1(c, sql, args=None):
    return c.execute(sql, args or {}).fetchone()


def trace(lon: float, lat: float, a: float, b: float) -> dict:
    c = db()
    snaps = c.execute(SQL_SNAP, {"lon": lon, "lat": lat}).fetchall()
    snaps = [s for s in snaps if s[1] <= SNAP_KM]
    if not snaps:
        return {"error": f"No river with a mean discharge of at least 1 m³/s within {SNAP_KM} km of this point."}
    sid, snap_km = min(snaps, key=lambda s: s[1])
    rows = c.execute(SQL_PATH, {"id": sid}).fetchall()
    ids, feats, km, hours = [], [], 0.0, 0.0
    cum = {}
    for n, hid, length, q, up, main, endo, g in rows:
        q = max(q or 0.0, 0.1)
        v = a * q ** b
        h = (length or 0) * 1000 / v / 3600
        feats.append({"type": "Feature", "geometry": json.loads(g),
                      "properties": {"n": n, "id": hid, "km0": round(km, 2), "h0": round(hours, 3), "q": round(q, 1),
                                     "v": round(v, 3), "up": round(up or 0)}})
        cum[n] = (km, hours)
        km += length or 0
        hours += h
        ids.append(hid)
    near = c.execute(SQL_NEAR, {"ids": ids}).fetchall()
    cities = sorted(({"name": nm, "country": co, "pop": int(pop or 0), "capital": cap == "capital", "km": round(cum[n][0], 1),
                      "h": round(cum[n][1], 2), "lon": round(x, 4), "lat": round(y, 4), "off_km": round(d, 1)}
                     for nm, co, pop, cap, n, x, y, d in near), key=lambda r: r["km"])
    seq = countries_along(c.execute(SQL_COUNTRIES, {"ids": ids}).fetchall(), cum, km)
    lakes = sorted(({"name": nm or "Unnamed lake", "type": t, "area_km2": round(ar or 0, 1), "res_days": round(r or 0, 1),
                     "km": round(cum[n][0], 1), "h": round(cum[n][1], 2)}
                    for nm, t, ar, r, n in c.execute(SQL_LAKES, {"ids": ids}).fetchall()), key=lambda r: r["km"])
    pop_by_n = {}
    if q1(c, "SELECT to_regclass('pop')")[0]:
        pop_by_n = {n: float(v) for n, v in c.execute(SQL_POP, {"ids": ids}).fetchall()}
    for f in feats:
        f["properties"]["pop"] = round(pop_by_n.get(f["properties"]["n"], 0))
    main = rows[-1][5] if rows else None
    name = c.execute("SELECT nullif(name, '') FROM mainstems WHERE main_riv = %s", (main,)).fetchone()
    return {"type": "FeatureCollection", "features": feats,
            "summary": {"start_id": sid, "snap_km": round(snap_km, 2), "reaches": len(rows), "km": round(km, 1),
                        "hours": round(hours, 1), "days": round(hours / 24, 2), "q_start": feats[0]["properties"]["q"],
                        "q_end": feats[-1]["properties"]["q"], "dilution": round(feats[-1]["properties"]["q"] / feats[0]["properties"]["q"], 1),
                        "ends": "inland sink" if rows[-1][6] else "sea", "system": name[0] if name else None,
                        "system_id": main, "pop_5km": round(sum(pop_by_n.values())), "velocity": {"a": a, "b": b, "formula": "v = a * Q^b (m/s)"}},
            "cities": cities, "countries": seq, "lakes": lakes}


LIVE_TTL = 600
_live_cache = {"t": 0, "v": None}


def live(c) -> dict:
    """Milestone 2: what is happening now. Every KPI comes with a comparison period."""
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # ---- cholera (WHO weekly). Reports lag by weeks: the window ends one week before the newest reported week.
    latest = q1(c, "SELECT max(week) FROM cholera_week")[0]
    if latest:
        end = latest - dt.timedelta(days=7)
        r = q1(c, """SELECT
              sum(cases) FILTER (WHERE week > %(e)s - 28 AND week <= %(e)s),
              sum(cases) FILTER (WHERE week > %(e)s - 56 AND week <= %(e)s - 28),
              count(DISTINCT iso3) FILTER (WHERE week > %(e)s - 28 AND week <= %(e)s AND cases > 0),
              count(DISTINCT iso3) FILTER (WHERE week > %(e)s - 56 AND week <= %(e)s - 28 AND cases > 0),
              sum(cases) FILTER (WHERE week >= date_trunc('year', %(e)s::date) AND week <= %(e)s),
              sum(cases) FILTER (WHERE week >= date_trunc('year', %(e)s::date) - interval '1 year' AND week <= %(e)s - interval '1 year'),
              sum(deaths) FILTER (WHERE week >= date_trunc('year', %(e)s::date) AND week <= %(e)s),
              sum(deaths) FILTER (WHERE week >= date_trunc('year', %(e)s::date) - interval '1 year' AND week <= %(e)s - interval '1 year')
            FROM cholera_week""", {"e": end})
        out["cholera"] = {"latest_week": str(latest), "window_end": str(end), "cases_4w": r[0] or 0, "cases_prev4w": r[1] or 0,
                          "countries_4w": r[2], "countries_prev4w": r[3], "cases_ytd": r[4] or 0, "cases_ytd_prev": r[5] or 0,
                          "deaths_ytd": r[6] or 0, "deaths_ytd_prev": r[7] or 0}
        rows = c.execute("""
            WITH w AS (SELECT generate_series(%(e)s::date - 7 * 25, %(e)s::date, interval '7 days')::date AS wk),
            spark AS (
              SELECT k.iso3, array_agg(coalesce(s.c, 0) ORDER BY w.wk) AS weekly
              FROM (SELECT DISTINCT iso3 FROM cholera_week) k CROSS JOIN w
              LEFT JOIN LATERAL (SELECT sum(cases) c FROM cholera_week x WHERE x.iso3 = k.iso3 AND x.week > w.wk - 7 AND x.week <= w.wk) s ON true
              GROUP BY k.iso3)
            SELECT k.iso3, max(k.country), max(k.lon), max(k.lat),
                   sum(k.cases) FILTER (WHERE k.week > %(e)s - 28 AND k.week <= %(e)s),
                   sum(k.cases) FILTER (WHERE k.week > %(e)s - 56 AND k.week <= %(e)s - 28),
                   sum(k.cases) FILTER (WHERE k.week > %(e)s - 84 AND k.week <= %(e)s),
                   sum(k.deaths) FILTER (WHERE k.week > %(e)s - 84 AND k.week <= %(e)s),
                   sum(k.cases) FILTER (WHERE k.week >= date_trunc('year', %(e)s::date) AND k.week <= %(e)s),
                   max(k.week) FILTER (WHERE k.cases > 0), max(sp.weekly)
            FROM cholera_week k JOIN spark sp USING (iso3) GROUP BY k.iso3""", {"e": end}).fetchall()
        out["cholera_countries"] = [{"iso3": i, "name": n, "lon": x, "lat": y, "cases_4w": a or 0, "cases_prev4w": b or 0,
                                     "cases_12w": d or 0, "deaths_12w": e or 0, "cases_ytd": f or 0, "last_case_week": str(g) if g else None,
                                     "weekly": [int(v) for v in sp]}
                                    for i, n, x, y, a, b, d, e, f, g, sp in rows if (d or 0) > 0 or (f or 0) > 0]
    # ---- WHO Disease Outbreak News: waterborne reports
    r = q1(c, """SELECT count(*) FILTER (WHERE published > now() - interval '365 days'),
                        count(*) FILTER (WHERE published <= now() - interval '365 days' AND published > now() - interval '730 days')
                 FROM don_reports WHERE kind = 'waterborne'""")
    out["don"] = {"waterborne_365": r[0], "waterborne_prev365": r[1],
                  "by_year": [{"year": int(y), "n": n} for y, n in c.execute(
                      "SELECT extract(year FROM published), count(*) FROM don_reports WHERE kind = 'waterborne' GROUP BY 1 ORDER BY 1")]}
    out["don_reports"] = [{"id": u, "date": str(p.date()), "title": t, "disease": d, "country": co, "iso3": i, "summary": sm,
                           "lon": x, "lat": y, "url": f"https://www.who.int/emergencies/disease-outbreak-news/item/{u}"}
                          for u, p, t, d, co, i, sm, x, y in c.execute("""
        SELECT d.url_name, d.published, d.title, d.disease, d.country, d.iso3, d.summary, ST_X(ct.p), ST_Y(ct.p)
        FROM don_reports d LEFT JOIN LATERAL (SELECT ST_PointOnSurface(geom) p FROM countries WHERE iso3 = d.iso3
                                              ORDER BY ST_Area(geom) DESC LIMIT 1) ct ON true
        WHERE d.kind = 'waterborne' AND d.published > now() - interval '3 years' ORDER BY d.published DESC""")]
    # ---- GDACS floods
    fl = c.execute("""SELECT eventid, name, country, iso3, alert, from_date::date, to_date::date, is_current, report_url,
                             ST_X(geom), ST_Y(geom), props->'severitydata'->>'severitytext'
                      FROM floods WHERE is_current OR to_date > now() - interval '30 days' ORDER BY to_date DESC""").fetchall()
    out["floods"] = [{"id": e, "name": n, "country": co, "iso3": i, "alert": a, "from": str(f), "to": str(t), "current": cur,
                      "url": u, "lon": x, "lat": y, "severity": sv} for e, n, co, i, a, f, t, cur, u, x, y, sv in fl]
    cur_fl = [f for f in out["floods"] if f["current"]]
    out["flood_kpi"] = {"current": len(cur_fl), "current_orange_red": sum(f["alert"] in ("Orange", "Red") for f in cur_fl),
                        "last30": len(out["floods"]), "countries": sorted({f["country"] for f in cur_fl if f["country"]})}
    # ---- river flow now vs the same season in the previous 5 years (GloFAS via Open-Meteo)
    g = c.execute("""
        WITH base AS (
          SELECT f.main_riv, percentile_cont(0.5) WITHIN GROUP (ORDER BY f.q) AS med,
                 percentile_cont(0.1) WITHIN GROUP (ORDER BY f.q) AS p10, percentile_cont(0.9) WITHIN GROUP (ORDER BY f.q) AS p90
          FROM gauge_flow f, generate_series(1, 5) y
          WHERE abs(f.day - (current_date - make_interval(years => y))::date) <= 15 GROUP BY 1),
        cur AS (
          SELECT main_riv, avg(q) FILTER (WHERE day > current_date - 7 AND day <= current_date) AS now7,
                 avg(q) FILTER (WHERE day > current_date AND day <= current_date + 7) AS next7,
                 array_agg(q ORDER BY day) AS spark, min(day) AS d0
          FROM gauge_flow WHERE day > current_date - 30 GROUP BY 1)
        SELECT g.main_riv, g.name, g.lon, g.lat, g.dis_av, cur.now7, cur.next7, base.med, base.p10, base.p90, cur.spark, cur.d0
        FROM gauges g JOIN cur USING (main_riv) JOIN base USING (main_riv) WHERE base.med > 0""").fetchall()
    gauges = []
    for m, n, x, y, dis, now7, next7, med, p10, p90, spark, d0 in g:
        if now7 is None or (dis or 0) > 0 and p90 < 0.1 * dis:   # GloFAS cell missed the channel: seasonal high < 10 % of the mean
            continue
        ratio = now7 / med
        gauges.append({"main": m, "name": n, "lon": x, "lat": y, "dis_av": round(dis or 0), "now7": round(now7, 1),
                       "next7": round(next7, 1) if next7 else None, "median": round(med, 1), "p10": round(p10, 1), "p90": round(p90, 1),
                       "ratio": round(ratio, 2), "spark": [round(v, 1) for v in spark], "spark_from": str(d0),
                       "cls": "very high" if ratio >= 2 else "high" if ratio >= 1.25 else "very low" if ratio <= 0.5
                       else "low" if ratio <= 0.8 else "normal"})
    out["gauges"] = gauges
    out["flow_kpi"] = {"n": len(gauges), "above": sum(x["ratio"] >= 1.25 for x in gauges), "below": sum(x["ratio"] <= 0.8 for x in gauges),
                       "far_above": sum(x["ratio"] >= 2 for x in gauges), "far_below": sum(x["ratio"] <= 0.5 for x in gauges)}
    # ---- overlap: countries with cholera in the last 4 weeks and a river flood now
    chol4 = {x["iso3"]: x["name"] for x in out.get("cholera_countries", []) if x["cases_4w"] > 0}
    out["overlap"] = sorted({chol4[f["iso3"]] for f in cur_fl if f["iso3"] in chol4})
    out["static"] = dict(c.execute("SELECT key, value FROM meta").fetchall()) if q1(c, "SELECT to_regclass('meta')")[0] else {}
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "waterways"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype: str, gz=False, cache="no-cache"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")   # only reachable on 127.0.0.1 and the private tailnet
        if gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        raw = json.dumps(obj, separators=(",", ":")).encode()
        if "gzip" in self.headers.get("Accept-Encoding", "") and len(raw) > 1400:
            return self._send(code, gzip.compress(raw, 5), "application/json", gz=True)
        self._send(code, raw, "application/json")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path == "/api/health":
            try:
                n = db().execute("SELECT count(*) FROM rivers").fetchone()[0]
                return self._json({"ok": True, "reaches": n})
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)[:200]}, 503)
        if u.path == "/api/live":
            try:
                if time.time() - _live_cache["t"] > LIVE_TTL:
                    _live_cache["v"], _live_cache["t"] = live(db()), time.time()
                return self._json(_live_cache["v"])
            except Exception as e:  # noqa: BLE001
                log.exception("live failed")
                _local.conn = None
                return self._json({"error": "live failed: " + str(e)[:160]}, 500)
        if u.path == "/api/trace":
            q = urllib.parse.parse_qs(u.query)
            try:
                lon, lat = float(q["lon"][0]), float(q["lat"][0])
                a = min(max(float(q.get("a", [A_DEFAULT])[0]), 0.02), 5.0)
                b = min(max(float(q.get("b", [B_DEFAULT])[0]), 0.0), 0.6)
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError
            except (KeyError, ValueError):
                return self._json({"error": "lon and lat are required numbers"}, 400)
            t0 = time.time()
            try:
                out = trace(lon, lat, a, b)
            except Exception as e:  # noqa: BLE001
                log.exception("trace failed")
                _local.conn = None
                return self._json({"error": "trace failed: " + str(e)[:160]}, 500)
            out["ms"] = round((time.time() - t0) * 1000)
            return self._json(out)
        return self._static(u.path)

    def _static(self, path):
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        f = (ROOT / rel).resolve()
        if ROOT not in f.parents and f != ROOT or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = TYPES.get(f.suffix, mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        gzf = f.with_name(f.name + ".gz")
        st = f.stat()
        etag = f'"{int(st.st_mtime)}-{st.st_size}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        accept = "gzip" in self.headers.get("Accept-Encoding", "")
        body = (gzf if accept and gzf.is_file() else f).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        if accept and gzf.is_file():
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def tailscale_ip():
    try:
        ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10).stdout.split()[0]
        return ip if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10") else None
    except Exception:  # noqa: BLE001
        return None


def serve(host):
    s = Server((host, PORT), Handler)
    log.info("serving %s on %s:%d", ROOT, host, PORT)
    s.serve_forever()


def main():
    threading.Thread(target=serve, args=("127.0.0.1",), daemon=True).start()
    while True:
        ip = tailscale_ip()
        if ip:
            serve(ip)
        time.sleep(60)


if __name__ == "__main__":
    main()
