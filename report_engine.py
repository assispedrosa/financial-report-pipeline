"""
Reporting engine: the single source of truth.

Reads the messy human-formatted workbook, tidies it into a clean long table,
and derives the P&L (gross profit, OpEx, EBITDA, margins), growth metrics and
budget variance. Both outputs — the static PDF (build_report.py) and the
interactive dashboard (app.py) — consume *this* module, so the two can never
disagree. That "one engine, two renderers" idea is the whole pitch.

Framework-free (pandas only) and scenario-light: swapping the raw workbook for
a different report (e.g. sales) mostly means adjusting ACCOUNT roles below.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

RAW_PATH = "data/raw_pnl.xlsx"

# Account roles — the only domain knowledge the engine needs. Change these to
# re-point the pipeline at a different P&L structure.
REVENUE = "Revenue"
COGS = "COGS"
OPEX_ACCOUNTS = ["Sales & Marketing", "G&A", "R&D"]


# --- Load + tidy ----------------------------------------------------------

def load_actuals(path: str = RAW_PATH) -> pd.DataFrame:
    """
    Parse the 'P&L' sheet into tidy long form:
    columns = [date, business_unit, account, value].

    Handles the manual layout: a 3-row banner, business-unit names that appear
    only on their first line, blank spacer rows, and months pivoted across
    columns as 'Jan/24' labels.
    """
    raw = pd.read_excel(path, sheet_name="P&L", header=3)
    raw = raw.rename(columns={"Business Unit": "business_unit", "Account": "account"})

    # Business unit only on the first row of each block -> forward fill.
    raw["business_unit"] = raw["business_unit"].ffill()
    # Drop spacer rows (no account).
    raw = raw[raw["account"].notna()].copy()

    month_cols = [c for c in raw.columns if c not in ("business_unit", "account")]
    long = raw.melt(
        id_vars=["business_unit", "account"],
        value_vars=month_cols,
        var_name="month_label",
        value_name="value",
    )
    long["date"] = pd.to_datetime(long["month_label"], format="%b/%y")
    long["value"] = pd.to_numeric(long["value"], errors="coerce").fillna(0.0)
    return long[["date", "business_unit", "account", "value"]].sort_values("date")


def load_budget(path: str = RAW_PATH) -> pd.DataFrame:
    """Annual budget per business unit / account."""
    bud = pd.read_excel(path, sheet_name="Budget FY", header=2)
    bud = bud.rename(
        columns={
            "Business Unit": "business_unit",
            "Account": "account",
            "Full-Year Budget": "budget",
        }
    )
    return bud[["business_unit", "account", "budget"]]


# --- Derive the P&L -------------------------------------------------------

def pnl_by_month(actuals: pd.DataFrame) -> pd.DataFrame:
    """
    Wide P&L per date (company total): Revenue, COGS, Gross Profit, OpEx,
    EBITDA and the margins. One row per month.
    """
    g = actuals.pivot_table(
        index="date", columns="account", values="value", aggfunc="sum"
    ).fillna(0.0)
    out = pd.DataFrame(index=g.index)
    out["Revenue"] = g.get(REVENUE, 0.0)
    out["COGS"] = g.get(COGS, 0.0)
    out["Gross Profit"] = out["Revenue"] - out["COGS"]
    out["OpEx"] = g[[a for a in OPEX_ACCOUNTS if a in g.columns]].sum(axis=1)
    out["EBITDA"] = out["Gross Profit"] - out["OpEx"]
    out["Gross Margin"] = out["Gross Profit"] / out["Revenue"]
    out["EBITDA Margin"] = out["EBITDA"] / out["Revenue"]
    return out


def pnl_by_bu(actuals: pd.DataFrame, month: pd.Timestamp | None = None) -> pd.DataFrame:
    """P&L per business unit, for a given month (default: latest)."""
    if month is None:
        month = actuals["date"].max()
    sub = actuals[actuals["date"] == month]
    g = sub.pivot_table(
        index="business_unit", columns="account", values="value", aggfunc="sum"
    ).fillna(0.0)
    out = pd.DataFrame(index=g.index)
    out["Revenue"] = g.get(REVENUE, 0.0)
    out["EBITDA"] = (
        g.get(REVENUE, 0.0)
        - g.get(COGS, 0.0)
        - g[[a for a in OPEX_ACCOUNTS if a in g.columns]].sum(axis=1)
    )
    out["EBITDA Margin"] = out["EBITDA"] / out["Revenue"]
    return out.sort_values("Revenue", ascending=False)


@dataclass
class KPIs:
    month: pd.Timestamp
    revenue: float
    ebitda: float
    gross_margin: float
    ebitda_margin: float
    rev_mom: float          # month-over-month revenue growth
    rev_yoy: float          # year-over-year revenue growth
    ytd_revenue: float
    ytd_ebitda: float
    rev_vs_budget: float    # YTD actual revenue vs prorated budget (fraction)


def compute_kpis(pnl: pd.DataFrame, budget: pd.DataFrame) -> KPIs:
    month = pnl.index.max()
    row = pnl.loc[month]
    rev = float(row["Revenue"])

    rev_mom = _growth(pnl["Revenue"], periods=1)
    rev_yoy = _growth(pnl["Revenue"], periods=12)

    ytd_mask = pnl.index.year == month.year
    ytd = pnl[ytd_mask]
    n_ytd = len(ytd)

    rev_budget_year = float(budget.loc[budget["account"] == REVENUE, "budget"].sum())
    prorated = rev_budget_year * n_ytd / 12.0
    rev_vs_budget = float(ytd["Revenue"].sum() / prorated - 1.0) if prorated else np.nan

    return KPIs(
        month=month,
        revenue=rev,
        ebitda=float(row["EBITDA"]),
        gross_margin=float(row["Gross Margin"]),
        ebitda_margin=float(row["EBITDA Margin"]),
        rev_mom=rev_mom,
        rev_yoy=rev_yoy,
        ytd_revenue=float(ytd["Revenue"].sum()),
        ytd_ebitda=float(ytd["EBITDA"].sum()),
        rev_vs_budget=rev_vs_budget,
    )


def _growth(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return float("nan")
    prev, cur = series.iloc[-periods - 1], series.iloc[-1]
    return float(cur / prev - 1.0) if prev else float("nan")


def build_report_data(path: str = RAW_PATH) -> dict:
    """Everything the renderers need, computed once."""
    actuals = load_actuals(path)
    budget = load_budget(path)
    pnl = pnl_by_month(actuals)
    return {
        "actuals": actuals,
        "budget": budget,
        "pnl": pnl,
        "by_bu": pnl_by_bu(actuals),
        "kpis": compute_kpis(pnl, budget),
        "company": "Meridian Industries Inc.",
    }


if __name__ == "__main__":
    data = build_report_data()
    k = data["kpis"]
    print(f"Company: {data['company']}")
    print(f"Latest month: {k.month:%b/%Y}")
    print(f"Revenue: {k.revenue:,.0f}  EBITDA: {k.ebitda:,.0f}  "
          f"EBITDA margin: {k.ebitda_margin:.1%}")
    print(f"Rev MoM: {k.rev_mom:+.1%}  YoY: {k.rev_yoy:+.1%}  "
          f"vs budget (YTD): {k.rev_vs_budget:+.1%}")
    print("\nBy business unit (latest month):")
    print(data["by_bu"].to_string())
