"""Turn the cleaned permits into findings, tables, charts and a Markdown report.

Every sentence in the findings is built from a calculated number, so re-running on newer
data can't leave a stale claim behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import analysis as an
from . import charts
from .clean import CleaningLog, closed_permits, issued_permits

README_START = "<!-- results:start -->"
README_END = "<!-- results:end -->"

NAMES = {
    "New Houses": "New houses",
    "Small Residential Projects": "Small residential projects",
    "Building Additions/Alterations": "Additions and alterations",
    "New Building": "New buildings",
}
SMALL_SCALE = "Suites, multiplexes and additions"
APARTMENTS = "Apartment and mixed-use buildings"


@dataclass
class Analysis:
    start: pd.Timestamp
    end: pd.Timestamp
    source_note: str
    issued: pd.DataFrame
    homes: pd.DataFrame
    areas: pd.DataFrame
    unknown_area_homes: int
    approvals: pd.DataFrame
    trend: pd.DataFrame
    cleanup: pd.Period | None
    baseline: float
    log: CleaningLog

    @property
    def full_years(self) -> list[int]:
        return an.full_years(self.issued, self.end)

    @property
    def partial(self) -> dict[int, str]:
        last = int(self.homes.index.max())
        return {} if last in self.full_years else {last: f"to {self.end:%b %-d}"}

    @property
    def categories(self) -> list[str]:
        return [c for c in an.CATEGORY_ORDER if c in self.homes.columns]


def analyse(
    cleared: pd.DataFrame, active: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, source_note: str = ""
) -> Analysis:
    log = CleaningLog()
    issued = issued_permits(cleared, active, start, end, log)
    closed = closed_permits(cleared, end, log)
    trend = an.closing_trend(closed)
    # Only whole months, so a month that has just started doesn't look like a sudden drop.
    last_whole = pd.Period(end, "M") if (end + pd.Timedelta(days=1)).day == 1 else pd.Period(end, "M") - 1
    trend = trend.loc[pd.Period(start, "M") : last_whole]
    cleanup, baseline = an.cleanup_start(trend)
    areas, unknown = an.homes_by_area(issued)
    return Analysis(
        start=start,
        end=end,
        source_note=source_note,
        issued=issued,
        homes=an.homes_by_year(issued),
        areas=areas,
        unknown_area_homes=unknown,
        approvals=an.approval_times(issued),
        trend=trend,
        cleanup=cleanup,
        baseline=baseline,
        log=log,
    )


# ---------------------------------------------------------------- formatting


def num(x: float) -> str:
    return f"{x:,.0f}"


def days(x: float) -> str:
    return f"{x:,.0f} day{'s' if round(x) != 1 else ''}"


def period(a: Analysis) -> str:
    return f"{a.start:%b %Y} to {a.end:%b %Y}"


# ---------------------------------------------------------------- findings


def _median(a: Analysis, permit_type: str, year: int) -> float | None:
    try:
        return float(a.approvals.loc[(permit_type, year), "Median days"])
    except KeyError:
        return None


def _change(before: float, after: float) -> str:
    if after == before:
        return "the same as"
    return "faster than" if after < before else "slower than"


def findings(a: Analysis) -> list[str]:
    h = a.homes
    full = [y for y in a.full_years if y in h.index]
    out = []

    out.append(
        f"**Toronto issued building permits for {num(h['Total'].sum())} new homes** from {period(a)}. "
        f"Those projects remove {num(h['Demolished'].sum())} existing homes, so the net gain is "
        f"{num(h['Net new homes'].sum())}."
    )

    if len(full) >= 2:
        totals = h.loc[full, "Total"]
        busiest, quietest, latest = int(totals.idxmax()), int(totals.idxmin()), full[-1]
        average = totals.mean()
        direction = "above" if totals[latest] >= average else "below"
        out.append(
            f"**{busiest} was the busiest year ({num(totals[busiest])} homes) and {quietest} the quietest "
            f"({num(totals[quietest])}).** {latest}, the latest full year, had {num(totals[latest])}: "
            f"{abs(totals[latest] / average - 1):.0%} {direction} the {full[0]}–{latest} average of {num(average)}."
        )

    if APARTMENTS in h.columns:
        share = h[APARTMENTS].sum() / h["Total"].sum()
        out.append(
            f"**{share:.0%} of the new homes are in apartment and mixed-use buildings.** New houses "
            f"account for {h.get('New houses', pd.Series(0)).sum() / h['Total'].sum():.0%}."
        )

    if SMALL_SCALE in h.columns and len(full) >= 2:
        first, latest = h.loc[full[0], SMALL_SCALE], h.loc[full[-1], SMALL_SCALE]
        if first > 0:
            ratio = latest / first
            out.append(
                f"**Small-scale housing grew:** permits for suites, multiplexes and additions added "
                f"{num(latest)} homes in {full[-1]}, {ratio:.1f} times the {num(first)} in {full[0]}."
            )

    top = a.areas
    if len(top):
        out.append(
            f"**{top.index[0]} had the most new homes approved: {num(top['Homes'].iloc[0])}, or "
            f"{top['Share of city'].iloc[0]:.0%} of the city.** The ten busiest postal areas (out of about "
            f"{a.issued['POSTAL'].replace('', pd.NA).nunique()}) account for {top['Share of city'].sum():.0%}."
        )
        missing = a.issued[~a.issued["ENDED"] & (a.issued["POSTAL"] == "")]
        if a.unknown_area_homes:
            big = missing[missing["UNITS_CREATED"] >= 100]
            out.append(
                f"**{a.unknown_area_homes / h['Total'].sum():.0%} of new homes ({num(a.unknown_area_homes)}) have no "
                f"postal code**, {big['UNITS_CREATED'].sum() / a.unknown_area_homes:.0%} of them on {len(big)} "
                f"permit{'s' if len(big) != 1 else ''} for 100 or more homes. Areas with large new developments "
                "are probably undercounted."
            )

    if len(full) >= 2:
        first, latest = full[0], full[-1]
        parts = []
        for permit_type in ["New Houses", "New Building"]:
            before, after = _median(a, permit_type, first), _median(a, permit_type, latest)
            if before is not None and after is not None:
                parts.append(
                    f"{NAMES[permit_type].lower()} took a median of {days(after)} in {latest}, "
                    f"{_change(before, after)} {days(before)} in {first}"
                )
        if parts:
            out.append("**From application to permit**, " + "; ".join(parts) + ".")

    if a.cleanup is not None:
        before = a.trend.loc[: a.cleanup - 1]
        after = a.trend.loc[a.cleanup :]
        out.append(
            f"**From {a.cleanup:%B %Y}, the city closed far more permits than usual**: "
            f"{num(after['Closed'].mean())} a month against a typical {num(a.baseline)}. The median "
            f"permit closed in that time was {after['Median age (years)'].median():.1f} years old, against "
            f"{before['Median age (years)'].median():.1f} before. This looks like old paperwork being cleared, "
            f"so **completion dates since then don't show when buildings were finished**, and this "
            f"report doesn't use them to count homes."
        )
    return out


# ---------------------------------------------------------------- tables


def homes_table(a: Analysis) -> str:
    columns = a.categories + ["Total", "Demolished", "Net new homes"]
    head = "| Year | " + " | ".join(columns) + " |\n|---|" + "---|" * len(columns) + "\n"
    lines = []
    for year, row in a.homes.iterrows():
        label = f"{year} ({a.partial[year]})" if year in a.partial else str(year)
        lines.append(f"| {label} | " + " | ".join(num(row[c]) for c in columns) + " |")
    total = a.homes[columns].sum()
    lines.append("| **All years** | " + " | ".join(f"**{num(total[c])}**" for c in columns) + " |")
    return head + "\n".join(lines)


def areas_table(a: Analysis) -> str:
    head = "| Postal area | New homes approved | Share of city |\n|---|---|---|\n"
    lines = [f"| {area} | {num(r['Homes'])} | {r['Share of city']:.1%} |" for area, r in a.areas.iterrows()]
    return head + "\n".join(lines)


def approvals_table(a: Analysis) -> str:
    types = [t for t in an.APPROVAL_TYPES if t in a.approvals.index.get_level_values(0)]
    head = "| Year issued | " + " | ".join(NAMES[t] for t in types) + " |\n|---|" + "---|" * len(types) + "\n"
    years = sorted(a.approvals.index.get_level_values(1).unique())
    lines = []
    for year in years:
        cells = []
        for t in types:
            if (t, year) in a.approvals.index:
                r = a.approvals.loc[(t, year)]
                cells.append(f"{num(r['Median days'])} ({num(r['90th percentile days'])})")
            else:
                cells.append("–")
        label = f"{year} ({a.partial[year]})" if year in a.partial else str(year)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return head + "\n".join(lines)


def closing_table(a: Analysis) -> str:
    by_year = a.trend.groupby(a.trend.index.year).agg(closed=("Closed", "sum"), age=("Median age (years)", "median"))
    head = "| Year | Permits closed | Median age when closed (years) |\n|---|---|---|\n"
    return head + "\n".join(f"| {y} | {num(r['closed'])} | {r['age']:.1f} |" for y, r in by_year.iterrows())


def log_table(a: Analysis) -> str:
    head = "| Step | Rows |\n|---|---|\n"
    return head + "\n".join(f"| {what} | {num(n)} |" for what, n in a.log.steps)


# ---------------------------------------------------------------- output


def draw_charts(a: Analysis, chart_dir: Path) -> dict[str, Path]:
    source = f"Data: City of Toronto Open Data, building permits. Permits issued {period(a)}."
    types = [t for t in an.APPROVAL_TYPES if t in a.approvals.index.get_level_values(0)]
    return {
        "homes": charts.homes_chart(a.homes, a.categories, a.partial, chart_dir / "homes.png", source),
        "approvals": charts.approval_chart(a.approvals, types, NAMES, chart_dir / "approvals.png", source),
        "areas": charts.areas_chart(a.areas, chart_dir / "areas.png", source),
        "closing": charts.closing_chart(a.trend, a.cleanup, chart_dir / "closing.png", source),
    }


def render(a: Analysis) -> str:
    bullets = "\n".join(f"- {f}" for f in findings(a))
    partial_note = f" {max(a.partial)} is a partial year (to {a.end:%b %-d})." if a.partial else ""
    return f"""# Toronto building permits: where new homes are approved, and how long it takes

Building permits issued by the City of Toronto from {period(a)}.{partial_note} Generated with
`python -m permits`. {a.source_note}

## Key findings

{bullets}

## New homes approved each year

Homes are counted when the permit is **issued**, from the permit's "dwelling units created" field.
Permits later cancelled or revoked are left out.

![New homes on permits issued each year](charts/homes.png)

{homes_table(a)}

- **Apartment and mixed-use buildings** are "New Building" permits.
- **Suites, multiplexes and additions** are "Small Residential Projects" and "Building
  Additions/Alterations" permits: second units, laneway and garden suites, multiplexes and extensions.
- **Demolished** counts the existing homes these projects remove.

## Where

Postal areas are the first three characters of a postal code (for example M5V). Canada Post
calls them forward sortation areas.

![Postal areas with the most new homes approved](charts/areas.png)

{areas_table(a)}

{num(a.unknown_area_homes)} homes are on permits with no postal code and aren't in this table. Most are
on large apartment permits, often for sites that don't have a postal code yet, so areas with big
new developments are undercounted. The shares are of all homes approved, including these.

## How long permits take

Days from **application** to **permit issued**, for permits issued each year: the median, then
the 90th percentile in brackets (one permit in ten took longer than this).

![Days from application to permit](charts/approvals.png)

{approvals_table(a)}

Large projects can start early on a separate "conditional" permit, so for new buildings the wait
for the full permit overstates how long work is held up.

## A permit-closing clean-up

![Permits closed each month and their age](charts/closing.png)

{closing_table(a)}

A sustained jump means at least three months in a row with 1.5 times the typical monthly
closings (the median of the first five years).

## How the data was cleaned

{log_table(a)}

## Method and limitations

- **Two files, combined.** The city publishes closed permits and open permits separately. Every
  permit issued since January 2017 is in one or the other, so together they show all permits
  issued, finished or not.
- **Homes are counted at approval, not completion.** Some approved homes will never be built,
  and big projects take years. The completion date isn't used, because of the clean-up above.
- **"Dwelling units created" is filled in from the application.** It's the city's best record,
  but it isn't checked against what was finally built.
- **Approval time runs from the application date to the issue date.** It includes time the
  applicant took to answer the city's comments, not just the city's own review time.
- **No personal data is used.** Street addresses and builder names are never read from the files.
"""


def readme_section(a: Analysis) -> str:
    bullets = "\n".join(f"- {f}" for f in findings(a)[:4])
    return f"""{README_START}
_Permits issued {period(a)}. Full report: [report/REPORT.md](report/REPORT.md)._

{bullets}

![New homes on permits issued each year](report/charts/homes.png)
{README_END}"""


def update_readme(path: Path, section: str) -> bool:
    """Replace the results section between the markers. Returns False if the markers are missing."""
    text = path.read_text()
    start, end = text.find(README_START), text.find(README_END)
    if start == -1 or end == -1:
        return False
    path.write_text(text[:start] + section + text[end + len(README_END) :])
    return True


def write_report(a: Analysis, out_dir: Path) -> Path:
    draw_charts(a, out_dir / "charts")
    path = out_dir / "REPORT.md"
    path.write_text(render(a))
    return path
