"""ROAS chart: one small panel per ad set, all on the same y-axis.

Each panel shows the 7-day rolling ROAS (revenue / spend over the last 7 days), with dashed
lines at the target ROAS and the break-even ROAS from budget.py. Small panels are easier to
read than six noisy lines on one chart.

Save the README image:  python -m ads_agent.charts
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # draw without a screen (servers, CI)
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ads_agent import DOCS_DIR  # noqa: E402
from ads_agent.budget import BREAK_EVEN_ROAS, TARGET_ROAS  # noqa: E402
from ads_agent.campaign import load_campaign  # noqa: E402

LINE = "#2a78d6"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def rolling_roas(frame: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    """Date x ad set table of ROAS over a rolling window of days."""
    daily = frame.pivot_table(index="date", columns="ad_set_id",
                              values=["spend_aed", "revenue_aed"], aggfunc="sum")
    revenue = daily["revenue_aed"].rolling(window_days).sum()
    spend = daily["spend_aed"].rolling(window_days).sum()
    return (revenue / spend).dropna()


def roas_chart(frame: pd.DataFrame, actions: dict[str, str] | None = None):
    """Return a matplotlib Figure. `actions` maps ad_set_id -> suggested action for titles."""
    roas = rolling_roas(frame)
    # Same order as the actions (best ROAS first) when given, else alphabetical.
    ad_sets = [a for a in actions if a in roas.columns] if actions else list(roas.columns)
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.6), sharex=True, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    top = max(6.0, float(roas.max().max()) * 1.1)

    for ax, ad_set in zip(axes.flat, ad_sets, strict=False):
        ax.set_facecolor(SURFACE)
        ax.plot(roas.index, roas[ad_set], color=LINE, linewidth=2)
        ax.axhline(TARGET_ROAS, color=MUTED, linestyle="--", linewidth=1)
        ax.axhline(BREAK_EVEN_ROAS, color=MUTED, linestyle=":", linewidth=1)
        title = ad_set if not actions else f"{ad_set}  ->  {actions.get(ad_set, '')}"
        ax.set_title(title, fontsize=9, color=TEXT, loc="left")
        ax.set_ylim(0, top)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED, labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
    for ax in axes.flat[len(ad_sets):]:
        ax.set_visible(False)

    for ax in axes[1]:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    axes[0][0].set_ylabel("ROAS (7-day rolling)", color=MUTED, fontsize=9)
    axes[1][0].set_ylabel("ROAS (7-day rolling)", color=MUTED, fontsize=9)
    fig.suptitle(
        f"Synthetic campaign: 7-day rolling ROAS per ad set   "
        f"(dashed = target {TARGET_ROAS}, dotted = break-even {BREAK_EVEN_ROAS})",
        fontsize=10, color=TEXT, x=0.01, ha="left",
    )
    fig.tight_layout()
    return fig


def main() -> None:
    from ads_agent.analyst import analyse

    frame = load_campaign()
    actions = analyse(frame)["suggestions"].set_index("ad_set_id")["action"].to_dict()
    out = DOCS_DIR / "campaign_roas.png"
    roas_chart(frame, actions).savefig(out, dpi=120, facecolor=SURFACE)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
