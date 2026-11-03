"""Charts for the report. Each function writes one PNG and returns its path."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files, no window

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Okabe-Ito colours: distinguishable with the common forms of colour blindness.
COLOURS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
THOUSANDS = FuncFormatter(lambda v, _: f"{v:,.0f}")


def _style(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.8)
    ax.set_axisbelow(True)


def _save(fig, path: Path, source: str) -> Path:
    fig.text(0.01, 0.01, source, fontsize=8, color="#666666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def homes_chart(table: pd.DataFrame, categories: list[str], partial: dict[int, str], path: Path, source: str) -> Path:
    """Stacked bars of new homes by kind of project. `partial` maps a year to a label like 'Jan–Oct'."""
    fig, ax = plt.subplots(figsize=(10, 5.5))
    labels = [f"{y}\n({partial[y]})" if y in partial else str(y) for y in table.index]
    bottom = pd.Series(0, index=table.index)
    for category, colour in zip(categories, COLOURS, strict=False):
        bars = ax.bar(labels, table[category], bottom=bottom, color=colour, label=category)
        for bar, year in zip(bars, table.index, strict=True):
            if year in partial:
                bar.set_hatch("//")
                bar.set_edgecolor("white")
        bottom = bottom + table[category]
    for i, total in enumerate(bottom):
        ax.text(i, total * 1.01, f"{total:,.0f}", ha="center", fontsize=8)
    ax.yaxis.set_major_formatter(THOUSANDS)
    _style(ax, "New homes on building permits issued each year")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    return _save(fig, path, source)


def approval_chart(table: pd.DataFrame, types: list[str], names: dict[str, str], path: Path, source: str) -> Path:
    """One small chart per permit type: median and 90th percentile days from application to issue."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for ax, permit_type in zip(axes.flat, types, strict=False):
        rows = table.loc[permit_type]
        ax.plot(rows.index, rows["Median days"], color="#0072B2", linewidth=2, marker="o", label="Median")
        ax.plot(
            rows.index,
            rows["90th percentile days"],
            color="#0072B2",
            linewidth=1.2,
            linestyle="--",
            label="90th percentile (1 in 10 took longer)",
        )
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(THOUSANDS)
        ax.set_xticks(rows.index[::2])
        _style(ax, f"{names.get(permit_type, permit_type)}: days to permit")
    axes.flat[0].legend(frameon=False, fontsize=8, loc="upper left")
    return _save(fig, path, source)


def areas_chart(table: pd.DataFrame, path: Path, source: str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    rows = table.iloc[::-1]
    ax.barh(rows.index, rows["Homes"], color="#009E73")
    for i, (homes, share) in enumerate(zip(rows["Homes"], rows["Share of city"], strict=True)):
        ax.text(homes * 1.01, i, f"{homes:,.0f} ({share:.0%})", va="center", fontsize=9)
    ax.xaxis.set_major_formatter(THOUSANDS)
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(
        "Postal areas with the most new homes approved (share of the city)", loc="left", fontsize=12, fontweight="bold"
    )
    return _save(fig, path, source)


def closing_chart(trend: pd.DataFrame, cleanup: pd.Period | None, path: Path, source: str) -> Path:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    x = trend.index.to_timestamp()
    top.bar(x, trend["Closed"], width=25, color="#56B4E9")
    top.yaxis.set_major_formatter(THOUSANDS)
    _style(top, "Permits marked Closed each month")
    bottom.plot(x, trend["Median age (years)"], color="#D55E00", linewidth=2)
    bottom.set_ylim(bottom=0)
    _style(bottom, "Median age of those permits when closed (years since issue)")
    if cleanup is not None:
        for ax in (top, bottom):
            ax.axvline(cleanup.to_timestamp(), color="#222222", linestyle=":", linewidth=1.5)
        top.annotate(
            f"Jump starts {cleanup.strftime('%b %Y')}",
            (cleanup.to_timestamp(), top.get_ylim()[1] * 0.92),
            xytext=(-8, 0),
            textcoords="offset points",
            ha="right",
            fontsize=9,
        )
    return _save(fig, path, source)
