from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_contract() -> dict[str, Any]:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    dashboard = payload.get("dashboard") if isinstance(payload, dict) else None
    if not isinstance(dashboard, dict):
        raise ValueError("config/dashboard.yaml thiếu object dashboard")
    return dashboard


def load_records(start: datetime, end: datetime) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        timestamp = parse_timestamp(record.get("ts"))
        if timestamp is not None and start <= timestamp <= end:
            record["_timestamp"] = timestamp
            records.append(record)
    return records


def numeric_values(records: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for record in records:
        value = record.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def percentile(values: list[float], percentage: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def minute_buckets(records: list[dict[str, Any]], field: str | None = None) -> dict[str, float]:
    buckets: defaultdict[str, float] = defaultdict(float)
    for record in records:
        timestamp = record.get("_timestamp")
        if not isinstance(timestamp, datetime):
            continue
        key = timestamp.strftime("%H:%M")
        if field is None:
            buckets[key] += 1
        else:
            value = record.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                buckets[key] += float(value)
    return dict(sorted(buckets.items()))


def build_metrics() -> dict[str, Any]:
    dashboard = load_contract()
    window_minutes = int(dashboard["time_range_minutes"])
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=window_minutes)
    records = load_records(start, end)

    received = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failed = [record for record in records if record.get("event") == "request_failed"]

    latency_values = numeric_values(responses, "latency_ms")
    ttft_values = numeric_values(responses, "ttft_ms")
    error_breakdown = Counter(
        str(record.get("error_type"))
        for record in failed
        if record.get("error_type") is not None
    )
    retrieval_records = [
        record for record in responses if isinstance(record.get("tool_success"), bool)
    ]
    retrieval_successes = sum(1 for record in retrieval_records if record["tool_success"])
    observed_minutes = max(1.0, (end - start).total_seconds() / 60)
    traffic_by_minute = minute_buckets(received)

    return {
        "window": {
            "start": start.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "minutes": window_minutes,
        },
        "record_count": len(records),
        "panels": {
            "latency": {
                "response_count": len(responses),
                "p50": percentile(latency_values, 50),
                "p95": percentile(latency_values, 95),
                "p99": percentile(latency_values, 99),
                "ttft_p95": percentile(ttft_values, 95),
            },
            "traffic": {
                "request_count": len(received),
                "rate_per_minute": len(received) / observed_minutes,
                "peak_per_minute": max(traffic_by_minute.values(), default=0),
                "by_minute": traffic_by_minute,
            },
            "errors": {
                "request_count": len(received),
                "failed_count": len(failed),
                "error_rate_pct": (len(failed) / len(received) * 100) if received else 0.0,
                "retrieval_success_pct": (
                    retrieval_successes / len(retrieval_records) * 100
                    if retrieval_records
                    else 0.0
                ),
                "retrieval_samples": len(retrieval_records),
                "breakdown": dict(error_breakdown),
            },
            "cost": {
                "total_usd": sum(numeric_values(responses, "cost_usd")),
                "by_minute": minute_buckets(responses, "cost_usd"),
            },
            "tokens": {
                "input_total": sum(numeric_values(responses, "tokens_in")),
                "output_total": sum(numeric_values(responses, "tokens_out")),
            },
            "quality": {
                "samples": len(numeric_values(responses, "quality_score")),
                "mean": mean(numeric_values(responses, "quality_score"))
                if numeric_values(responses, "quality_score")
                else 0.0,
            },
        },
    }


def fmt(value: float | int, digits: int = 2) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.{digits}f}"


def threshold_text(panel: dict[str, Any]) -> str:
    threshold = panel["threshold"]
    operator = {"lte": "≤", "gte": "≥"}.get(threshold["operator"], threshold["operator"])
    return f"{threshold['aggregation']} {operator} {threshold['value']} {panel['unit']}"


def card(label: str, value: str, unit: str = "") -> str:
    return (
        '<div class="metric-card">'
        f'<div class="metric-label">{escape(label)}</div>'
        f'<div class="metric-value">{escape(value)}<span>{escape(unit)}</span></div>'
        "</div>"
    )


def series_bars(series: dict[str, float], unit: str) -> str:
    if not series:
        return '<div class="empty">No data in the selected window.</div>'
    items = list(series.items())[-12:]
    maximum = max(max(value for _, value in items), 1.0)
    bars = []
    for label, value in items:
        height = max(4, round(value / maximum * 100))
        bars.append(
            '<div class="bar-wrap">'
            f'<div class="bar" style="height:{height}%" title="{escape(label)}: {fmt(value)} {escape(unit)}"></div>'
            f'<div class="bar-label">{escape(label)}</div>'
            "</div>"
        )
    return '<div class="bars">' + "".join(bars) + "</div>"


def panel_shell(panel: dict[str, Any], body: str) -> str:
    panel_id = escape(str(panel["id"]))
    title = escape(str(panel["title"]))
    unit = escape(str(panel["unit"]))
    threshold = escape(threshold_text(panel))
    return (
        f'<section class="panel" id="panel-{panel_id}">'
        f'<div class="panel-heading"><h2>{title}</h2><span class="panel-id">{panel_id}</span></div>'
        f'<div class="panel-meta">Unit: {unit} · Threshold: {threshold}</div>'
        f"{body}</section>"
    )


def render_dashboard() -> str:
    contract = load_contract()
    metrics = build_metrics()
    data = metrics["panels"]
    panels = {str(panel["id"]): panel for panel in contract["panels"]}

    latency = data["latency"]
    latency_body = (
        '<div class="cards">'
        + card("P50", fmt(latency["p50"]), "ms")
        + card("P95", fmt(latency["p95"]), "ms")
        + card("P99", fmt(latency["p99"]), "ms")
        + card("TTFT P95", fmt(latency["ttft_p95"]), "ms")
        + "</div>"
        + f'<p class="note">Based on {latency["response_count"]} response_sent records.</p>'
    )

    traffic = data["traffic"]
    traffic_body = (
        '<div class="cards">'
        + card("Requests", fmt(traffic["request_count"], 0))
        + card("Average rate", fmt(traffic["rate_per_minute"]), "req/min")
        + card("Peak minute", fmt(traffic["peak_per_minute"], 0), "req")
        + "</div>"
        + series_bars(traffic["by_minute"], "requests")
    )

    errors = data["errors"]
    breakdown = ", ".join(
        f"{escape(name)}: {escape(fmt(count, 0))}" for name, count in errors["breakdown"].items()
    ) or "none"
    errors_body = (
        '<div class="cards">'
        + card("Error rate", fmt(errors["error_rate_pct"]), "%")
        + card("Failed", fmt(errors["failed_count"], 0))
        + card("Retrieval success", fmt(errors["retrieval_success_pct"]), "%")
        + "</div>"
        + f'<p class="note">Retrieval samples: {errors["retrieval_samples"]} · Error breakdown: {breakdown}</p>'
    )

    cost = data["cost"]
    cost_body = (
        '<div class="cards">'
        + card("Total cost", fmt(cost["total_usd"], 6), "USD")
        + card("Minutes with data", fmt(len(cost["by_minute"]), 0))
        + "</div>"
        + series_bars(cost["by_minute"], "USD")
    )

    tokens = data["tokens"]
    tokens_body = (
        '<div class="cards">'
        + card("Input", fmt(tokens["input_total"], 0), "tokens")
        + card("Output", fmt(tokens["output_total"], 0), "tokens")
        + card("Total", fmt(tokens["input_total"] + tokens["output_total"], 0), "tokens")
        + "</div>"
    )

    quality = data["quality"]
    quality_body = (
        '<div class="cards">'
        + card("Mean quality", fmt(quality["mean"], 3), "score")
        + card("Samples", fmt(quality["samples"], 0))
        + "</div>"
        + '<div class="quality-track"><div class="quality-fill" style="width:'
        + f'{max(0.0, min(1.0, quality["mean"])) * 100:.1f}%'
        + '"></div></div>'
    )

    bodies = {
        "latency": latency_body,
        "traffic": traffic_body,
        "errors": errors_body,
        "cost": cost_body,
        "tokens": tokens_body,
        "quality": quality_body,
    }
    rendered_panels = "".join(panel_shell(panels[panel_id], bodies[panel_id]) for panel_id in (
        "latency", "traffic", "errors", "cost", "tokens", "quality"
    ))
    window = metrics["window"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>{escape(str(contract['title']))}</title>
  <style>
    :root {{ color-scheme: dark; --bg: #0b1220; --panel: #111c2e; --line: #263854; --text: #e5eefc; --muted: #93a4be; --accent: #5eead4; --accent2: #60a5fa; --warn: #fbbf24; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at top right, #172b4b, var(--bg) 48%); color: var(--text); font: 15px/1.45 system-ui, sans-serif; }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 30px 22px 48px; }}
    header {{ margin-bottom: 22px; }}
    h1 {{ margin: 0 0 7px; font-size: clamp(1.55rem, 3vw, 2.25rem); }}
    h2 {{ margin: 0; font-size: 1.05rem; }}
    .subtitle, .note, .panel-meta {{ color: var(--muted); }}
    .subtitle {{ margin: 0; }}
    .status {{ display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 14px; color: var(--muted); font-size: .88rem; }}
    .status strong {{ color: var(--accent); font-weight: 600; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .panel {{ min-height: 205px; padding: 18px; border: 1px solid var(--line); border-radius: 15px; background: rgba(17, 28, 46, .9); box-shadow: 0 12px 30px rgba(0,0,0,.16); }}
    .panel-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .panel-id {{ padding: 3px 8px; border: 1px solid #335273; border-radius: 999px; color: var(--accent2); font-size: .72rem; letter-spacing: .04em; text-transform: uppercase; }}
    .panel-meta {{ margin-top: 5px; font-size: .78rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(105px, 1fr)); gap: 9px; margin-top: 19px; }}
    .metric-card {{ padding: 11px; border-radius: 10px; background: #0d1728; }}
    .metric-label {{ color: var(--muted); font-size: .76rem; }}
    .metric-value {{ margin-top: 4px; color: var(--text); font-size: 1.25rem; font-weight: 700; }}
    .metric-value span {{ margin-left: 4px; color: var(--muted); font-size: .7rem; font-weight: 500; }}
    .note {{ margin: 14px 0 0; font-size: .8rem; }}
    .bars {{ display: flex; align-items: end; gap: 6px; height: 72px; margin-top: 17px; padding: 6px 0 0; border-bottom: 1px solid var(--line); }}
    .bar-wrap {{ display: flex; flex: 1; align-items: end; height: 100%; min-width: 0; }}
    .bar {{ width: 100%; min-height: 3px; border-radius: 4px 4px 0 0; background: linear-gradient(180deg, var(--accent), var(--accent2)); }}
    .bar-label {{ position: absolute; margin-top: 77px; color: var(--muted); font-size: .62rem; transform: translateX(-5px) rotate(-35deg); transform-origin: left top; }}
    .empty {{ margin-top: 22px; color: var(--muted); }}
    .quality-track {{ height: 12px; margin-top: 24px; overflow: hidden; border-radius: 999px; background: #25334a; }}
    .quality-fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent2), var(--accent)); }}
    footer {{ margin-top: 20px; color: var(--muted); font-size: .78rem; }}
    @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 22px 14px 36px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(str(contract['title']))}</h1>
      <p class="subtitle">Live dashboard from <code>data/logs.jsonl</code></p>
      <div class="status">
        <span>Window: <strong>{escape(window['start'])}</strong> → <strong>{escape(window['end'])}</strong></span>
        <span>Records: <strong>{metrics['record_count']}</strong></span>
        <span>Refresh: <strong>{contract['refresh_seconds']}s</strong></span>
      </div>
    </header>
    <div class="grid">{rendered_panels}</div>
    <footer>All values are calculated from the current log window; no metric values are hard-coded.</footer>
  </main>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            body = render_dashboard().encode("utf-8")
            content_type = "text/html; charset=utf-8"
        elif path == "/api/metrics":
            body = json.dumps(build_metrics(), ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            self.send_error(404, "Not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 13 local dashboard")
    parser.add_argument("--host", default=os.getenv("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DASHBOARD_PORT", "8050")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    print(f"Reading: {LOG_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
