import pandas as pd

from permits.clean import CleaningLog, closed_permits, issued_permits

from .helpers import file, permit

START, END = pd.Timestamp("2017-01-01"), pd.Timestamp("2026-11-02")


def issued(cleared_rows, active_rows=()):
    log = CleaningLog()
    rows = issued_permits(file(cleared_rows, "cleared"), file(list(active_rows), "active"), START, END, log)
    return rows, dict(log.steps)


def test_revisions_are_dropped_because_they_repeat_the_original():
    rows, log = issued([permit("A"), permit("A", revision="01", units="0")])
    assert rows["PERMIT_NUM"].tolist() == ["A"]
    assert log["Dropped: revisions to an earlier permit (they repeat its details)"] == 1


def test_a_permit_in_both_files_is_counted_once_using_the_cleared_copy():
    rows, _ = issued([permit("A", status="Closed")], [permit("A", status="Inspection")])
    assert len(rows) == 1
    assert rows.loc[0, "STATUS"] == "Closed"


def test_a_conditional_permit_and_the_full_permit_are_different_permits():
    rows, _ = issued([permit("A", permit_type="Conditional Permit", units=""), permit("A", permit_type="New Building")])
    assert sorted(rows["PERMIT_TYPE"]) == ["Conditional Permit", "New Building"]


def test_permits_not_yet_issued_or_outside_the_period_are_dropped():
    rows, log = issued([permit("A", issued=None), permit("B", issued="2016-12-31"), permit("C")])
    assert rows["PERMIT_NUM"].tolist() == ["C"]
    assert log["Dropped: not issued (still under review, refused before issue, or no date)"] == 1


def test_approval_time_is_days_from_application_to_issue():
    rows, _ = issued([permit("A", applied="2020-01-01", issued="2020-03-01")])
    assert rows.loc[0, "WAIT_DAYS"] == 60


def test_an_impossible_approval_time_is_blank_but_the_permit_is_kept():
    rows, log = issued([permit("A", applied="2020-05-01", issued="2020-03-01"), permit("B", applied=None)])
    assert len(rows) == 2 and rows["WAIT_DAYS"].isna().all()
    assert log["Kept, but no approval time: application date missing or after the issue date"] == 2


def test_numbers_with_commas_are_read_and_blanks_are_zero():
    rows, _ = issued([permit("A", units="1,250", lost="")])
    assert rows.loc[0, "UNITS_CREATED"] == 1250 and rows.loc[0, "UNITS_LOST"] == 0


def test_cancelled_permits_are_flagged_and_categories_assigned():
    rows, _ = issued(
        [
            permit("A", status="Cancelled"),
            permit("B", permit_type="Small Residential Projects"),
            permit("C", permit_type="Plumbing(PS)"),
        ]
    )
    assert rows["ENDED"].tolist() == [True, False, False]
    assert rows["CATEGORY"].tolist() == ["New houses", "Suites, multiplexes and additions", "Other permit types"]


def test_closed_permits_skip_other_statuses_and_dates_in_the_future():
    log = CleaningLog()
    cleared = file(
        [
            permit("A", issued="2020-01-01", completed="2022-01-01"),
            permit("B", status="Cancelled", completed="2022-01-01"),
            permit("C", completed="2028-11-03"),
        ],
        "cleared",
    )
    rows = closed_permits(cleared, END, log)
    assert rows["PERMIT_NUM"].tolist() == ["A"]
    assert round(rows.loc[0, "AGE_YEARS"], 2) == 2.0
    assert dict(log.steps)["Dropped from the closing analysis: closed date after Nov 2, 2026"] == 1
