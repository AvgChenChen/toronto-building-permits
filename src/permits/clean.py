"""Turn the two raw files into tidy tables, recording every row that's dropped and why.

The cleaning log goes into the report, so a reader can see exactly what was excluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .sources import DataError

# Statuses for permits that were issued but won't lead to finished work. They count towards
# approval times (the permit was issued) but not towards homes approved.
ENDED = {
    "Cancelled",
    "Refused",
    "Revoked",
    "Revocation Pending",
    "Revocation Notice Sent",
    "Pending Cancellation",
    "Abandoned",
    "Superseded",
}

CATEGORIES = {
    "New Building": "Apartment and mixed-use buildings",
    "New Houses": "New houses",
    "Small Residential Projects": "Suites, multiplexes and additions",
    "Building Additions/Alterations": "Suites, multiplexes and additions",
}
OTHER = "Other permit types"


@dataclass
class CleaningLog:
    steps: list[tuple[str, int]] = field(default_factory=list)

    def add(self, what: str, count: int) -> None:
        if count:
            self.steps.append((what, int(count)))


def _dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.str.strip(), format="%Y-%m-%d", errors="coerce")


def _whole_numbers(series: pd.Series, column: str) -> pd.Series:
    values = series.str.replace(",", "", regex=False).str.strip()
    missing = values.eq("")
    numbers = pd.to_numeric(values.mask(missing), errors="coerce")
    invalid = ~missing & (numbers.isna() | numbers.lt(0) | numbers.mod(1).ne(0))
    if invalid.any():
        example = values[invalid].iloc[0]
        raise DataError(f"{column} has {int(invalid.sum())} invalid unit count(s); example {example!r}")
    return numbers.fillna(0)


def parse(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in ["APPLICATION_DATE", "ISSUED_DATE", "COMPLETED_DATE"]:
        out[column] = _dates(out[column])
    out["UNITS_CREATED"] = _whole_numbers(out["DWELLING_UNITS_CREATED"], "DWELLING_UNITS_CREATED")
    out["UNITS_LOST"] = _whole_numbers(out["DWELLING_UNITS_LOST"], "DWELLING_UNITS_LOST")
    out["POSTAL"] = out["POSTAL"].str.strip().str.upper()
    return out.drop(columns=["DWELLING_UNITS_CREATED", "DWELLING_UNITS_LOST"])


def issued_permits(
    cleared: pd.DataFrame, active: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, log: CleaningLog
) -> pd.DataFrame:
    """One row per permit issued between start and end (inclusive), from both files."""
    rows = parse(pd.concat([cleared, active], ignore_index=True))
    log.add("Rows read from both files", len(rows))

    revision = rows["REVISION_NUM"].str.strip() != "00"
    log.add("Dropped: revisions to an earlier permit (they repeat its details)", revision.sum())
    rows = rows[~revision]

    # A permit can be in both files while the city moves it from active to cleared, and one permit
    # number can carry both an early-start "conditional" permit and the full permit. So a permit is
    # identified by number and type, and the cleared copy (the later one) wins.
    rows = rows.sort_values("SOURCE", key=lambda s: s.map({"cleared": 0, "active": 1}), kind="stable")
    duplicate = rows.duplicated(["PERMIT_NUM", "REVISION_NUM", "PERMIT_TYPE"], keep="first")
    log.add("Dropped: the same permit listed twice", duplicate.sum())
    rows = rows[~duplicate]

    not_issued = rows["ISSUED_DATE"].isna()
    log.add("Dropped: not issued (still under review, refused before issue, or no date)", not_issued.sum())
    rows = rows[~not_issued]

    outside = (rows["ISSUED_DATE"] < start) | (rows["ISSUED_DATE"] > end)
    log.add(f"Dropped: issued before {start:%b %-d, %Y} or after {end:%b %-d, %Y}", outside.sum())
    rows = rows[~outside].copy()

    wait = (rows["ISSUED_DATE"] - rows["APPLICATION_DATE"]).dt.days
    bad_wait = wait.isna() | (wait < 0)
    log.add("Kept, but no approval time: application date missing or after the issue date", bad_wait.sum())
    rows["WAIT_DAYS"] = wait.where(~bad_wait)

    rows["CATEGORY"] = rows["PERMIT_TYPE"].map(CATEGORIES).fillna(OTHER)
    rows["ENDED"] = rows["STATUS"].isin(ENDED)
    rows["YEAR"] = rows["ISSUED_DATE"].dt.year
    log.add("Permits analysed", len(rows))
    return rows.reset_index(drop=True)


def closed_permits(cleared: pd.DataFrame, as_of: pd.Timestamp, log: CleaningLog) -> pd.DataFrame:
    """Permits the city marked Closed, with how old each was when it was closed."""
    rows = parse(cleared)
    rows = rows[rows["STATUS"].str.strip() == "Closed"]
    future = rows["COMPLETED_DATE"] > as_of
    log.add(f"Dropped from the closing analysis: closed date after {as_of:%b %-d, %Y}", future.sum())
    rows = rows[~future & rows["COMPLETED_DATE"].notna()].copy()
    rows["AGE_YEARS"] = (rows["COMPLETED_DATE"] - rows["ISSUED_DATE"]).dt.days / 365.25
    rows["MONTH"] = rows["COMPLETED_DATE"].dt.to_period("M")
    return rows.reset_index(drop=True)
