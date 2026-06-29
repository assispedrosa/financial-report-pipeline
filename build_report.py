"""
Static PDF renderer — the "old way" artifact, generated automatically.

Takes the engine output, draws a few matplotlib charts, drops them into a clean
HTML template and prints it to PDF with headless Chromium (Playwright). The
point of shipping this alongside the dashboard: prove the pipeline can still
produce the emailable one-pager finance teams expect — for free, from the same
source of truth — while the dashboard is the upgrade.

Run: python build_report.py  ->  data/management_report.pdf
"""

from __future__ import annotations

import base64
import io
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from jinja2 import Template

import report_engine as eng

OUT_PDF = "data/management_report.pdf"
INK = "#1F3864"
ACCENT = "#FF4B4B"
GREY = "#8A94A6"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _chart_revenue_ebitda(pnl) -> str:
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    x = pnl.index
    ax.bar(x, pnl["Revenue"], width=20, color=INK, alpha=0.85, label="Revenue")
    ax.plot(x, pnl["EBITDA"], color=ACCENT, lw=2.2, marker="o", ms=3, label="EBITDA")
    ax.set_ylabel("USD '000")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    return _fig_to_b64(fig)


def _chart_margin(pnl) -> str:
    fig, ax = plt.subplots(figsize=(3.0, 2.2))
    ax.plot(pnl.index, pnl["EBITDA Margin"], color=ACCENT, lw=2.2)
    ax.fill_between(pnl.index, pnl["EBITDA Margin"], color=ACCENT, alpha=0.12)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.set_title("EBITDA margin", fontsize=9, color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    return _fig_to_b64(fig)


def _chart_bu(by_bu) -> str:
    fig, ax = plt.subplots(figsize=(3.0, 2.2))
    order = by_bu.sort_values("Revenue")
    ax.barh(order.index, order["Revenue"], color=INK, alpha=0.85)
    ax.set_title("Revenue by business unit", fontsize=9, color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8)
    return _fig_to_b64(fig)


TEMPLATE = Template(
    """
<!doctype html><html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Arial, sans-serif; color: #222; margin: 0; }
  .page { padding: 28px 34px; }
  .top { display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom: 3px solid {{ ink }}; padding-bottom: 10px; }
  .company { font-size: 20px; font-weight: 700; color: {{ ink }}; }
  .subtitle { font-size: 11px; color: {{ grey }}; }
  .period { font-size: 12px; color: {{ ink }}; font-weight: 600; }
  .kpis { display:flex; gap:10px; margin: 16px 0; }
  .kpi { flex:1; border:1px solid #E6E8EC; border-radius:8px; padding:10px 12px; }
  .kpi .label { font-size:10px; color:{{ grey }}; text-transform:uppercase;
                letter-spacing:.04em; }
  .kpi .value { font-size:19px; font-weight:700; color:{{ ink }}; margin-top:3px; }
  .kpi .delta { font-size:11px; margin-top:2px; }
  .pos { color:#137333; } .neg { color:{{ accent }}; }
  .row { display:flex; gap:14px; margin-top:8px; }
  .card { border:1px solid #E6E8EC; border-radius:8px; padding:10px; }
  .grow { flex:1; }
  img { width:100%; }
  table { width:100%; border-collapse: collapse; font-size:11px; margin-top:6px; }
  th, td { padding:5px 8px; text-align:right; }
  th:first-child, td:first-child { text-align:left; }
  thead th { background:{{ ink }}; color:#fff; font-weight:600; }
  tbody tr:nth-child(even){ background:#F7F8FA; }
  .foot { margin-top:14px; font-size:9px; color:{{ grey }};
          border-top:1px solid #E6E8EC; padding-top:6px; }
</style></head><body><div class="page">

  <div class="top">
    <div>
      <div class="company">{{ company }}</div>
      <div class="subtitle">Monthly Management Report &middot; figures in USD thousands</div>
    </div>
    <div class="period">{{ period }}</div>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="label">Revenue</div>
      <div class="value">{{ revenue }}</div>
      <div class="delta {{ mom_cls }}">{{ mom }} MoM &nbsp; {{ yoy }} YoY</div></div>
    <div class="kpi"><div class="label">EBITDA</div>
      <div class="value">{{ ebitda }}</div>
      <div class="delta">{{ ebitda_margin }} margin</div></div>
    <div class="kpi"><div class="label">Gross margin</div>
      <div class="value">{{ gross_margin }}</div></div>
    <div class="kpi"><div class="label">Revenue vs budget (YTD)</div>
      <div class="value {{ bud_cls }}">{{ vs_budget }}</div></div>
  </div>

  <div class="card"><img src="data:image/png;base64,{{ chart_main }}"></div>

  <div class="row">
    <div class="card grow"><img src="data:image/png;base64,{{ chart_margin }}"></div>
    <div class="card grow"><img src="data:image/png;base64,{{ chart_bu }}"></div>
  </div>

  <table>
    <thead><tr><th>Business unit</th><th>Revenue</th><th>EBITDA</th>
      <th>EBITDA margin</th></tr></thead>
    <tbody>
    {% for r in bu_rows %}
      <tr><td>{{ r.name }}</td><td>{{ r.rev }}</td><td>{{ r.ebitda }}</td>
          <td>{{ r.margin }}</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <div class="foot">Generated automatically from data/raw_pnl.xlsx by the
    reporting pipeline. Figures illustrative (synthetic data).</div>
</div></body></html>
"""
)


def render_html(data: dict) -> str:
    k = data["kpis"]
    by_bu = data["by_bu"]
    bu_rows = [
        dict(
            name=name,
            rev=f"${by_bu.at[name, 'Revenue']:,.0f}k",
            ebitda=f"${by_bu.at[name, 'EBITDA']:,.0f}k",
            margin=f"{by_bu.at[name, 'EBITDA Margin']:.1%}",
        )
        for name in by_bu.index
    ]
    return TEMPLATE.render(
        ink=INK, accent=ACCENT, grey=GREY,
        company=data["company"],
        period=f"{k.month:%B %Y}",
        revenue=f"${k.revenue:,.0f}k",
        ebitda=f"${k.ebitda:,.0f}k",
        ebitda_margin=f"{k.ebitda_margin:.1%}",
        gross_margin=f"{k.gross_margin:.1%}",
        mom=f"{k.rev_mom:+.1%}", yoy=f"{k.rev_yoy:+.1%}",
        mom_cls="pos" if k.rev_mom >= 0 else "neg",
        vs_budget=f"{k.rev_vs_budget:+.1%}",
        bud_cls="pos" if k.rev_vs_budget >= 0 else "neg",
        chart_main=_chart_revenue_ebitda(data["pnl"]),
        chart_margin=_chart_margin(data["pnl"]),
        chart_bu=_chart_bu(data["by_bu"]),
        bu_rows=bu_rows,
    )


def html_to_pdf(html: str, path: str) -> None:
    from playwright.sync_api import sync_playwright

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html, wait_until="networkidle")
        pg.pdf(path=path, format="A4", print_background=True,
               margin=dict(top="0", bottom="0", left="0", right="0"))
        b.close()


def main() -> None:
    data = eng.build_report_data()
    html = render_html(data)
    html_to_pdf(html, OUT_PDF)
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
