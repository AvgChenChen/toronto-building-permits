import pandas as pd
import pytest

from permits import analysis as an
from permits.clean import CleaningLog, issued_permits

from .helpers import file, permit

END = pd.Timestamp("2026-11-02")


def issued(rows):
    return issued_permits(file(rows, "cleared"), file([], "active"), pd.Timestamp("2017-01-01"), END, CleaningLog())


def test_homes_are_counted_by_issue_year_and_kind_without_cancelled_permits():
    rows = issued(
        [
            permit("A", issued="2020-02-01", permit_type="New Building", units="100", lost="2"),
            permit("B", issued="2020-06-01", units="1", lost="1"),
            permit("C", issued="2021-01-05", permit_type="Small Residential Projects", units="2"),
            permit("D", issued="2021-01-05", permit_type="New Building", units="500", status="Cancelled"),
        ]
    )
    table = an.homes_by_year(rows)
    assert table.loc[2020, "Apartment and mixed-use buildings"] == 100
    assert table.loc[2020, "Total"] == 101 and table.loc[2020, "Net new homes"] == 98
    assert table.loc[2021, "Total"] == 2  # the cancelled 500 aren't counted


def test_areas_are_ranked_and_homes_without_a_postal_code_are_reported_separately():
    rows = issued(
        [
            permit("A", postal="M5V", units="30"),
            permit("B", postal="M4E", units="10"),
            permit("C", postal="", units="10"),
        ]
    )
    table, unknown = an.homes_by_area(rows)
    assert table.index.tolist() == ["M5V", "M4E"]
    assert table.loc["M5V", "Share of city"] == pytest.approx(0.6)
    assert unknown == 10


def test_approval_times_by_type_and_year():
    rows = issued(
        [permit(str(i), applied="2020-01-01", issued=f"2020-01-{d:02d}") for i, d in enumerate([11, 21, 31])]
        + [permit("X", applied="2020-01-01", issued="2020-02-01", permit_type="Plumbing(PS)")]
    )
    table = an.approval_times(rows)
    assert table.loc[("New Houses", 2020), "Median days"] == 20
    assert table.loc[("New Houses", 2020), "Permits"] == 3
    assert "Plumbing(PS)" not in table.index.get_level_values(0)


def test_full_years_leave_out_a_partial_last_year():
    rows = issued([permit("A", issued="2025-05-01"), permit("B", issued="2026-03-01")])
    assert an.full_years(rows, END) == [2025]
    assert an.full_years(rows, pd.Timestamp("2026-12-31")) == [2025, 2026]


def test_cleanup_start_finds_the_first_month_of_a_sustained_jump():
    counts = [100] * 60 + [160, 90, 200, 210, 190, 220]  # a one-month spike, then a run from month 63
    trend = pd.DataFrame({"Closed": counts}, index=pd.period_range("2017-01", periods=len(counts), freq="M"))
    start, baseline = an.cleanup_start(trend)
    assert baseline == 100
    assert str(start) == "2022-03"


def test_no_cleanup_when_closings_stay_normal():
    trend = pd.DataFrame({"Closed": [100] * 70}, index=pd.period_range("2017-01", periods=70, freq="M"))
    assert an.cleanup_start(trend)[0] is None
