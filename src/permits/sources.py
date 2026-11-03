"""Download and read the City of Toronto's building permit files.

Two datasets on Toronto Open Data, both refreshed daily:
- "Building Permits - Cleared Permits": permits closed or cancelled since 2017.
- "Building Permits - Active Permits": permits still open.

A permit issued in 2017 or later is in one file or the other, so together they cover every
permit issued since then, finished or not.

Only the columns the analysis needs are read. Street addresses, descriptions and builder
names (some builders are individuals) are never loaded.
"""

from __future__ import annotations

import json
import shutil
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import certifi
import pandas as pd

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
COLUMNS = [
    "PERMIT_NUM",
    "REVISION_NUM",
    "PERMIT_TYPE",
    "STRUCTURE_TYPE",
    "POSTAL",  # forward sortation area: the first three characters of a postal code
    "APPLICATION_DATE",
    "ISSUED_DATE",
    "COMPLETED_DATE",
    "STATUS",
    "DWELLING_UNITS_CREATED",
    "DWELLING_UNITS_LOST",
]


@dataclass(frozen=True)
class Dataset:
    key: str  # short name used for the cached file
    package: str  # Toronto Open Data dataset id
    resource: str  # the CSV's name inside the dataset


CLEARED = Dataset("cleared", "building-permits-cleared-permits", "Cleared Building Permits since 2017.csv")
ACTIVE = Dataset("active", "building-permits-active-permits", "building-permits-active-permits.csv")


class DataError(Exception):
    """The downloaded data is missing something the analysis needs."""


def _context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def _api(action: str, **params) -> dict:
    url = f"{CKAN}/{action}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=60, context=_context()) as response:
        body = json.load(response)
    if not body.get("success"):
        raise DataError(f"Toronto Open Data returned an error for {action}: {body.get('error')}")
    return body["result"]


def find_resource(package: dict, name: str) -> dict:
    for resource in package["resources"]:
        if resource["name"] == name:
            return resource
    names = ", ".join(r["name"] for r in package["resources"])
    raise DataError(f"No file named {name!r} in {package['name']}; found: {names}")


def download(dataset: Dataset, cache_dir: Path, refresh: bool = False) -> Path:
    """Save the dataset's CSV in cache_dir, with a small JSON file recording what was downloaded."""
    csv_path = cache_dir / f"{dataset.key}.csv"
    meta_path = cache_dir / f"{dataset.key}.json"
    if csv_path.exists() and meta_path.exists() and not refresh:
        return csv_path
    package = _api("package_show", id=dataset.package)
    resource = find_resource(package, dataset.resource)
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = csv_path.with_suffix(".part")
    with urllib.request.urlopen(resource["url"], timeout=600, context=_context()) as response, partial.open("wb") as f:
        shutil.copyfileobj(response, f)
    partial.replace(csv_path)
    meta_path.write_text(
        json.dumps(
            {
                "dataset": dataset.package,
                "file": dataset.resource,
                "url": resource["url"],
                "last_modified": resource.get("last_modified"),
                "downloaded": pd.Timestamp.now(tz="America/Toronto").isoformat(timespec="seconds"),
            },
            indent=2,
        )
    )
    return csv_path


def downloaded_on(cache_dir: Path, dataset: Dataset) -> pd.Timestamp:
    meta = json.loads((cache_dir / f"{dataset.key}.json").read_text())
    return pd.Timestamp(meta["downloaded"]).tz_localize(None).normalize()


def read(path: Path, source: str) -> pd.DataFrame:
    """Read the needed columns as text. Parsing and checks happen in clean.py."""
    header = pd.read_csv(path, nrows=0).columns
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise DataError(f"{path.name} is missing columns: {', '.join(missing)}")
    frame = pd.read_csv(path, usecols=COLUMNS, dtype=str, keep_default_na=False)
    return frame.assign(SOURCE=source)
