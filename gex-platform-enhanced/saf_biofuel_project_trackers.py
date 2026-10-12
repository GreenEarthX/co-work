#!/usr/bin/env python3
"""Collect project/facility records from public SAF, biofuel and hydrogen sources.

Sources handled:
  1. IATA announced SAF facilities page (browser-rendered visualization)
  2. ICAO SAF production facilities tracker (Power BI dashboard)
  3. OSTI/Zenodo U.S. ethanol and biodiesel plant/feedstock CSV dataset
  4. EPRI Renewable Fuels Atlas U.S. facility CSV/JSON ZIP datasets
  5. Nordic Hydrogen Valleys public API (167 project records)
  6. ICAO Finvest SAF project portal (Power BI dashboard)

The script does not bypass authentication, paywalls or access controls. For
Power BI/browser-rendered sources, it saves the raw page and extracts visible
HTML tables/text where possible. The direct-download/API sources are parsed
into normalized JSON/CSV files.

Install:
    python -m pip install requests beautifulsoup4
    # Optional, for IATA/ICAO dashboards:
    python -m pip install playwright
    python -m playwright install chromium

Run all sources:
    python saf_biofuel_project_trackers.py --output-dir project_data

Run direct sources only:
    python saf_biofuel_project_trackers.py --output-dir project_data --skip-browser

Run one source:
    python saf_biofuel_project_trackers.py --source nordic --output-dir project_data

Notes:
  - ICAO and IATA dashboard structures may change. Raw HTML is retained so
    extraction can be debugged without downloading the page again.
  - Respect source terms, robots rules and update intervals.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent

URLS = {
    "iata": "https://www.iata.org/en/programs/sustainability/sustainable-aviation-fuel-saf/",
    "icao_saf": "https://www.icao.int/SAF/SAF-production-facilities",
    "icao_finvest": "https://www.icao.int/finvest/saf",
    "nordic_api": "https://admin.nordich2valleys.org/api/nodes?populate=deep&pagination[pageSize]=200",
    "zenodo_record": "https://zenodo.org/api/records/8250829",
    "epri_download_page": "https://apps.epri.com/lcri-rf-atlas/public/download.html",
}

EPRI_FILES = {
    "existing_renewable_diesel": "data-download-csv/lcri-rf-atlas-existingRenDiesel-csv.zip",
    "existing_biodiesel": "data-download-csv/lcri-rf-atlas-existingBiodiesel-csv.zip",
    "existing_rng": "data-download-csv/lcri-rf-atlas-existingRNG-csv.zip",
    "ethanol": "data-download-csv/lcri-rf-atlas-ethanol-csv.zip",
    "hydrogen_production": "data-download-csv/lcri-rf-atlas-hydrogenProduction-csv.zip",
}
EPRI_BASE = "https://apps.epri.com/lcri-rf-atlas/public/"

USER_AGENT = "saf-biofuel-project-trackers/1.0 (public research data collection)"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def clean(value: Any) -> Any:
    if isinstance(value, str):
        value = re.sub(r"\s+", " ", value).strip()
        if value in {"", "—", "–", "-", "N/A", "n/a"}:
            return None
    return value


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dictionaries; lists are kept as JSON-compatible values."""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict):
                out.update(flatten(item, name))
            else:
                out[name] = item
    else:
        out[prefix or "value"] = value
    return out


def write_records(out_dir: Path, name: str, records: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{name}.json"
    csv_path = out_dir / f"{name}.csv"
    payload = {"metadata": metadata, "records": records}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields: list[str] = []
    for record in records:
        for key in record:
            if key not in fields:
                fields.append(key)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {}
            for key in fields:
                value = record.get(key)
                row[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            writer.writerow(row)
    print(f"{name}: wrote {len(records)} records -> {json_path} and {csv_path}")


def save_raw(out_dir: Path, filename: str, content: bytes) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(content)
    return path


def source_metadata(source: str, url: str, **extra: Any) -> dict[str, Any]:
    return {"source": source, "source_url": url, "retrieved_at_utc": utc_now(), **extra}


def run_nordic(s: requests.Session, out_dir: Path) -> dict[str, Any]:
    """Download all Nordic Hydrogen Valleys project nodes from the public API."""
    url = URLS["nordic_api"]
    response = s.get(url, timeout=60)
    response.raise_for_status()
    raw = response.content
    save_raw(out_dir / "raw", "nordic_nodes.json", raw)
    payload = response.json()
    records: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        record = {"id": item.get("id"), **attrs}
        for nested in ("coords", "capacity", "projectPhase", "region", "endUseSectors", "stakeholders", "links"):
            if nested in record and isinstance(record[nested], (dict, list)):
                record[nested] = record[nested]
        records.append(record)
    total = payload.get("meta", {}).get("pagination", {}).get("total")
    write_records(out_dir, "nordic_hydrogen_valleys_projects", records,
                  source_metadata("Nordic Hydrogen Valleys API", url, expected_total=total))
    return {"records": len(records), "expected": total}


def iter_zip_text_files(content: bytes) -> Iterable[tuple[str, str]]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            lower = info.filename.lower()
            if lower.endswith((".csv", ".json")):
                yield info.filename, archive.read(info).decode("utf-8-sig", errors="replace")


def parse_csv_text(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(text.splitlines())
    return [{key: clean(value) for key, value in row.items()} for row in reader]


def run_epri(s: requests.Session, out_dir: Path) -> dict[str, Any]:
    """Download EPRI's public facility CSV ZIPs and export each as JSON/CSV."""
    raw_dir = out_dir / "raw" / "epri"
    summary: dict[str, Any] = {}
    for name, relative in EPRI_FILES.items():
        url = urljoin(EPRI_BASE, relative)
        response = s.get(url, timeout=90)
        response.raise_for_status()
        save_raw(raw_dir, f"{name}.zip", response.content)
        for inner_name, text in iter_zip_text_files(response.content):
            if inner_name.lower().endswith(".csv"):
                records = parse_csv_text(text)
            else:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    records = [flatten(x) if isinstance(x, dict) else {"value": x} for x in parsed]
                elif isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
                    records = [flatten(x) if isinstance(x, dict) else {"value": x} for x in parsed["data"]]
                else:
                    records = [flatten(parsed)] if isinstance(parsed, dict) else [{"value": parsed}]
            stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(inner_name).stem).strip("_")
            output_name = f"epri_{name}_{stem}" if stem else f"epri_{name}"
            write_records(out_dir, output_name, records,
                          source_metadata("EPRI Renewable Fuels Atlas", url, archive_member=inner_name))
            summary[output_name] = len(records)
    return summary


def download_zenodo_file(s: requests.Session, out_dir: Path, file_entry: dict[str, Any]) -> tuple[Path, bytes]:
    key = file_entry.get("key") or Path(file_entry["links"]["self"]).name
    url = file_entry.get("links", {}).get("self")
    if not url:
        raise ValueError(f"Zenodo file has no download URL: {file_entry}")
    response = s.get(url, timeout=120)
    response.raise_for_status()
    path = save_raw(out_dir, key, response.content)
    return path, response.content


def run_zenodo(s: requests.Session, out_dir: Path) -> dict[str, Any]:
    """Download the public OSTI-linked Zenodo biofuel plant/feedstock files."""
    record_url = URLS["zenodo_record"]
    response = s.get(record_url, timeout=60)
    response.raise_for_status()
    record = response.json()
    save_raw(out_dir / "raw" / "zenodo", "record.json", response.content)
    summary: dict[str, Any] = {}
    for entry in record.get("files", []):
        path, content = download_zenodo_file(s, out_dir / "raw" / "zenodo", entry)
        if path.suffix.lower() == ".zip":
            for member, text in iter_zip_text_files(content):
                if member.lower().endswith(".csv"):
                    records = parse_csv_text(text)
                    archive_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem).strip("_")
                    member_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(member).stem).strip("_")
                    name = f"zenodo_{archive_stem}_{member_stem}"
                    write_records(out_dir, name, records,
                                  source_metadata("Zenodo record linked by OSTI", record_url,
                                                  archive_file=path.name, archive_member=member))
                    summary[name] = len(records)
    return summary


def extract_html_tables(html: str, source_url: str) -> list[dict[str, Any]]:
    """Extract ordinary HTML tables; dashboard canvases may yield zero rows."""
    soup = BeautifulSoup(html, "html.parser")
    all_records: list[dict[str, Any]] = []
    for table_index, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [clean(x.get_text(" ", strip=True)) or f"column_{i+1}" for i, x in enumerate(rows[0].find_all(["th", "td"]))]
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            values = [clean(x.get_text(" ", strip=True)) for x in cells]
            if not any(values):
                continue
            record = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
            record["source_url"] = source_url
            record["html_table_index"] = table_index
            all_records.append(record)
    return all_records


def extract_visible_text_records(html: str, source_url: str, keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    """Fallback: preserve visible dashboard text as one searchable record."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    matches = [k for k in keywords if k.lower() in text.lower()]
    return [{"source_url": source_url, "visible_text": text, "matched_keywords": matches}] if text else []


def run_http_dashboard(s: requests.Session, out_dir: Path, name: str, url: str) -> dict[str, Any]:
    response = s.get(url, timeout=90)
    response.raise_for_status()
    raw_path = save_raw(out_dir / "raw" / "dashboards", f"{name}.html", response.content)
    records = extract_html_tables(response.text, url)
    if records:
        write_records(out_dir, name, records, source_metadata(name, url, extraction="ordinary HTML tables"))
    else:
        fallback = extract_visible_text_records(response.text, url, ("SAF", "facility", "project", "status"))
        write_records(out_dir, name, fallback, source_metadata(name, url,
                      extraction="visible HTML text fallback; dashboard rows not present in server HTML",
                      raw_html=str(raw_path)))
    return {"records": len(records), "raw_html": str(raw_path), "browser_needed": not bool(records)}


def try_browser_dashboard(out_dir: Path, name: str, url: str, wait_seconds: float = 8.0) -> dict[str, Any]:
    """Render a dashboard/page with Playwright and extract tables/text if available."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"records": 0, "browser_needed": True, "error": "Playwright not installed"}

    raw_dir = out_dir / "raw" / "dashboards"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(int(wait_seconds * 1000))
        html = page.content()
        save_raw(raw_dir, f"{name}_rendered.html", html.encode("utf-8"))
        # Capture visible tables and links. Power BI often renders canvases, so
        # the fallback record preserves text for manual inspection.
        records = extract_html_tables(html, url)
        if not records:
            body_text = page.locator("body").inner_text(timeout=20)
            records = [{"source_url": url, "visible_text": re.sub(r"\s+", " ", body_text).strip()}]
        browser.close()
    write_records(out_dir, name, records, source_metadata(name, url, extraction="Playwright-rendered page"))
    return {"records": len(records), "browser_needed": False}


def run_source(name: str, s: requests.Session, out_dir: Path, skip_browser: bool) -> Any:
    if name == "nordic":
        return run_nordic(s, out_dir)
    if name == "epri":
        return run_epri(s, out_dir)
    if name == "zenodo":
        return run_zenodo(s, out_dir)
    if name == "iata":
        if skip_browser:
            return run_http_dashboard(s, out_dir, "iata_saf_facilities", URLS["iata"])
        return try_browser_dashboard(out_dir, "iata_saf_facilities", URLS["iata"])
    if name == "icao_saf":
        if skip_browser:
            return run_http_dashboard(s, out_dir, "icao_saf_production_facilities", URLS["icao_saf"])
        return try_browser_dashboard(out_dir, "icao_saf_production_facilities", URLS["icao_saf"])
    if name == "icao_finvest":
        if skip_browser:
            return run_http_dashboard(s, out_dir, "icao_finvest_saf_projects", URLS["icao_finvest"])
        return try_browser_dashboard(out_dir, "icao_finvest_saf_projects", URLS["icao_finvest"])
    raise ValueError(f"Unknown source: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("project_data"))
    parser.add_argument("--source", choices=["iata", "icao_saf", "zenodo", "epri", "nordic", "icao_finvest"], action="append")
    parser.add_argument("--skip-browser", action="store_true", help="Do not use optional Playwright rendering")
    args = parser.parse_args()

    sources = args.source or ["iata", "icao_saf", "zenodo", "epri", "nordic", "icao_finvest"]
    s = session()
    manifest: dict[str, Any] = {"started_at_utc": utc_now(), "sources": {}}
    for name in sources:
        try:
            print(f"\n== {name} ==")
            manifest["sources"][name] = {"ok": True, "result": run_source(name, s, args.output_dir, args.skip_browser)}
        except Exception as exc:
            print(f"{name}: ERROR: {exc}", file=sys.stderr)
            manifest["sources"][name] = {"ok": False, "error": repr(exc)}
    manifest["finished_at_utc"] = utc_now()
    (args.output_dir / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nManifest written to {args.output_dir / 'manifest.json'}")
    return 0 if all(x.get("ok") for x in manifest["sources"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
