"""Generates the InfectedWaterways Power BI project (Milestone 6) from the CSV snapshots in powerbi/data/.

Data: build/export_bi.py copies the bi.* views (sql/04_bi.sql) from the Pi. Model: 6 CSV tables + _Measures, no DAX
calculated tables. Report: 4 pages, 1280 x 720, the light "product UI" design of the Sky & Sea report
(SkyAndSeaLakehouse/powerbi_build/gen_pbip.py): designed page backgrounds with white rounded cards and an icon rail,
transparent visuals on top, Segoe UI Light hero numbers, pill slicers.
Pages: Cholera now / Floods -> cholera / Unsafe water / Outbreak news.
Re-running overwrites model + pages: snapshot + semantic diff first if the user saved in Desktop.
Run with the global Python (needs Pillow):  py build/gen_pbip.py
"""
import hashlib, json, os, re, shutil, uuid

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "powerbi")).replace(os.sep, "/") + "/"
NAME = "InfectedWaterways"
REPORT = ROOT + NAME + ".Report/"
SM = ROOT + NAME + ".SemanticModel/"
MODEL = SM + "definition/"
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "powerbi", "data")) + os.sep
TEMPLATE = os.path.join(HERE, "..", "..", "HamburgTrainDelays", "powerbi", "hamburg_delays")  # file template

# ============================================================== design tokens (Sky & Sea, light)
WALL, CANVAS, CARD, LINE = "#E4E8EC", "#EEF1F4", "#FFFFFF", "#E3E7EC"
INK1, INK2, INK3 = "#111418", "#4F5865", "#8A94A1"
WATER, GREEN, ALERT = "#2A78D6", "#1BAF7A", "#EB6834"   # validated categorical slots (light)
GHOST = "#B8C0CA"                                      # "before" / comparison bars
DARK = "#16191D"
BAND_COLORS = {0: GHOST, 1: "#8FB2DE", 2: "#F2A47F", 3: ALERT}
FONT_H, FONT_B, FONT_L = "Segoe UI Semibold", "Segoe UI", "Segoe UI Light"
W, H = 1280, 720
MEAS = "_Measures"
SCALE = 2


def guid(seed):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "infected-waterways/" + seed))


def hid(seed):
    return hashlib.md5(("infected-waterways/" + seed).encode()).hexdigest()[:20]


def tq(n):
    return f"'{n}'" if re.search(r"[^A-Za-z0-9_]", n) else n


# ============================================================== M queries (CSV snapshots)
M, COLS = {}, {}
I64, NUM, TXT, DATE, BOOL = "Int64.Type", "type number", "type text", "type date", "bool"


def table(name, csv, cols, extra="", added=()):
    """cols: (name, m_type, tmdl_type, format[, sortBy[, hidden]]). bool columns arrive as 't'/'f'."""
    typed = ", ".join(f'{{"{c[0]}", {c[1]}}}' for c in cols if c[1] != BOOL)
    bools = [c[0] for c in cols if c[1] == BOOL]
    steps = ['let',
             f'    Source = Csv.Document(File.Contents(DataFolder & "{csv}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
             '    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
             '    Kept = Table.SelectColumns(Promoted, {' + ", ".join(f'"{c[0]}"' for c in cols) + '}),',
             '    Nulls = Table.TransformColumns(Kept, {}, each if _ = "" then null else _),',
             f'    Typed = Table.TransformColumnTypes(Nulls, {{{typed}}}, "en-US")']
    last = "Typed"
    if bools:
        steps[-1] += ","
        steps.append('    Flags = Table.TransformColumns(Typed, {' + ", ".join(f'{{"{b}", each _ = "t", type logical}}' for b in bools) + '})')
        last = "Flags"
    if extra:
        steps[-1] += ","
        steps.append(extra.replace("{prev}", last))
        last = extra.strip().split("\n")[-1].split("=")[0].strip()
    M[name] = "\n".join(steps) + f"\nin\n    {last}"
    COLS[name] = [(c[0], c[2], c[3]) + tuple(c[4:]) for c in list(cols) + list(added)]


table("DimWeek", "dim_week",
      [("week", DATE, "date", "dd mmm yyyy"), ("week_key", I64, "int64", "0", None, True), ("iso_year", I64, "int64", "0"),
       ("iso_week", I64, "int64", "0"), ("week_label", TXT, "string", None, "week_key")])
table("DimCountry", "country",
      [("iso3", TXT, "string", None), ("country", TXT, "string", None), ("who_region", TXT, "string", None),
       ("pop", I64, "int64", "#,##0"), ("pop_year", I64, "int64", "0"), ("basic_pct", NUM, "double", "0.0"),
       ("safe_pct", NUM, "double", "0.0"), ("wash_year", I64, "int64", "0"), ("unsafe_pct", NUM, "double", "0.0"),
       ("unsafe_band", TXT, "string", None, "band_order"), ("band_order", I64, "int64", "0", None, True),
       ("has_cholera", BOOL, "boolean", None)])
table("FactCholera", "cholera_week",
      [("iso3", TXT, "string", None), ("week", DATE, "date", "dd mmm yyyy"), ("region", TXT, "string", None),
       ("cases", I64, "int64", "#,##0"), ("deaths", I64, "int64", "#,##0")],
      extra='    #"Added week_key" = Table.AddColumn({prev}, "week_key", each Date.Year([week]) * 10000 + Date.Month([week]) * 100 + Date.Day([week]), Int64.Type)',
      added=[("week_key", None, "int64", "0", None, True)])
table("Flood", "flood",
      [("eventid", I64, "int64", "0"), ("iso3", TXT, "string", None), ("alert", TXT, "string", None, "alert_order"),
       ("alert_order", I64, "int64", "0", None, True), ("from_date", DATE, "date", "dd mmm yyyy"),
       ("week", DATE, "date", "dd mmm yyyy"), ("days", I64, "int64", "0"), ("name", TXT, "string", None)])
table("FloodLag", "flood_lag",
      [("eventid", I64, "int64", "0"), ("iso3", TXT, "string", None), ("alert", TXT, "string", None, "alert_order"),
       ("alert_order", I64, "int64", "0", None, True), ("flood_week", DATE, "date", "dd mmm yyyy"),
       ("lag_week", I64, "int64", "0", None, True), ("cases", I64, "int64", "#,##0"), ("baseline", NUM, "double", "#,##0.0"),
       ("ratio", NUM, "double", "0.00")],
      extra='    #"Added lag_label" = Table.AddColumn({prev}, "lag_label", each if [lag_week] > 0 then "+" & Text.From([lag_week]) else Text.From([lag_week]), type text)',
      added=[("lag_label", None, "string", None, "lag_week")])
table("Don", "don",
      [("url_name", TXT, "string", None), ("published", DATE, "date", "dd mmm yyyy"), ("year", I64, "int64", "0"),
       ("title", TXT, "string", None), ("country", TXT, "string", None), ("iso3", TXT, "string", None),
       ("kind", TXT, "string", None), ("disease_group", TXT, "string", None)])

ORDER = ["DimWeek", "DimCountry", "FactCholera", "Flood", "FloodLag", "Don", MEAS]
RELS = [("FactCholera", "week_key", "DimWeek", "week_key"), ("FactCholera", "iso3", "DimCountry", "iso3"),
        ("FloodLag", "iso3", "DimCountry", "iso3")]


def col_block(table, spec):
    name, dt, fmt = spec[0], spec[1], spec[2]
    sort = spec[3] if len(spec) > 3 else None
    hidden = spec[4] if len(spec) > 4 else False
    o = [f"\tcolumn {tq(name)}", f"\t\tdataType: {'dateTime' if dt == 'date' else dt}"]
    if hidden:
        o.append("\t\tisHidden")
    if fmt:
        o.append(f"\t\tformatString: {fmt}")
    o.append(f"\t\tlineageTag: {guid(f'c/{table}/{name}')}")
    o.append("\t\tsummarizeBy: none")
    o.append(f"\t\tsourceColumn: {name}")
    if sort:
        o.append(f"\t\tsortByColumn: {tq(sort)}")
    o += ["", "\t\tannotation SummarizationSetBy = Automatic"]
    if dt == "date":
        o += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
    o.append("")
    return o


def tmdl_table(t):
    o = [f"table {t}", f"\tlineageTag: {guid('t/' + t)}", ""]
    for spec in COLS[t]:
        o += col_block(t, spec)
    o += [f"\tpartition {tq(t)} = m", "\t\tmode: import", "\t\tsource ="]
    o += ["\t\t\t\t" + l for l in M[t].split("\n")]
    o += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(o)


# ============================================================== measures
class Measures:
    def __init__(self):
        self.items = []

    def add(self, name, dax, fmt=None, folder=""):
        self.items.append((name, dax, fmt, folder))

    def tmdl(self):
        o = [f"table {MEAS}", f"\tlineageTag: {guid('t/_Measures')}", ""]
        for name, dax, fmt, folder in self.items:
            lines = dax.strip("\n").split("\n")
            if len(lines) == 1:
                o.append(f"\tmeasure '{name}' = {lines[0]}")
            else:
                o.append(f"\tmeasure '{name}' =")
                o += ["\t\t\t" + l for l in lines]
            if fmt:
                o.append(f"\t\tformatString: {fmt}")
            if folder:
                o.append(f"\t\tdisplayFolder: {folder}")
            o.append(f"\t\tlineageTag: {guid('m/' + name)}")
            o.append("")
        o += ["\tcolumn Value", "\t\tisHidden", "\t\tdataType: int64", "\t\tformatString: 0",
              f"\t\tlineageTag: {guid('c/_Measures.Value')}", "\t\tsummarizeBy: none", "\t\tsourceColumn: Value", "",
              "\t\tannotation SummarizationSetBy = Automatic", "",
              f"\tpartition {MEAS} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              '\t\t\t\t  Source = #table({"Value"}, {{0}}),',
              '\t\t\t\t  #"Changed Type" = Table.TransformColumnTypes(Source, {{"Value", Int64.Type}})',
              "\t\t\t\tin", '\t\t\t\t  #"Changed Type"', "", "\tannotation PBI_ResultType = Table", ""]
        return "\n".join(o)


def txt(expr, fmt="#,##0"):
    # thin-space thousands separator: cards re-format "7,390" with the viewer's locale, this they leave alone
    return f'SUBSTITUTE(FORMAT({expr}, "{fmt}", "en-GB"), ",", UNICHAR(8239))'


def pct(expr, fmt="+0%;-0%;0%"):
    return f'IF(ISBLANK({expr}), "–", FORMAT({expr}, "{fmt}", "en-GB"))'


def build_measures():
    m = Measures()
    FC, DC, FL, DN = "FactCholera", "DimCountry", "FloodLag", "Don"

    def win(lo, hi):
        """cases filter for weeks (anchor - lo, anchor - hi]"""
        return f"REMOVEFILTERS(DimWeek), {FC}[week] > a - {lo}, {FC}[week] <= a - {hi}"

    f = "1 Cholera now"
    m.add("Anchor Week", f"CALCULATE(MAX({FC}[week]), ALL()) - 7", "dd mmm yyyy", f)
    for nm, lo, hi in (("L4W", 28, 0), ("P4W", 56, 28), ("LY4W", 392, 364), ("52W", 364, 0)):
        m.add(f"Cases {nm}", f"VAR a = [Anchor Week]\nRETURN CALCULATE(SUM({FC}[cases]), {win(lo, hi)})", "#,##0", f)
        if nm != "52W":
            m.add(f"Deaths {nm}", f"VAR a = [Anchor Week]\nRETURN CALCULATE(SUM({FC}[deaths]), {win(lo, hi)})", "#,##0", f)
            m.add(f"Countries {nm}", f"VAR a = [Anchor Week]\nRETURN CALCULATE(DISTINCTCOUNT({FC}[iso3]), {win(lo, hi)})", "0", f)
    for nm, base in (("Prev", "P4W"), ("LY", "LY4W")):
        m.add(f"Change vs {nm}", f"VAR c = [Cases L4W]\nVAR b = [Cases {base}]\n"
                                 "RETURN IF(ISBLANK(c) || ISBLANK(b) || b = 0, BLANK(), DIVIDE(c - b, b))", "+0%;-0%;0%", f)
    m.add("CFR L4W", "DIVIDE([Deaths L4W], [Cases L4W])", "0.0%", f)
    m.add("Weekly Cases", f"// the newest week is left out, as in the KPIs: late reports make it look like a crash\nIF(MAX(DimWeek[week]) > [Anchor Week], BLANK(), SUM({FC}[cases]))", "#,##0", f)
    m.add("Window Text",
          'VAR a = [Anchor Week]\nRETURN "WHO weekly cholera & AWD reports  ·  last 4 complete weeks " & FORMAT(a - 21, "d mmm", "en-GB") & " – " & '
          'FORMAT(a + 6, "d mmm yyyy", "en-GB") & "  ·  newest week left out (late reports)"', None, f)
    m.add("L4W Text", txt("[Cases L4W]"), None, f)
    m.add("L4W Sub", pct("[Change vs Prev]") + ' & " vs the 4 weeks before (" & ' + txt("[Cases P4W]") + ' & " cases)"', None, f)
    m.add("LY Text", pct("[Change vs LY]"), None, f)
    m.add("LY Sub", txt("[Cases LY4W]") + ' & " cases in the same weeks of " & YEAR([Anchor Week] - 364)', None, f)
    m.add("LY Sub2", '[Countries LY4W] & " countries reported then, " & [Countries L4W] & " now"', None, f)
    m.add("Deaths Text", txt("[Deaths L4W]"), None, f)
    m.add("Deaths Sub", '"deaths  ·  " & FORMAT([CFR L4W], "0.0%", "en-GB") & " of reported cases died (CFR)"', None, f)
    m.add("Deaths Sub2", '[Countries L4W] & " countries reported in these 4 weeks"', None, f)
    m.add("Top Countries L4W",
          f"VAR N = SELECTEDVALUE({DC}[country])\nVAR V = [Cases L4W]\n"
          "RETURN IF(ISBLANK(N) || ISBLANK(V) || V = 0, BLANK(),\n"
          f"    VAR R = RANKX(FILTER(ALLSELECTED({DC}[country]), [Cases L4W] > 0), [Cases L4W], V, DESC)\n"
          "    RETURN IF(R <= 10, V))", "#,##0", f)
    m.add("Country Bar Color", f'VAR c = [Change vs Prev]\nRETURN IF(ISBLANK(c), "{GHOST}", IF(c > 0.1, "{ALERT}", IF(c < -0.1, "{GREEN}", "{INK3}")))', None, f)

    f = "2 Floods"
    lag = lambda lo, hi: f"{FL}[lag_week] >= {lo}, {FL}[lag_week] <= {hi}"  # noqa: E731
    m.add("Floods Studied", f"DISTINCTCOUNT({FL}[eventid])", "#,##0", f)
    m.add("Flood Countries", f"DISTINCTCOUNT({FL}[iso3])", "0", f)
    m.add("Floods Logged", "COUNTROWS(Flood)", "#,##0", f)
    m.add("Median Ratio", f"MEDIAN({FL}[ratio])", "0.00", f)
    m.add("Ratio After", f"CALCULATE([Median Ratio], {lag(1, 8)})", "0.00", f)
    m.add("Ratio Before", f"CALCULATE([Median Ratio], {lag(-4, -1)})", "0.00", f)
    for nm, lo, hi in (("After", 1, 8), ("Before", -4, -1)):
        m.add(f"Above Share {nm}", f"DIVIDE(CALCULATE(COUNTROWS({FL}), {FL}[ratio] > 1, {lag(lo, hi)}), CALCULATE(COUNT({FL}[ratio]), {lag(lo, hi)}))", "0%", f)
    m.add("Studied Text", txt("[Floods Studied]"), None, f)
    m.add("Studied Sub", '"floods in " & [Flood Countries] & " countries with WHO cholera data"', None, f)
    m.add("Studied Sub2", '"out of " & ' + txt("[Floods Logged]") + ' & " GDACS floods since " & FORMAT(MIN(Flood[from_date]), "mmm yyyy", "en-GB")', None, f)
    m.add("Ratio Text", 'IF(ISBLANK([Ratio After]), "–", FORMAT([Ratio After], "0.00", "en-GB") & "×")', None, f)
    m.add("Ratio Sub", '"of normal: median of weeks +1 to +8 after the flood"', None, f)
    m.add("Ratio Sub2", 'FORMAT([Ratio Before], "0.00", "en-GB") & "× in the 4 weeks before it"', None, f)
    m.add("Above Text", 'FORMAT([Above Share After], "0%", "en-GB")', None, f)
    m.add("Above Sub", '"of weeks +1 to +8 above normal  ·  " & FORMAT([Above Share Before], "0%", "en-GB") & " before the flood"', None, f)
    m.add("Lag Bar Color", f'VAR k = SELECTEDVALUE({FL}[lag_week])\nRETURN IF(k > 0, "{WATER}", IF(k = 0, "{DARK}", "{GHOST}"))', None, f)

    f = "3 Water"
    wash = f"KEEPFILTERS({DC}[band_order] < 4)"  # KEEPFILTERS: must not replace a band filter from a KPI or the axis
    m.add("WASH Countries", f"CALCULATE(COUNTROWS({DC}), {wash})", "0", f)
    m.add("WASH Countries Reporting", f"CALCULATE(COUNTROWS({DC}), {wash}, {DC}[has_cholera] = TRUE())", "0", f)
    m.add("Share Reporting", "DIVIDE([WASH Countries Reporting] + 0, [WASH Countries])", "0%", f)
    m.add("Pop Reporting", f"CALCULATE(SUM({DC}[pop]), {DC}[has_cholera] = TRUE())", "#,##0", f)
    m.add("Per 100k 52W", f"IF(SELECTEDVALUE({DC}[band_order]) = 4, BLANK(), DIVIDE([Cases 52W], [Pop Reporting]) * 100000)", "#,##0.0", f)
    m.add("Top Per 100k",
          f"VAR N = SELECTEDVALUE({DC}[country])\nVAR V = [Per 100k 52W]\n"
          "RETURN IF(ISBLANK(N) || ISBLANK(V) || V = 0, BLANK(),\n"
          f"    VAR R = RANKX(FILTER(ALLSELECTED({DC}[country]), [Per 100k 52W] > 0), [Per 100k 52W], V, DESC)\n"
          "    RETURN IF(R <= 15, V))", "#,##0.0", f)
    m.add("Band Color", f"SWITCH(SELECTEDVALUE({DC}[band_order]), " + ", ".join(f'{k}, "{v}"' for k, v in BAND_COLORS.items()) + f', "{GHOST}")', None, f)
    for nm, b, lab in (("High", 3, "30 % or more"), ("Low", 0, "under 5 %")):
        m.add(f"{nm} Band Text", f'FORMAT(CALCULATE([Share Reporting], {DC}[band_order] = {b}), "0%", "en-GB")', None, f)
        m.add(f"{nm} Band Sub", f'CALCULATE([WASH Countries Reporting] + 0, {DC}[band_order] = {b}) & " of " & CALCULATE([WASH Countries], {DC}[band_order] = {b}) & '
                                f'" countries reported cholera since 2023"', None, f)
        m.add(f"{nm} Band Sub2", f'"countries where {lab} lack basic drinking water"', None, f)
    m.add("Water Period Text",
          'VAR a = [Anchor Week]\nRETURN "Water: WHO/UNICEF JMP, latest year per country  ·  cholera: WHO weekly reports, 52 weeks to " & '
          'FORMAT(a + 6, "d mmm yyyy", "en-GB")', None, f)

    f = "4 DON"
    wb = f'{DN}[kind] = "waterborne"'
    m.add("Waterborne Reports", f"CALCULATE(COUNTROWS({DN}), {wb})", "#,##0", f)
    m.add("DON Reports", f"COUNTROWS({DN})", "#,##0", f)
    m.add("Waterborne Share", "DIVIDE([Waterborne Reports], [DON Reports])", "0.0%", f)
    m.add("Waterborne Countries", f"CALCULATE(DISTINCTCOUNT({DN}[iso3]), {wb})", "0", f)
    m.add("Latest Waterborne", f"CALCULATE(MAX({DN}[published]), {wb})", "dd mmm yyyy", f)
    m.add("WB Text", txt("[Waterborne Reports]"), None, f)
    m.add("WB Sub", 'FORMAT([Waterborne Share], "0.0%", "en-GB") & " of all " & ' + txt("[DON Reports]") + ' & " reports since " & '
          f'MIN({DN}[year]) & "  ·  " & [Waterborne Countries] & " countries"', None, f)
    m.add("Latest Text", 'FORMAT([Latest Waterborne], "d mmm yyyy", "en-GB")', None, f)
    m.add("Latest Sub", f'VAR d = [Latest Waterborne]\nRETURN FORMAT(DATEDIFF(d, TODAY(), DAY), "#,##0", "en-GB") & " days ago (at refresh)  ·  " & '
          f'CALCULATE(MAX({DN}[disease_group]), {wb}, {DN}[published] = d)', None, f)
    m.add("Latest Sub2", f'VAR d = [Latest Waterborne]\nVAR t = CALCULATE(MAX({DN}[title]), {wb}, {DN}[published] = d)\n'
          'RETURN IF(LEN(t) > 52, LEFT(t, 50) & "…", t)', None, f)
    m.add("Cholera DON Share", f'DIVIDE(CALCULATE([Waterborne Reports], {DN}[disease_group] = "Cholera / AWD"), [Waterborne Reports])', "0%", f)
    m.add("Cholera DON Text", 'FORMAT([Cholera DON Share], "0%", "en-GB")', None, f)
    m.add("Cholera DON Sub", '"of waterborne reports are cholera / AWD"', None, f)
    m.add("Cholera DON Sub2", f'"hepatitis A/E " & CALCULATE([Waterborne Reports] + 0, {DN}[disease_group] = "Hepatitis A / E") & '
          f'"  ·  typhoid " & CALCULATE([Waterborne Reports] + 0, {DN}[disease_group] = "Typhoid") & '
          f'"  ·  other " & CALCULATE([Waterborne Reports] + 0, {DN}[disease_group] = "Other waterborne")', None, f)
    m.add("Waterborne per Year", "[Waterborne Reports] + 0", "#,##0", f)
    m.add("Top DON Countries",
          f"VAR N = SELECTEDVALUE({DN}[country])\nVAR V = [Waterborne Reports]\n"
          "RETURN IF(ISBLANK(N) || ISBLANK(V), BLANK(),\n"
          f"    VAR R = RANKX(FILTER(ALLSELECTED({DN}[country]), NOT ISBLANK([Waterborne Reports])), [Waterborne Reports], V, DESC)\n"
          "    RETURN IF(R <= 12, V))", "#,##0", f)
    return m


def write_model():
    tables = MODEL + "tables/"
    os.makedirs(tables, exist_ok=True)
    for fn in os.listdir(tables):
        os.remove(tables + fn)

    def w(path, text):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    for t in ORDER[:-1]:
        w(tables + f"{t}.tmdl", tmdl_table(t))
    m = build_measures()
    w(tables + f"{MEAS}.tmdl", m.tmdl())
    w(MODEL + "relationships.tmdl", "".join(
        f"relationship {guid(f'rel/{a}.{b}')}\n\tfromColumn: {a}.{b}\n\ttoColumn: {c}.{d}\n\n" for a, b, c, d in RELS))
    folder = DATA_DIR.replace('"', '""')
    w(MODEL + "expressions.tmdl",
      f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
      f"\tlineageTag: {guid('e/DataFolder')}\n\n\tannotation PBI_ResultType = Text\n\n")
    qorder = ["DataFolder"] + ORDER
    model = ("model Model\n\tculture: en-GB\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-GB\n"
             "\tvalueFilterBehavior: independent\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
             "annotation __PBI_TimeIntelligenceEnabled = 0\n\n"
             "annotation PBI_QueryOrder = [" + ",".join('"' + t + '"' for t in qorder) + "]\n\n"
             'annotation PBI_ProTooling = ["DevMode"]\n\n'
             + "".join(f"ref table {tq(t)}\n" for t in ORDER) + "\nref cultureInfo en-GB\n\n")
    w(MODEL + "model.tmdl", model)
    os.makedirs(MODEL + "cultures", exist_ok=True)
    w(MODEL + "cultures/en-GB.tmdl", "cultureInfo en-GB\n\n")
    w(MODEL + "database.tmdl", "database\n\tcompatibilityLevel: 1606\n\n")
    pos = {"DimWeek": (0, 0), "FactCholera": (260, 0), "DimCountry": (520, 0), "FloodLag": (780, 0), "Flood": (780, 380),
           "Don": (0, 380), MEAS: (260, 380)}
    nodes = [{"location": {"x": pos[t][0], "y": pos[t][1]}, "nodeIndex": t, "nodeLineageTag": guid("t/" + t),
              "size": {"height": 300, "width": 234}, "zIndex": 0} for t in ORDER]
    dl = {"version": "1.1.0", "diagrams": [{"ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": nodes,
                                            "name": "All tables", "zoomValue": 100, "pinKeyFieldsToTop": False,
                                            "showExtraHeaderInfo": False, "hideKeyFieldsWhenCollapsed": False,
                                            "tablesLocked": False}], "selectedDiagram": "All tables", "defaultDiagram": "All tables"}
    json.dump(dl, open(SM + "diagramLayout.json", "w", encoding="utf-8", newline="\n"), indent=2)
    cache = SM + ".pbi/cache.abf"
    if os.path.exists(cache) and os.environ.get("GEN_KEEP_CACHE") != "1":
        os.remove(cache)
    return len(m.items)


# ============================================================== scaffold (copied from a working PBIP)
def scaffold():
    def w(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)

    w(ROOT + NAME + ".pbip", {"version": "1.0", "artifacts": [{"report": {"path": NAME + ".Report"}}],
                               "settings": {"enableAutoRecovery": True}})
    w(REPORT + "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    plat = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"
    w(REPORT + ".platform", {"$schema": plat, "metadata": {"type": "Report", "displayName": NAME},
                             "config": {"version": "2.0", "logicalId": guid("logical/report")}})
    w(SM + ".platform", {"$schema": plat, "metadata": {"type": "SemanticModel", "displayName": NAME},
                         "config": {"version": "2.0", "logicalId": guid("logical/model")}})
    w(SM + "definition.pbism", {"version": "4.2", "settings": {}})
    for rel in ("definition/version.json", "StaticResources/SharedResources/BaseThemes/Fluent2-CY26SU09.json"):
        os.makedirs(os.path.dirname(REPORT + rel), exist_ok=True)
        shutil.copyfile(TEMPLATE + ".Report/" + rel, REPORT + rel)
    os.makedirs(REPORT + "definition/pages", exist_ok=True)


def write_report_json(images):
    rj = json.load(open(TEMPLATE + ".Report/definition/report.json", encoding="utf-8"))
    rj["resourcePackages"] = [p for p in rj["resourcePackages"] if p["type"] != "RegisteredResources"]
    rj["resourcePackages"].append({"name": "RegisteredResources", "type": "RegisteredResources",
                                   "items": [{"name": n, "path": n, "type": "Image"} for n in images]})
    with open(REPORT + "definition/report.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rj, fh, indent=2, ensure_ascii=False)


# ============================================================== report JSON helpers (as in Sky & Sea)
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def S(s):
    return lit("'" + s.replace("'", "''") + "'")


def B(b):
    return lit("true" if b else "false")


def D(n):
    return lit(f"{n}D")


def clr(h):
    return {"solid": {"color": lit(f"'{h}'")}}


def col(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def mea(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": MEAS}}, "Property": prop}}


def mclr(prop):
    return {"solid": {"color": {"expr": mea(prop)}}}


def cproj(entity, prop, active=True, display=None):
    p = {"field": col(entity, prop), "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    if active:
        p["active"] = True
    return p


def mproj(prop, display=None):
    p = {"field": mea(prop), "queryRef": f"{MEAS}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    return p


def vcobj(title=None, sub=None):
    """Transparent container: the card itself is drawn in the page background."""
    d = {"background": [{"properties": {"show": B(False)}}], "border": [{"properties": {"show": B(False)}}],
         "dropShadow": [{"properties": {"show": B(False)}}]}
    if title:
        d["title"] = [{"properties": {"show": B(True), "text": S(title), "fontColor": clr(INK1), "alignment": S("left"),
                                      "bold": B(False), "fontSize": D(13), "fontFamily": S(FONT_H)}}]
    else:
        d["title"] = [{"properties": {"show": B(False)}}]
    if title and not sub:
        d["subTitle"] = [{"properties": {"show": B(False)}}]
    if sub:
        d["subTitle"] = [{"properties": {"show": B(True), "text": S(sub), "fontColor": clr(INK3), "alignment": S("left"),
                                         "fontSize": D(9), "fontFamily": S(FONT_B)}}]
    d["padding"] = [{"properties": {"top": D(4), "bottom": D(4), "left": D(4), "right": D(4)}}]
    return d


class Page:
    def __init__(self, key, name):
        self.key, self.pid, self.name, self.bg = key, PIDS[key], name, f"bg_{key}.png"
        self.visuals = []
        self.z = 0

    def add(self, key, x, y, w, h, visual, extra=None):
        z = self.z
        self.z += 1000
        d = {"$schema": VC_SCHEMA, "name": hid(f"{self.pid}/{key}"),
             "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": visual}
        if extra:
            d.update(extra)
        self.visuals.append(d)
        return d


def T(v, sz, c=INK1, fam=FONT_B, bold=False):
    return (v, fam, sz, c, bold)


def textbox(page, key, x, y, w, h, paragraphs):
    paras = [{"textRuns": [{"value": v, "textStyle": {**({"fontWeight": "bold"} if bold else {}),
                                                     "fontFamily": fam, "fontSize": f"{sz}pt", "color": c}}
                           for (v, fam, sz, c, bold) in runs]} for runs in paragraphs]
    vc = vcobj()
    vc["padding"] = [{"properties": {"top": D(0), "bottom": D(0), "left": D(0), "right": D(0)}}]
    page.add(key, x, y, w, h, {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                               "visualContainerObjects": vc, "drillFilterOtherVisuals": True})


def textline(page, key, x, y, w, h, measure, size, color=INK1, font=FONT_B, bg=CARD):
    """Left-aligned dynamic text: the new card with all chrome off (Sky & Sea fix for clipped text)."""
    vc = vcobj()
    vc["padding"] = [{"properties": {"top": D(0), "bottom": D(0), "left": D(0), "right": D(0)}}]
    x, w = x - 14, w + 14  # the new card keeps ~14 px inner padding: shift so text lines up with the labels
    dflt = {"id": "default"}
    off = lambda: [{"properties": {"show": B(False)}, "selector": dflt}]  # noqa: E731
    page.add(key, x, y, w, h, {"visualType": "cardVisual",
                               "query": {"queryState": {"Data": {"projections": [mproj(measure)]}}},
                               "objects": {"value": [{"properties": {"fontColor": clr(color), "fontSize": D(size), "fontFamily": S(font),
                                                                     "bold": B(False), "horizontalAlignment": S("left"), "textWrap": B(True)},
                                                      "selector": dflt}],
                                           "label": off(), "accentBar": off(), "outline": off(), "shadowCustom": off(),
                                           "glowCustom": off(), "divider": off(),
                                           "fillCustom": [{"properties": {"show": B(True), "fillColor": clr(bg), "transparency": D(0)}, "selector": dflt}],
                                           "layout": [{"properties": {"alignment": S("left"), "paddingUniform": D(0), "paddingIndividual": B(False),
                                                                      "backgroundShow": B(False)}, "selector": dflt}],
                                           "padding": [{"properties": {"paddingUniform": D(0), "paddingSelection": S("Uniform")}, "selector": dflt}],
                                           "cardCalloutArea": [{"properties": {"paddingUniform": D(0), "paddingIndividual": B(False), "backgroundFillColor": clr(bg)}, "selector": dflt}],
                                           "spacing": [{"properties": {"verticalSpacing": D(0)}, "selector": dflt}]},
                               "visualContainerObjects": vc, "drillFilterOtherVisuals": True})


def axis(size=9, color=INK3):
    return {"labelColor": clr(color), "fontFamily": S(FONT_B), "fontSize": D(size)}


def value_axis(show=True, precision=0):
    return [{"properties": {"show": B(show), "gridlineShow": B(show), "gridlineColor": clr(LINE), "gridlineTransparency": D(0),
                            "showAxisTitle": B(False), "labelDisplayUnits": D(1), "labelPrecision": lit(f"{precision}D"), **axis()}}]


def cat_axis(**extra):
    return [{"properties": {"showAxisTitle": B(False), "gridlineShow": B(False), **axis(), **extra}}]


def legend(show=True):
    if not show:
        return [{"properties": {"show": B(False)}}]
    return [{"properties": {"show": B(True), "position": S("Top"), "labelColor": clr(INK2), "fontFamily": S(FONT_B), "fontSize": D(9)}}]


def data_labels(size=9, precision=None):
    p = {"show": B(True), "color": clr(INK2), "fontFamily": S(FONT_B), "fontSize": D(size), "labelDisplayUnits": D(1)}
    if precision is not None:
        p["labelPrecision"] = lit(f"{precision}D")
    return [{"properties": p}]


def measure_colors(pairs):
    return [{"properties": {"fill": clr(pairs[0][1])}}] + [
        {"properties": {"fill": clr(hx)}, "selector": {"metadata": f"{MEAS}.{p}"}} for p, hx in pairs]


def measure_fill(color_measure):
    return [{"properties": {"fill": mclr(color_measure)}, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]


def chart(page, key, x, y, w, h, vtype, query, objects, title=None, sub=None):
    page.add(key, x, y, w, h, {"visualType": vtype, "query": query, "objects": objects,
                               "visualContainerObjects": vcobj(title, sub), "drillFilterOtherVisuals": True})


def sorted_q(cat_entity, cat_prop, cat_display, measures, sort_field, direction):
    return {"queryState": {"Category": {"projections": [cproj(cat_entity, cat_prop, display=cat_display)]},
                           "Y": {"projections": [mproj(mm, dn) for mm, dn in measures]}},
            "sortDefinition": {"sort": [{"field": sort_field, "direction": direction}], "isDefaultSort": True}}


def pills(page, key, x, y, w, h, entity, prop):
    vis = {"visualType": "slicer",
           "query": {"queryState": {"Values": {"projections": [cproj(entity, prop)]}}},
           "objects": {"data": [{"properties": {"mode": S("Tile")}}],
                       "general": [{"properties": {"orientation": D(1)}}],
                       "header": [{"properties": {"show": B(False)}}],
                       "items": [{"properties": {"fontColor": clr(INK1), "fontFamily": S(FONT_B), "textSize": D(9),
                                                 "background": clr(CARD), "outlineStyle": D(0)}}],
                       "pendingChangesIcon": [{"properties": {"color": clr(INK1)}}]},
           "visualContainerObjects": vcobj(), "drillFilterOtherVisuals": True}
    page.add(key, x, y, w, h, vis)


# ============================================================== layout + backgrounds
PAGES = [("now", "Cholera now"), ("floods", "Floods → cholera"), ("water", "Unsafe water"), ("don", "Outbreak news")]
PIDS = {k: hid("page/" + k) for k, _ in PAGES}
RAIL_Y = [132, 188, 244, 300]
KPI_ROW = [(96, 100, 372, 160), (484, 100, 372, 160), (872, 100, 384, 160)]
CARDS = {
    "now": KPI_ROW + [(96, 276, 760, 420), (872, 276, 384, 420)],
    "floods": KPI_ROW + [(96, 276, 760, 420), (872, 276, 384, 420)],
    "water": KPI_ROW[:2] + [(96, 276, 372, 420), (484, 276, 372, 420), (872, 100, 384, 596)],
    "don": KPI_ROW + [(96, 276, 760, 420), (872, 276, 384, 420)],
}


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def draw_icon(d, kind, cx, cy, color):
    s = SCALE
    P = lambda pts: [(cx + x * s, cy + y * s) for x, y in pts]  # noqa: E731
    if kind in ("now", "brand"):     # water drop
        d.ellipse([cx - 7 * s, cy - 2 * s, cx + 7 * s, cy + 12 * s], fill=color)
        d.polygon(P([(0, -11), (6.2, 2.5), (-6.2, 2.5)]), fill=color)
    elif kind == "floods":           # two waves
        for dy in (-4, 4):
            pts = [(x, dy + 2.6 * (1 if (x // 5) % 2 else -1) * (1 - ((x % 5) / 2.5 - 1) ** 2)) for x in range(-11, 12)]
            d.line(P(pts), fill=color, width=2 * s, joint="curve")
    elif kind == "water":            # tap with a drop
        d.rectangle([cx - 10 * s, cy - 8 * s, cx + 4 * s, cy - 4 * s], fill=color)
        d.rectangle([cx - 4 * s, cy - 12 * s, cx - 1 * s, cy - 8 * s], fill=color)
        d.rectangle([cx + 1 * s, cy - 8 * s, cx + 5 * s, cy + 1 * s], fill=color)
        d.ellipse([cx + 0.5 * s, cy + 5 * s, cx + 5.5 * s, cy + 10 * s], fill=color)
        d.polygon(P([(3, 2), (5.3, 6.6), (0.7, 6.6)]), fill=color)
    elif kind == "don":              # document with lines
        d.rounded_rectangle([cx - 8 * s, cy - 11 * s, cx + 8 * s, cy + 11 * s], radius=2 * s, outline=color, width=2 * s)
        for yy in (-5, 0, 5):
            d.line([(cx - 4 * s, cy + yy * s), (cx + 4 * s, cy + yy * s)], fill=color, width=2 * s)


def make_background(key, path):
    s = SCALE
    img = Image.new("RGBA", (W * s, H * s), hexrgb(CANVAS))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for x, y, w, h in CARDS[key]:
        sd.rounded_rectangle([x * s, (y + 4) * s, (x + w) * s, (y + h + 4) * s], radius=24 * s, fill=(17, 20, 24, 26))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10 * s))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)
    for x, y, w, h in CARDS[key]:
        d.rounded_rectangle([x * s, y * s, (x + w) * s, (y + h) * s], radius=24 * s, fill=hexrgb(CARD), outline=hexrgb(LINE), width=1)
    d.rounded_rectangle([18 * s, 22 * s, 54 * s, 58 * s], radius=10 * s, fill=hexrgb(DARK))
    draw_icon(d, "brand", 36 * s, 40 * s, hexrgb("#FFFFFF"))
    d.line([(24 * s, 100 * s), (48 * s, 100 * s)], fill=hexrgb(LINE), width=s)
    for (k, _), cy in zip(PAGES, RAIL_Y):
        on = k == key
        d.ellipse([16 * s, (cy - 20) * s, 56 * s, (cy + 20) * s], fill=hexrgb(DARK if on else CARD),
                  outline=None if on else hexrgb(LINE), width=s)
        draw_icon(d, k, 36 * s, cy * s, hexrgb("#FFFFFF" if on else INK1))
    img.convert("RGB").save(path, optimize=True)


def page_chrome(P, title, sub_measure=None, sub_text=None):
    textbox(P, "head/title", 96, 22, 520, 46, [[T(title, 24, INK1, FONT_H)]])
    if sub_measure:
        textline(P, "head/sub", 96, 64, 760, 28, sub_measure, 10, INK3, bg=CANVAS)
    elif sub_text:
        textbox(P, "head/sub", 96, 66, 1160, 24, [[T(sub_text, 10, INK3)]])
    for (k, label), cy in zip(PAGES, RAIL_Y):
        if k == P.key:
            continue
        objs = {"icon": [{"properties": {"shapeType": S("blank")}, "selector": {"id": "default"}}],
                "fill": [{"properties": {"show": B(False)}}],
                "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
                "text": [{"properties": {"show": B(False)}}]}
        vco = {"background": [{"properties": {"show": B(False)}}], "border": [{"properties": {"show": B(False)}}],
               "dropShadow": [{"properties": {"show": B(False)}}], "title": [{"properties": {"show": B(False)}}],
               "visualLink": [{"properties": {"show": B(True), "type": S("PageNavigation"), "navigationSection": S(PIDS[k])}}],
               "general": [{"properties": {"altText": S(f"Go to {label}")}}]}
        P.add(f"nav/{k}", 16, cy - 20, 40, 40, {"visualType": "actionButton", "objects": objs, "visualContainerObjects": vco,
                                                "drillFilterOtherVisuals": True}, extra={"howCreated": "InsertVisualButton"})


def label(P, key, x, y, w, text, size=8, color=INK3):
    textbox(P, key, x, y, w, 22, [[T(text, size, color, FONT_B)]])


def kpi_row(P, items):
    """items: 3 x (label, hero measure, sub measure, hero colour[, second sub measure]). The new card does not wrap,
    so each sub line must stay under ~55 characters (9 pt in a ~330 px card)."""
    for i, ((x, y, w, h), it) in enumerate(zip(KPI_ROW, items)):
        lab, hero, sub, color = it[:4]
        if lab is None:
            continue
        label(P, f"k{i}/label", x + 24, y + 18, w - 48, lab)
        textline(P, f"k{i}/hero", x + 20, y + 36, w - 40, 66, hero, 36, color, FONT_L)
        textline(P, f"k{i}/sub", x + 24, y + 104, w - 44, 24, sub, 9, INK2)
        if len(it) > 4:
            textline(P, f"k{i}/sub2", x + 24, y + 126, w - 44, 24, it[4], 9, INK3)


def notes(P, key, x, y, w, h, title, rows, foot=None):
    paras = [[T(title, 13, INK1, FONT_H)], [T(" ", 6, INK3)]]
    for head, body in rows:
        paras.append([T(head + " ", 9, INK1, FONT_H), T(body, 9, INK2)])
    if foot:
        paras += [[T(" ", 6, INK3)], [T(foot, 8, INK3)]]
    textbox(P, key, x, y, w, h, paras)


# ============================================================== pages
def page_now():
    P = Page("now", "Cholera now")
    page_chrome(P, "Cholera now", sub_measure="Window Text")
    pills(P, "region", 520, 26, 736, 36, "FactCholera", "region")
    kpi_row(P, [("REPORTED CASES · LAST 4 WEEKS", "L4W Text", "L4W Sub", INK1),
                ("VS THE SAME 4 WEEKS LAST YEAR", "LY Text", "LY Sub", INK1, "LY Sub2"),
                ("DEATHS · LAST 4 WEEKS", "Deaths Text", "Deaths Sub", INK1, "Deaths Sub2")])
    q = {"queryState": {"Category": {"projections": [cproj("DimWeek", "week", display="Week (Monday)")]},
                        "Y": {"projections": [mproj("Weekly Cases", "Reported cases")]}},
         "sortDefinition": {"sort": [{"field": col("DimWeek", "week"), "direction": "Ascending"}], "isDefaultSort": True}}
    objs = {"lineStyles": [{"properties": {"strokeWidth": D(2), "showMarker": B(False), "lineChartType": S("linear")}}],
            "valueAxis": value_axis(), "categoryAxis": cat_axis(), "legend": legend(False),  # no axisType: dates go continuous
            "dataPoint": measure_colors([("Weekly Cases", WATER)])}
    chart(P, "weekly", 112, 292, 728, 392, "lineChart", q, objs, "Reported cholera cases per week",
          "All countries in the WHO weekly feed since Jan 2023 · a missing report counts as nothing, not as zero")
    q = sorted_q("DimCountry", "country", "Country", [("Top Countries L4W", "Cases")], mea("Top Countries L4W"), "Descending")
    objs = {"valueAxis": value_axis(False), "categoryAxis": cat_axis(fontSize=D(9)), "legend": legend(False),
            "labels": data_labels(), "dataPoint": measure_fill("Country Bar Color")}
    chart(P, "top", 888, 292, 352, 392, "clusteredBarChart", q, objs, "Most cases, last 4 weeks",
          "Cases · orange = up, green = down > 10 % vs 4 weeks before")
    return P


def page_floods():
    P = Page("floods", "Floods → cholera")
    page_chrome(P, "Floods → cholera", sub_text="Does a country report more cholera in the weeks after a GDACS flood? Each flood vs the country's own normal (weeks −12 to −5)")
    pills(P, "alert", 896, 26, 360, 36, "FloodLag", "alert")
    kpi_row(P, [("FLOODS STUDIED", "Studied Text", "Studied Sub", INK1, "Studied Sub2"),
                ("CHOLERA CASES AFTER A FLOOD", "Ratio Text", "Ratio Sub", WATER, "Ratio Sub2"),
                ("WEEKS ABOVE NORMAL AFTER A FLOOD", "Above Text", "Above Sub", INK1)])
    q = sorted_q("FloodLag", "lag_label", "Weeks from flood start", [("Median Ratio", "Cases ÷ normal (median)")],
                 col("FloodLag", "lag_week"), "Ascending")
    objs = {"valueAxis": value_axis(True, 1), "categoryAxis": cat_axis(axisType=S("Categorical"), fontSize=D(10)), "legend": legend(False),
            "labels": data_labels(9, 2), "dataPoint": measure_fill("Lag Bar Color")}
    chart(P, "lag", 112, 292, 728, 392, "clusteredColumnChart", q, objs, "Weekly cases ÷ the country's normal, by week from the flood",
          "Median over all floods · 1.00 = normal · grey = before, black = flood week, blue = after")
    notes(P, "notes", 892, 300, 344, 380, "How to read this", [
        ("Result.", "No rise: the median stays below 1.00 before and after floods, and orange/red floods look the same."),
        ("Why it can hide a link.", "WHO counts are national and weekly; a local outbreak downstream of one flood is small next to the national total."),
        ("Floods.", "GDACS flood alerts (GloFAS-based), mostly green = small. Multi-country floods are left out."),
        ("Kept.", "A flood counts when its country has 4 + reported weeks with cases in weeks −12 to −5, and weeks −4 to +8 lie inside the data."),
    ], "Correlation, not cause. Uneven WHO reporting: a missing week is no report, not zero.")
    return P


def page_water():
    P = Page("water", "Unsafe water")
    page_chrome(P, "Unsafe water", sub_measure="Water Period Text")
    kpi_row(P, [("REPORTED CHOLERA · WORST WATER ACCESS", "High Band Text", "High Band Sub", ALERT, "High Band Sub2"),
                ("REPORTED CHOLERA · BEST WATER ACCESS", "Low Band Text", "Low Band Sub", INK1, "Low Band Sub2"), (None, None, None, None)])
    q = sorted_q("DimCountry", "unsafe_band", "Without basic drinking water", [("Share Reporting", "Countries reporting cholera")],
                 col("DimCountry", "band_order"), "Ascending")
    objs = {"valueAxis": value_axis(False), "categoryAxis": cat_axis(axisType=S("Categorical"), fontSize=D(9)), "legend": legend(False),
            "labels": data_labels(9), "dataPoint": measure_fill("Band Color")}
    chart(P, "share", 112, 292, 340, 392, "clusteredColumnChart", q, objs, "Share of countries with cholera",
          "Any report since Jan 2023 · axis = people without basic water")
    q = sorted_q("DimCountry", "unsafe_band", "Without basic drinking water", [("Per 100k 52W", "Cases per 100,000 people")],
                 col("DimCountry", "band_order"), "Ascending")
    objs = {"valueAxis": value_axis(False), "categoryAxis": cat_axis(axisType=S("Categorical"), fontSize=D(9)), "legend": legend(False),
            "labels": data_labels(9, 1), "dataPoint": measure_fill("Band Color")}
    chart(P, "rate", 500, 292, 340, 392, "clusteredColumnChart", q, objs, "Cases per 100,000 people",
          "Last 52 weeks · countries in the WHO feed only")
    q = sorted_q("DimCountry", "country", "Country", [("Top Per 100k", "Cases per 100,000")], mea("Top Per 100k"), "Descending")
    objs = {"valueAxis": value_axis(False), "categoryAxis": cat_axis(fontSize=D(9)), "legend": legend(False),
            "labels": data_labels(9, 1), "dataPoint": measure_fill("Band Color")}
    chart(P, "top", 888, 116, 352, 568, "clusteredBarChart", q, objs, "Highest rates, last 52 weeks",
          "Cases per 100,000 · orange = 30 % + lack basic water")
    return P


def page_don():
    P = Page("don", "Outbreak news")
    page_chrome(P, "Outbreak news", sub_text="WHO Disease Outbreak News since 1996: one report per event of international concern, not a case count")
    kpi_row(P, [("WATERBORNE REPORTS", "WB Text", "WB Sub", INK1),
                ("LATEST WATERBORNE REPORT", "Latest Text", "Latest Sub", INK1, "Latest Sub2"),
                ("CHOLERA'S SHARE", "Cholera DON Text", "Cholera DON Sub", WATER, "Cholera DON Sub2")])
    q = sorted_q("Don", "year", "Year", [("Waterborne per Year", "Waterborne reports")], col("Don", "year"), "Ascending")
    objs = {"valueAxis": value_axis(), "categoryAxis": cat_axis(axisType=S("Categorical"), fontSize=D(8)), "legend": legend(False),
            "dataPoint": measure_colors([("Waterborne per Year", WATER)])}
    chart(P, "years", 112, 292, 728, 392, "clusteredColumnChart", q, objs, "Waterborne outbreak reports per year",
          "Cholera, AWD, hepatitis A/E, typhoid, shigella, E. coli, leptospirosis … · since 2023 WHO tracks cholera in a weekly feed instead (page 1)")
    q = sorted_q("Don", "country", "Country", [("Top DON Countries", "Reports")], mea("Top DON Countries"), "Descending")
    objs = {"valueAxis": value_axis(False), "categoryAxis": cat_axis(fontSize=D(9)), "legend": legend(False),
            "labels": data_labels(), "dataPoint": measure_colors([("Top DON Countries", WATER)])}
    chart(P, "countries", 888, 292, 352, 392, "clusteredBarChart", q, objs, "Most waterborne reports",
          "Reports per country (as WHO names it) since 1996")
    return P


def write_report():
    pages = [page_now(), page_floods(), page_water(), page_don()]
    res = REPORT + "StaticResources/RegisteredResources/"
    os.makedirs(res, exist_ok=True)
    for fn in os.listdir(res):
        os.remove(res + fn)
    for P in pages:
        make_background(P.key, res + P.bg)
    write_report_json([P.bg for P in pages])
    pdir = REPORT + "definition/pages/"
    for d in os.listdir(pdir):
        if os.path.isdir(pdir + d):
            shutil.rmtree(pdir + d)
    for P in pages:
        os.makedirs(pdir + P.pid + "/visuals", exist_ok=True)
        item = {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": P.bg}}}
        page_json = {"$schema": PAGE_SCHEMA, "name": P.pid, "displayName": P.name, "displayOption": "FitToPage",
                     "height": H, "width": W,
                     "objects": {"background": [{"properties": {"image": {"image": {"name": S(P.bg), "url": item, "scaling": S("Fill")}},
                                                                "transparency": D(0)}}],
                                 "outspace": [{"properties": {"color": clr(WALL), "transparency": D(0)}}]}}
        json.dump(page_json, open(pdir + P.pid + "/page.json", "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
        for v in P.visuals:
            vd = pdir + P.pid + "/visuals/" + v["name"]
            os.makedirs(vd, exist_ok=True)
            json.dump(v, open(vd + "/visual.json", "w", encoding="utf-8", newline="\n"), indent=2, ensure_ascii=False)
    pj = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
          "pageOrder": [P.pid for P in pages], "activePageName": PIDS["now"]}
    json.dump(pj, open(pdir + "pages.json", "w", encoding="utf-8", newline="\n"), indent=2)
    return pages


if __name__ == "__main__":
    if not os.path.exists(ROOT + NAME + ".pbip"):
        scaffold()
    n = write_model()
    pages = write_report()
    print("measures:", n, "| visuals:", {p.key: len(p.visuals) for p in pages})
