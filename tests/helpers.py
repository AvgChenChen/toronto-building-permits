"""Small permit files in the same shape as the city's, with every value as text."""

from __future__ import annotations

import pandas as pd

from permits.sources import COLUMNS


def permit(
    num: str,
    issued: str | None = "2020-03-01",
    applied: str | None = "2020-01-01",
    permit_type: str = "New Houses",
    status: str = "Closed",
    units: str = "1",
    lost: str = "0",
    postal: str = "M4E",
    revision: str = "00",
    completed: str = "",
) -> dict:
    return {
        "PERMIT_NUM": num,
        "REVISION_NUM": revision,
        "PERMIT_TYPE": permit_type,
        "STRUCTURE_TYPE": "",
        "POSTAL": postal,
        "APPLICATION_DATE": applied or "",
        "ISSUED_DATE": issued or "",
        "COMPLETED_DATE": completed,
        "STATUS": status,
        "DWELLING_UNITS_CREATED": units,
        "DWELLING_UNITS_LOST": lost,
    }


def file(rows: list[dict], source: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=COLUMNS).fillna("")
    return frame.assign(SOURCE=source)
