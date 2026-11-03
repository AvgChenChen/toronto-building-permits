"""The measures: homes approved, where, approval times, and the permit-closing trend."""

from __future__ import annotations

import pandas as pd

from .clean import CATEGORIES, OTHER

APPROVAL_TYPES = ["New Houses", "Small Residential Projects", "Building Additions/Alterations", "New Building"]
CATEGORY_ORDER = list(dict.fromkeys(CATEGORIES.values())) + [OTHER]


def full_years(issued: pd.DataFrame, end: pd.Timestamp) -> list[int]:
    """Years with all twelve months inside the data. The last year is partial unless end is Dec 31."""
    years = sorted(issued["YEAR"].unique())
    return [y for y in years if y < end.year or (end.month, end.day) == (12, 31)]


def homes_by_year(issued: pd.DataFrame) -> pd.DataFrame:
    """New homes on permits issued each year, by kind of project, plus homes demolished.

    Permits later cancelled or revoked are left out: those homes aren't going to be built.
    """
    live = issued[~issued["ENDED"]]
    created = live.pivot_table(index="YEAR", columns="CATEGORY", values="UNITS_CREATED", aggfunc="sum", fill_value=0)
    created = created.reindex(columns=[c for c in CATEGORY_ORDER if c in created.columns])
    created = created.loc[:, created.sum() > 0]
    table = created.copy()
    table["Total"] = created.sum(axis=1)
    table["Demolished"] = live.groupby("YEAR")["UNITS_LOST"].sum()
    table["Net new homes"] = table["Total"] - table["Demolished"]
    return table.astype(int)


def homes_by_area(issued: pd.DataFrame, top: int = 10) -> tuple[pd.DataFrame, int]:
    """The areas (first three characters of the postal code) with the most new homes approved.

    Returns the table and the number of homes on permits with no postal code.
    """
    live = issued[~issued["ENDED"]]
    unknown = int(live.loc[live["POSTAL"] == "", "UNITS_CREATED"].sum())
    by_area = live[live["POSTAL"] != ""].groupby("POSTAL")["UNITS_CREATED"].sum().sort_values(ascending=False)
    total = live["UNITS_CREATED"].sum()
    table = by_area.head(top).to_frame("Homes").astype(int)
    table["Share of city"] = table["Homes"] / total
    return table, unknown


def approval_times(issued: pd.DataFrame, types: list[str] = APPROVAL_TYPES) -> pd.DataFrame:
    """Days from application to issue: median and 90th percentile, by permit type and issue year."""
    rows = issued[issued["PERMIT_TYPE"].isin(types) & issued["WAIT_DAYS"].notna()]
    grouped = rows.groupby(["PERMIT_TYPE", "YEAR"])["WAIT_DAYS"]
    table = pd.DataFrame(
        {"Permits": grouped.size(), "Median days": grouped.median(), "90th percentile days": grouped.quantile(0.9)}
    )
    return table


def closing_trend(closed: pd.DataFrame) -> pd.DataFrame:
    """Per month: permits marked Closed, and their median age (years since issue) when closed."""
    grouped = closed.groupby("MONTH")
    return pd.DataFrame({"Closed": grouped.size(), "Median age (years)": grouped["AGE_YEARS"].median()})


def cleanup_start(trend: pd.DataFrame, baseline_months: int = 60, factor: float = 1.5, run: int = 3):
    """The first month of a sustained jump in closings, or None.

    The baseline is the median monthly count over the first `baseline_months`. A jump is `run`
    months in a row at `factor` times the baseline or more.
    """
    baseline = trend["Closed"].iloc[:baseline_months].median()
    high = trend["Closed"] >= factor * baseline
    streak = high.astype(int).groupby((~high).cumsum()).cumsum()
    hits = streak[streak >= run]
    if hits.empty:
        return None, float(baseline)
    start = hits.index[0] - (run - 1)
    return start, float(baseline)
