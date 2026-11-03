"""Data import and validation for data templates.

* parse_csv: CSV or TSV or pasted spreadsheet cells -> {columns, rows}
  (strings), at most MAX_ROWS x MAX_COLS.
* parse_number: "1,234.5", "$1.2M", "45%", "(12)", "-3.4", "1.2k" -> float,
  plus the unit it carried (prefix, suffix, scale).
* Shape detection: wide (one label or period column plus numeric columns,
  either orientation) or long (period, entity, value triples), decided from
  the data itself.
* Per-template views: race (periods x entities), series (x labels plus 1 to 3
  numeric series), categories (labels plus one value), tickers (name, value,
  change, optional spark), versus (metric, A, B, higher_is_better).

Every view returns problems (blocking) and warnings. Bars start at zero by
construction (the charts never take a non-zero baseline), and a negative
value in a bar race is reported because a race needs non-negative values.
"""

from __future__ import annotations

import csv
import io
import math
import re
from typing import Any, Optional

MAX_ROWS = 400
MAX_COLS = 40
MAX_CELL = 120
MAX_ABS = 1e15  # same bound as spec.MAX_ABS_NUMBER

_NUM = re.compile(r"^([^\d\-+.(]*)\(?([-+]?\d[\d,\s]*\.?\d*|[-+]?\.\d+)\)?\s*([a-zA-Z%€£¥$]*)\s*$")
_SCALE = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "mn": 1e6, "b": 1e9, "B": 1e9, "bn": 1e9, "t": 1e12, "T": 1e12}
_YEARISH = re.compile(r"^(1[5-9]\d\d|2[01]\d\d)([-/ ](0?[1-9]|1[0-2]|Q[1-4]|[A-Za-z]{3,9}))?$|^Q[1-4][ -]?\d{2,4}$|"
                      r"^\d{4}-\d{2}(-\d{2})?$|^\d{1,2}/\d{1,2}/\d{2,4}$|^[A-Za-z]{3,9}[ -]\d{2,4}$")


def parse_csv(text: str) -> dict:
    """{columns, rows} from CSV, TSV or semicolon separated text."""
    text = (text or "").strip("﻿\n\r ")
    if not text:
        return {"columns": [], "rows": []}
    sample = text[:4000]
    delim = "\t" if sample.count("\t") >= max(1, sample.count(",") // 2) else (
        ";" if sample.count(";") > sample.count(",") else ",")
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = []
    for r in reader:
        if not any((c or "").strip() for c in r):
            continue
        rows.append([(c or "").strip()[:MAX_CELL] for c in r[:MAX_COLS]])
        if len(rows) > MAX_ROWS + 1:
            break
    if not rows:
        return {"columns": [], "rows": []}
    header = rows[0]
    if all(parse_number(h)[0] is not None for h in header[1:]) and len(rows) > 1 and not any(
            _YEARISH.match(h or "") for h in header[1:]):
        # no header row: invent names
        header = [f"Column {i + 1}" for i in range(len(rows[0]))]
        body = rows
    else:
        body = rows[1:]
    width = max(len(header), max((len(r) for r in body), default=0))
    header = (header + [f"Column {i + 1}" for i in range(len(header), width)])[:width]
    body = [(r + [""] * width)[:width] for r in body[:MAX_ROWS]]
    return {"columns": [h or f"Column {i + 1}" for i, h in enumerate(header)], "rows": body}


def parse_number(s: Any) -> tuple[Optional[float], dict]:
    """(value, unit) where unit = {prefix, suffix}. None for non-numbers."""
    if s is None:
        return None, {}
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        try:
            f = float(s)
        except OverflowError:
            return None, {}
        return (f if math.isfinite(f) and abs(f) <= MAX_ABS else None), {}
    t = str(s)[:MAX_CELL].strip().replace("−", "-").replace(" ", " ")
    if not t or t in ("-", "--", "n/a", "NA", "N/A", "null", "None"):
        return None, {}
    neg = t.startswith("(") and t.endswith(")")
    m = _NUM.match(t.replace("(", "").replace(")", "") if neg else t)
    if not m:
        return None, {}
    prefix, num, suffix = m.group(1).strip(), m.group(2).replace(",", "").replace(" ", ""), m.group(3)
    if prefix and not re.fullmatch(r"[$€£¥₹]|Rs\.?|USD|EUR|INR|-|\+", prefix):
        return None, {}
    try:
        v = float(num)
    except ValueError:
        return None, {}
    if prefix in ("-",):
        v, prefix = -v, ""
    scale = 1.0
    if suffix in _SCALE:
        scale = _SCALE[suffix]
    elif suffix and suffix not in ("%",) and not re.fullmatch(r"[a-zA-Z]{1,4}", suffix):
        return None, {}
    v = -v * scale if neg else v * scale
    if not math.isfinite(v) or abs(v) > MAX_ABS:
        return None, {}  # "999...9" (inf), "1e308"-scale values: not a usable number
    return v, {"prefix": prefix, "suffix": suffix if suffix == "%" else ""}


def _numeric_ratio(values: list[str]) -> float:
    vals = [v for v in values if (v or "").strip()]
    if not vals:
        return 0.0
    return sum(1 for v in vals if parse_number(v)[0] is not None) / len(vals)


def _units(cells: list[str]) -> dict:
    prefixes, suffixes = {}, {}
    for c in cells:
        v, u = parse_number(c)
        if v is None:
            continue
        if u.get("prefix"):
            prefixes[u["prefix"]] = prefixes.get(u["prefix"], 0) + 1
        if u.get("suffix"):
            suffixes[u["suffix"]] = suffixes.get(u["suffix"], 0) + 1
    return {"prefix": max(prefixes, key=prefixes.get) if prefixes else "",
            "suffix": max(suffixes, key=suffixes.get) if suffixes else ""}


def _decimals(values: list[float]) -> int:
    best = 0
    for v in values[:200]:
        s = f"{abs(v):.6f}".rstrip("0").rstrip(".")
        if "." in s:
            best = max(best, min(2, len(s.split(".")[1])))
    return best


def detect_shape(table: dict) -> dict:
    """{format: wide|long|unknown, label_col, numeric_cols, period_col,
    entity_col, value_col, transposed}."""
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not cols or not rows:
        return {"format": "unknown"}
    by_col = [[r[i] for r in rows] for i in range(len(cols))]
    ratios = [_numeric_ratio(c) for c in by_col]
    yearish = [i for i, c in enumerate(by_col)
               if sum(1 for v in c if _YEARISH.match((v or "").strip())) >= 0.8 * len(rows)]
    numeric = [i for i, r in enumerate(ratios) if r >= 0.8 and i not in yearish]
    text_cols = [i for i in range(len(cols)) if i not in numeric]
    # Long: exactly one numeric value column plus two label columns with repeats.
    if len(numeric) == 1 and len(text_cols) >= 2 and len(rows) >= 4:
        a, b = text_cols[0], text_cols[1]
        ua, ub = len(set(by_col[a])), len(set(by_col[b]))
        if ua < len(rows) and ub < len(rows):
            yearish_a = sum(1 for v in by_col[a] if _YEARISH.match(v or "")) / len(rows)
            yearish_b = sum(1 for v in by_col[b] if _YEARISH.match(v or "")) / len(rows)
            period, entity = (a, b) if yearish_a >= yearish_b else (b, a)
            return {"format": "long", "period_col": period, "entity_col": entity, "value_col": numeric[0]}
    if numeric:
        label = text_cols[0] if text_cols else None
        transposed = sum(1 for c in (cols[i] for i in numeric) if _YEARISH.match(c or "")) >= 0.6 * len(numeric)
        return {"format": "wide", "label_col": label, "numeric_cols": numeric, "transposed": transposed}
    return {"format": "unknown"}


def _cell_values(cells: list[str]) -> list[Optional[float]]:
    return [parse_number(c)[0] for c in cells]


def _period_sort_key(label: str):
    v, _ = parse_number(label)
    if v is not None:
        return (0, v, label)
    return (1, 0, label)


# ---------------------------------------------------------------------------
# Views per template
# ---------------------------------------------------------------------------

def race_view(table: dict, *, top_n: int = 10) -> dict:
    """Periods x entities for a bar chart race."""
    problems, warnings = [], []
    shape = detect_shape(table)
    cols, rows = table.get("columns") or [], table.get("rows") or []
    periods: list[str] = []
    entities: list[str] = []
    matrix: dict[str, list[Optional[float]]] = {}
    unit_cells: list[str] = []
    if shape["format"] == "long":
        pc, ec, vc = shape["period_col"], shape["entity_col"], shape["value_col"]
        periods = sorted({r[pc] for r in rows if r[pc]}, key=_period_sort_key)
        entities = sorted({r[ec] for r in rows if r[ec]})
        pidx = {p: i for i, p in enumerate(periods)}
        matrix = {e: [None] * len(periods) for e in entities}
        for r in rows:
            if r[pc] in pidx and r[ec] in matrix:
                matrix[r[ec]][pidx[r[pc]]] = parse_number(r[vc])[0]
                unit_cells.append(r[vc])
    elif shape["format"] == "wide":
        num = shape["numeric_cols"]
        label = shape.get("label_col")
        if shape.get("transposed"):
            # rows are entities, numeric columns are periods
            periods = [cols[i] for i in num]
            for r in rows:
                name = r[label] if label is not None else f"Row {len(entities) + 1}"
                if not name:
                    continue
                entities.append(name)
                matrix[name] = _cell_values([r[i] for i in num])
                unit_cells += [r[i] for i in num]
        else:
            # rows are periods, numeric columns are entities
            periods = [r[label] if label is not None else str(k + 1) for k, r in enumerate(rows)]
            for i in num:
                entities.append(cols[i])
                matrix[cols[i]] = _cell_values([r[i] for r in rows])
                unit_cells += [r[i] for r in rows]
    else:
        problems.append("Could not read the data: give one label column plus numeric columns (wide), "
                        "or period, name and value columns (long).")
        return {"ok": False, "problems": problems, "warnings": warnings, "format": "unknown"}
    if len(periods) < 2:
        problems.append("A bar chart race needs at least 2 periods.")
    if len(entities) < 2:
        problems.append("A bar chart race needs at least 2 names.")
    if len(entities) > 60:
        warnings.append(f"{len(entities)} names: only the top {top_n} are shown at any moment.")
    missing = 0
    for e, vals in matrix.items():
        last = None
        for k, v in enumerate(vals):
            if v is None:
                missing += 1
                vals[k] = last if last is not None else 0.0
            else:
                last = v
            if vals[k] < 0:
                problems.append(f"'{e}' has a negative value; bar races need values of zero or more.")
                break
    if missing:
        warnings.append(f"{missing} empty cells were filled with the previous period's value (or zero).")
    flat = [v for vals in matrix.values() for v in vals if v is not None]
    if flat and max(flat) <= 0:
        problems.append("Every value is zero.")
    units = _units(unit_cells)
    if len(periods) > 120:
        warnings.append("More than 120 periods: consider yearly data for a readable race.")
    return {
        "ok": not problems, "problems": problems, "warnings": warnings, "format": shape["format"],
        "periods": periods, "entities": entities, "values": matrix, "units": units,
        "decimals": _decimals(flat), "max": max(flat) if flat else 0.0,
    }


def series_view(table: dict) -> dict:
    """X labels and up to 3 numeric series (line, bar or donut charts)."""
    problems, warnings = [], []
    shape = detect_shape(table)
    cols, rows = table.get("columns") or [], table.get("rows") or []
    if shape["format"] == "long":
        rv = race_view(table)
        if not rv["ok"]:
            return {**rv, "ok": False}
        labels = rv["periods"]
        series = [{"name": e, "values": rv["values"][e]} for e in rv["entities"]]
        units = rv["units"]
    elif shape["format"] == "wide":
        label = shape.get("label_col")
        num = shape["numeric_cols"]
        if shape.get("transposed") and len(rows) <= 3:
            labels = [cols[i] for i in num]
            series = [{"name": (r[label] if label is not None else f"Series {k + 1}"),
                       "values": _cell_values([r[i] for i in num])} for k, r in enumerate(rows)]
        else:
            labels = [r[label] if label is not None else str(k + 1) for k, r in enumerate(rows)]
            series = [{"name": cols[i], "values": _cell_values([r[i] for r in rows])} for i in num]
        units = _units([c for r in rows for c in r])
    else:
        return {"ok": False, "problems": ["Could not read the data: give a label column plus 1 to 3 numeric columns."],
                "warnings": [], "format": "unknown"}
    if len(series) > 3:
        warnings.append(f"{len(series)} numeric columns: the first 3 are charted (at most 3 series).")
        series = series[:3]
    if len(labels) < 2:
        problems.append("A chart needs at least 2 rows.")
    if len(labels) > 60:
        warnings.append("More than 60 points: labels are thinned on screen.")
    flat = [v for s in series for v in s["values"] if v is not None]
    if not flat:
        problems.append("No numeric values found.")
    total = sum(v for v in (series[0]["values"] if series else []) if v is not None)
    suggest = "line"
    if series and len(series) == 1 and len(labels) <= 6 and abs(total - 100) <= 1.5 and min(flat or [0]) >= 0:
        suggest = "donut"
    elif len(labels) <= 10 and not any(_YEARISH.match(str(lb) or "") for lb in labels):
        suggest = "bar"
    return {"ok": not problems, "problems": problems, "warnings": warnings, "format": shape["format"],
            "labels": [str(lb) for lb in labels], "series": series, "units": units,
            "decimals": _decimals(flat), "suggested_chart": suggest,
            "has_negative": any(v < 0 for v in flat)}


_NAME_HINTS = ("name", "ticker", "symbol", "index", "asset", "stock", "market")
_VALUE_HINTS = ("value", "price", "close", "last", "level")
_CHANGE_HINTS = ("change", "chg", "%", "pct", "percent", "return", "move")


def tickers_view(table: dict) -> dict:
    """Market recap rows: name, value, change percent, optional spark values."""
    problems, warnings = [], []
    cols, rows = table.get("columns") or [], table.get("rows") or []
    if not cols or not rows:
        return {"ok": False, "problems": ["Add a table with name, value and change columns."], "warnings": []}
    low = [c.lower() for c in cols]

    def find(hints, exclude=()):
        for i, c in enumerate(low):
            if i not in exclude and any(h in c for h in hints):
                return i
        return None

    ni = find(_NAME_HINTS)
    ci = find(_CHANGE_HINTS, exclude=(ni,) if ni is not None else ())
    vi = find(_VALUE_HINTS, exclude=tuple(x for x in (ni, ci) if x is not None))
    if ni is None:
        ni = 0
    numeric = [i for i in range(len(cols)) if i != ni and _numeric_ratio([r[i] for r in rows]) >= 0.8]
    if vi is None:
        vi = next((i for i in numeric if i != ci), None)
    if ci is None:
        ci = next((i for i in numeric if i != vi), None)
    if vi is None:
        problems.append("No value column found (name it value, price or close).")
        return {"ok": False, "problems": problems, "warnings": warnings}
    spark_cols = [i for i in numeric if i not in (vi, ci)]
    items = []
    for r in rows[:12]:
        name = r[ni]
        if not name:
            continue
        value = parse_number(r[vi])[0]
        change = parse_number(r[ci])[0] if ci is not None else None
        if value is None:
            warnings.append(f"'{name}' has no value; skipped.")
            continue
        spark = [v for v in (parse_number(r[i])[0] for i in spark_cols) if v is not None]
        items.append({"name": name, "value": value, "change": change, "spark": spark if len(spark) >= 2 else None})
    if len(rows) > 12:
        warnings.append("Only the first 12 rows are used.")
    if len(items) < 2:
        problems.append("A market recap needs at least 2 rows with values.")
    if ci is None:
        warnings.append("No change column found: tiles show values only.")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "items": items,
            "units": _units([r[vi] for r in rows]), "decimals": max(2, _decimals([i["value"] for i in items]))}


def versus_view(table: dict) -> dict:
    """Comparison rows: metric, A, B, higher_is_better (true by default)."""
    problems, warnings = [], []
    cols, rows = table.get("columns") or [], table.get("rows") or []
    if len(cols) < 3 or not rows:
        return {"ok": False, "problems": ["Add a table with metric, A and B columns."], "warnings": []}
    numeric = [i for i in range(1, len(cols)) if _numeric_ratio([r[i] for r in rows]) >= 0.8]
    if len(numeric) < 2:
        return {"ok": False, "problems": ["The A and B columns must be numbers."], "warnings": []}
    a, b = numeric[0], numeric[1]
    hib = next((i for i, c in enumerate(cols) if "better" in c.lower() or "higher" in c.lower()), None)
    out = []
    for r in rows[:6]:
        av, bv = parse_number(r[a])[0], parse_number(r[b])[0]
        if av is None or bv is None:
            continue
        h = True
        if hib is not None:
            h = (r[hib] or "").strip().lower() not in ("false", "no", "0", "lower", "n")
        out.append({"label": r[0], "a": av, "b": bv, "higher_is_better": h,
                    "unit": _units([r[a], r[b]])})
    if len(rows) > 6:
        warnings.append("Only the first 6 metrics are used (rounds of 3 to 4 seconds).")
    if len(out) < 1:
        problems.append("No complete metric rows.")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "a_name": cols[a], "b_name": cols[b],
            "metrics": out}


def validate_table(kind: str, table: Optional[dict], **kw) -> dict:
    if not table or not table.get("rows"):
        return {"ok": False, "problems": ["No data yet. Paste CSV or upload a file."], "warnings": []}
    fn = {"race": race_view, "series": series_view, "tickers": tickers_view, "versus": versus_view}.get(kind)
    if fn is None:
        return {"ok": True, "problems": [], "warnings": []}
    return fn(table, **kw) if kind == "race" else fn(table)
