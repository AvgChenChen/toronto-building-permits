import re

import pandas as pd
import pytest

from permits import report

from .helpers import file, permit

START, END = pd.Timestamp("2017-01-01"), pd.Timestamp("2026-11-02")


@pytest.fixture
def analysis():
    cleared, active = [], []
    n = 0
    for year in range(2017, 2027):
        for month in range(1, 13):
            if pd.Timestamp(year, month, 1) > END:
                break
            # Normal closings, then twice as many from June 2025, and those are much older.
            closings = 4 if pd.Timestamp(year, month, 1) >= pd.Timestamp("2025-06-01") else 2
            for _ in range(closings):
                n += 1
                old = closings == 4
                cleared.append(
                    permit(
                        f"C{n}",
                        applied=f"{year - (6 if old else 1)}-01-01",
                        issued=f"{year - (5 if old else 1)}-01-01",
                        completed=f"{year}-{month:02d}-15",
                        units="0",
                    )
                )
        cleared.append(
            permit(
                f"B{year}",
                issued=f"{year}-04-01",
                applied=f"{year - 1}-10-01",
                permit_type="New Building",
                units=str(100 + 10 * (year - 2017)),
                postal="M5V",
            )
        )
        cleared.append(permit(f"H{year}", issued=f"{year}-05-01", applied=f"{year}-02-01", units="1", postal="M4E"))
        cleared.append(
            permit(
                f"S{year}",
                issued=f"{year}-06-01",
                permit_type="Small Residential Projects",
                units=str(1 + (year - 2017)),
                postal="M6H",
            )
        )
    active.append(permit("B2017", status="Inspection", permit_type="New Building", units="999"))  # duplicate
    return report.analyse(file(cleared, "cleared"), file(active, "active"), START, END, "Test data.")


def test_the_duplicate_in_the_active_file_is_not_counted(analysis):
    assert analysis.homes.loc[2017, "Apartment and mixed-use buildings"] == 100


def test_findings_are_calculated_from_the_data(analysis):
    text = "\n".join(report.findings(analysis))
    assert "2025 was the busiest year" in text  # 2026 is partial, so it can't be the busiest
    assert "M5V had the most new homes approved" in text
    assert "From June 2025, the city closed far more permits than usual" in text
    assert "Small-scale housing grew" in text and "9.0 times" in text


def test_the_partial_year_is_labelled(analysis):
    assert analysis.partial == {2026: "to Nov 2"}
    assert "2026 (to Nov 2)" in report.homes_table(analysis)


def test_the_closing_trend_leaves_out_the_month_that_has_just_started(analysis):
    assert str(analysis.trend.index[-1]) == "2026-10"


def test_report_and_charts_are_written(tmp_path, analysis):
    path = report.write_report(analysis, tmp_path)
    text = path.read_text()
    assert "## Key findings" in text and "## How the data was cleaned" in text
    assert not re.search(r"\bnan\b", text, re.IGNORECASE)
    for name in ["homes", "approvals", "areas", "closing"]:
        assert (tmp_path / "charts" / f"{name}.png").stat().st_size > 10_000


def test_readme_section_is_replaced_between_markers(tmp_path, analysis):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Title\n\n{report.README_START}\nold\n{report.README_END}\n\n## After\n")
    assert report.update_readme(readme, report.readme_section(analysis))
    text = readme.read_text()
    assert "old" not in text and "## After" in text


def test_homes_without_a_postal_code_are_called_out(analysis):
    analysis.issued.loc[analysis.issued["PERMIT_NUM"] == "B2020", "POSTAL"] = ""
    analysis.unknown_area_homes = 130
    text = "\n".join(report.findings(analysis))
    assert "have no postal code" in text and "on 1 permit for 100 or more homes" in text
