from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from calendars.daycounts import DayCounts
from scripts.build_econometrics_panel import filter_government_universe
from src.config import CONFIG
from src.core.spread_calculator import geometric_spread_bps_from_pct
from src.finmath.termstructure.curve_models import (
    CurveBootstrap,
    flat_forward_interpolation,
)
from src.utils.file_io import (
    load_di_surface,
    load_govt_bond_data,
    load_yield_surface,
)
from src.utils.interpolation import interpolate_raw_di_yield_for_tenor


HTML_OUT = Path("templates/brl_risk_spread_surface.html")
SUMMARY_OUT = Path("templates/brl_risk_summary.html")

SOV_INPUTS_OUT = Path(
    "templates/brl_risk_sovereign_inputs.html"
)

SOV_ZERO_OUT = Path(
    "templates/brl_risk_sovereign_zero.html"
)

XLSX_OUT = Path(
    "data/brl_sovereign_spread_surface_with_provenance.xlsx"
)

PANEL_PATH = Path(
    "datos_y_modelos/db/econometrics_db/"
    "panel_main_and_robustness_rebuilt_v4.xlsx"
)

PUBLIC_TENORS = {
    "6 meses": 0.5,
    "1 año": 1.0,
    "2 años": 2.0,
    "3 años": 3.0,
    "4 años": 4.0,
    "5 años": 5.0,
    "7 años": 7.0,
    "10 años": 10.0,
}


def load_final_panel_dates():
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"Final econometric panel not found: {PANEL_PATH}"
        )

    panel_dates = pd.read_excel(
        PANEL_PATH,
        sheet_name="ts",
        usecols=["obs_date"],
    )

    panel_dates["obs_date"] = pd.to_datetime(
        panel_dates["obs_date"],
        errors="raise",
    ).dt.normalize()

    dates = pd.DatetimeIndex(
        panel_dates["obs_date"]
        .dropna()
        .unique()
    ).sort_values()

    if len(dates) == 0:
        raise ValueError("No observation dates found in final panel.")

    return dates


def load_nominal_sovereign_inputs():
    govt = load_govt_bond_data(
        CONFIG["GOVT_PATH"]
    ).copy()

    yas = load_yield_surface(
        CONFIG["GOVT_YA_PATH"]
    ).copy()

    yas.index = pd.to_datetime(
        yas.index,
        errors="raise",
    ).normalize()

    if yas.index.duplicated().any():
        raise AssertionError(
            "Duplicate observation dates in sovereign YAS surface."
        )

    for column in ["ISSUE_DT", "MATURITY"]:
        govt[column] = pd.to_datetime(
            govt[column],
            errors="coerce",
        )

    eligible_ids = set(yas.columns)

    govt = govt[
        govt["id"].isin(eligible_ids)
    ].copy()

    ltn = filter_government_universe(
        govt.copy(),
        inflation_linked="N",
        bond_type="LTN",
    ).copy()

    ntnf = filter_government_universe(
        govt.copy(),
        inflation_linked="N",
        bond_type="NTNF",
    ).copy()

    ltn["TYPE"] = "LTN"
    ntnf["TYPE"] = "NTNF"

    nominal = pd.concat(
        [ltn, ntnf],
        ignore_index=True,
    )

    required = {
        "id",
        "TYPE",
        "ISSUE_DT",
        "MATURITY",
        "CPN",
        "CPN_FREQ",
    }

    missing = required.difference(
        nominal.columns
    )

    if missing:
        raise AssertionError(
            "Missing sovereign metadata fields: "
            f"{sorted(missing)}"
        )

    nominal = nominal[
        nominal["ISSUE_DT"].notna()
        & nominal["MATURITY"].notna()
    ].copy()

    nominal = nominal.sort_values(
        ["MATURITY", "TYPE", "id"]
    ).reset_index(drop=True)

    return nominal, yas


def build_sovereign_zero_curve(
    obs_date,
    nominal,
    yas,
    dc,
):
    obs_date = pd.Timestamp(
        obs_date
    ).normalize()

    if obs_date not in yas.index:
        return None, None

    active = nominal[
        (nominal["ISSUE_DT"] <= obs_date)
        & (nominal["MATURITY"] > obs_date)
    ].copy()

    candidates = []

    for _, bond in active.iterrows():
        bond_id = bond["id"]

        if bond_id not in yas.columns:
            continue

        ytm_pct = pd.to_numeric(
            yas.at[obs_date, bond_id],
            errors="coerce",
        )

        if pd.isna(ytm_pct) or float(ytm_pct) == 0.0:
            continue

        candidates.append(
            (
                bond,
                float(ytm_pct) / 100.0,
            )
        )

    ltn_tenors = set()

    for bond, _ in candidates:
        if bond["TYPE"] != "LTN":
            continue

        payment_date = dc.following(
            bond["MATURITY"].date()
        )

        ltn_tenors.add(
            dc.tf(
                obs_date.date(),
                payment_date,
            )
        )

    cash_flows = []
    rates = []

    used_ltn = 0
    used_ntnf = 0
    kept_single_cf_ntnf = 0
    dropped_single_cf_ntnf = 0

    for bond, ytm_dec in candidates:
        if bond["TYPE"] == "LTN":
            payment_date = dc.following(
                bond["MATURITY"].date()
            )

            cf = pd.Series(
                [100.0],
                index=[payment_date],
                dtype=float,
            )

            used_ltn += 1

        else:
            coupon_pct = pd.to_numeric(
                bond["CPN"],
                errors="coerce",
            )

            frequency = pd.to_numeric(
                bond["CPN_FREQ"],
                errors="coerce",
            )

            if pd.isna(coupon_pct) or pd.isna(frequency):
                raise AssertionError(
                    "Missing NTN-F coupon metadata for "
                    f"{bond['id']}."
                )

            frequency = int(frequency)

            if frequency != 2:
                raise AssertionError(
                    "Unexpected NTN-F coupon frequency "
                    f"{frequency} for {bond['id']}."
                )

            coupon_cash_flow = (
                (
                    1.0
                    + float(coupon_pct) / 100.0
                )
                ** (1.0 / frequency)
                - 1.0
            ) * 100.0

            expiry = bond["MATURITY"].date()

            payment_dates = [
                dc.following(expiry)
            ]

            payment_date = dc.workday(
                dc.eom(
                    dc.following(expiry),
                    offset=-7,
                ),
                1,
            )

            while payment_date > dc.following(
                obs_date.date()
            ):
                payment_dates.append(
                    payment_date
                )

                payment_date = dc.workday(
                    dc.eom(
                        payment_date,
                        offset=-7,
                    ),
                    1,
                )

            payment_dates = sorted(
                payment_dates
            )

            cf = pd.Series(
                coupon_cash_flow,
                index=payment_dates,
                dtype=float,
            )

            cf.iloc[-1] += 100.0

            if len(cf) == 1:
                tenor = dc.tf(
                    obs_date.date(),
                    max(cf.index),
                )

                if tenor in ltn_tenors:
                    dropped_single_cf_ntnf += 1
                    continue

                kept_single_cf_ntnf += 1

            used_ntnf += 1

        cash_flows.append(cf)
        rates.append(ytm_dec)

    if not cash_flows:
        return None, None

    if used_ltn == 0:
        raise AssertionError(
            "No valid LTN anchor on sovereign curve date "
            f"{obs_date.date()}."
        )

    bootstrap = CurveBootstrap(
        cash_flows=cash_flows,
        rates=rates,
        day_count_convention="bus/252",
        calendar="cdr_anbima",
        ref_date=obs_date.date(),
    )

    zero_curve = (
        bootstrap.zero_curve
        .dropna()
        .astype(float)
        .sort_index()
    )

    duplicate_tenors = zero_curve.index[
        zero_curve.index.duplicated()
    ].tolist()

    if duplicate_tenors:
        raise AssertionError(
            "Duplicate sovereign zero-curve tenors on "
            f"{obs_date.date()}: {duplicate_tenors}"
        )

    stats = {
        "raw_inputs": len(candidates),
        "used_inputs": len(cash_flows),
        "used_ltn": used_ltn,
        "used_ntnf": used_ntnf,
        "zero_nodes": len(zero_curve),
        "single_cf_ntnf_kept": kept_single_cf_ntnf,
        "single_cf_ntnf_dropped": dropped_single_cf_ntnf,
    }

    return zero_curve, stats


def exact_node_status(
    tenors,
    target_tenor,
):
    tenors = np.asarray(
        tenors,
        dtype=float,
    )

    if tenors.size == 0:
        return False

    return bool(
        np.any(
            np.isclose(
                tenors,
                float(target_tenor),
                rtol=0.0,
                atol=1e-12,
            )
        )
    )


def build_dashboard_data():
    panel_dates = load_final_panel_dates()

    nominal, yas = (
        load_nominal_sovereign_inputs()
    )

    di_surface = load_di_surface(
        CONFIG["HIST_CURVE_PATH"]
    ).copy()

    di_surface["obs_date"] = pd.to_datetime(
        di_surface["obs_date"],
        errors="raise",
    ).dt.normalize()

    di_surface["tenor"] = pd.to_numeric(
        di_surface["tenor"],
        errors="coerce",
    )

    di_surface["yield"] = pd.to_numeric(
        di_surface["yield"],
        errors="coerce",
    )

    di_surface = di_surface.dropna(
        subset=[
            "obs_date",
            "tenor",
            "yield",
        ]
    )

    dc = DayCounts(
        "bus/252",
        calendar="cdr_anbima",
    )

    tenor_items = list(
        PUBLIC_TENORS.items()
    )

    tenor_values = [
        float(value)
        for _, value in tenor_items
    ]

    spread = pd.DataFrame(
        index=panel_dates,
        columns=tenor_values,
        dtype=float,
    )

    sovereign_yield = pd.DataFrame(
        index=panel_dates,
        columns=tenor_values,
        dtype=float,
    )

    di_yield = pd.DataFrame(
        index=panel_dates,
        columns=tenor_values,
        dtype=float,
    )

    provenance = pd.DataFrame(
        index=panel_dates,
        columns=tenor_values,
        dtype=object,
    )

    support_rows = []

    for obs_date in panel_dates:
        obs_date = pd.Timestamp(
            obs_date
        ).normalize()

        zero_curve, stats = (
            build_sovereign_zero_curve(
                obs_date=obs_date,
                nominal=nominal,
                yas=yas,
                dc=dc,
            )
        )

        di_grp = di_surface[
            di_surface["obs_date"].eq(
                obs_date
            )
        ].copy()

        if zero_curve is None or zero_curve.empty:
            for target in tenor_values:
                provenance.loc[
                    obs_date,
                    target,
                ] = "Sin curva soberana en la fecha"

            continue

        if di_grp.empty:
            for target in tenor_values:
                provenance.loc[
                    obs_date,
                    target,
                ] = "Sin curva DI en la fecha"

            continue

        sov_min = float(
            zero_curve.index.min()
        )

        sov_max = float(
            zero_curve.index.max()
        )

        di_min = float(
            di_grp["tenor"].min()
        )

        di_max = float(
            di_grp["tenor"].max()
        )

        support_rows.append(
            {
                "obs_date": obs_date,
                "sovereign_min_tenor": sov_min,
                "sovereign_max_tenor": sov_max,
                "sovereign_zero_nodes": len(
                    zero_curve
                ),
                "sovereign_raw_inputs": stats[
                    "raw_inputs"
                ],
                "sovereign_used_inputs": stats[
                    "used_inputs"
                ],
                "used_ltn": stats[
                    "used_ltn"
                ],
                "used_ntnf": stats[
                    "used_ntnf"
                ],
                "single_cf_ntnf_kept": stats[
                    "single_cf_ntnf_kept"
                ],
                "single_cf_ntnf_dropped": stats[
                    "single_cf_ntnf_dropped"
                ],
                "di_min_tenor": di_min,
                "di_max_tenor": di_max,
                "di_nodes": len(di_grp),
            }
        )

        sov_nodes = zero_curve.index.to_numpy(
            dtype=float
        )

        di_nodes = di_grp[
            "tenor"
        ].to_numpy(dtype=float)

        for target in tenor_values:
            target = float(target)

            sovereign_supported = (
                sov_min
                <= target
                <= sov_max
            )

            di_supported = (
                di_min
                <= target
                <= di_max
            )

            sovereign_zero_pct = np.nan
            di_zero_pct = np.nan

            sovereign_method = None
            di_method = None

            # --------------------------------------------
            # Sovereign zero leg
            # --------------------------------------------
            if sovereign_supported:
                if exact_node_status(
                    sov_nodes,
                    target,
                ):
                    nearest_pos = int(
                        np.argmin(
                            np.abs(
                                sov_nodes - target
                            )
                        )
                    )

                    sovereign_zero_dec = float(
                        zero_curve.iloc[
                            nearest_pos
                        ]
                    )

                    sovereign_method = (
                        "nodo zero soberano"
                    )

                else:
                    sovereign_zero_dec = float(
                        flat_forward_interpolation(
                            target,
                            zero_curve,
                        )
                    )

                    sovereign_method = (
                        "soberano interpolado"
                    )

                sovereign_zero_pct = (
                    sovereign_zero_dec * 100.0
                )

                sovereign_yield.loc[
                    obs_date,
                    target,
                ] = sovereign_zero_pct

            # --------------------------------------------
            # DI zero leg
            # --------------------------------------------
            if di_supported:
                di_zero_pct = (
                    interpolate_raw_di_yield_for_tenor(
                        surface=di_surface,
                        obs_date=obs_date,
                        target_tenor=target,
                    )
                )

                if pd.isna(di_zero_pct):
                    di_supported = False

                else:
                    di_method = (
                        "nodo DI"
                        if exact_node_status(
                            di_nodes,
                            target,
                        )
                        else "DI interpolado"
                    )

                    di_yield.loc[
                        obs_date,
                        target,
                    ] = di_zero_pct

            # --------------------------------------------
            # Spread requires simultaneous support
            # --------------------------------------------
            if not (
                sovereign_supported
                and di_supported
            ):
                missing_legs = []

                if not sovereign_supported:
                    missing_legs.append(
                        "soberano"
                    )

                if not di_supported:
                    missing_legs.append(
                        "DI"
                    )

                provenance.loc[
                    obs_date,
                    target,
                ] = (
                    "Fuera del soporte observado: "
                    + " + ".join(missing_legs)
                )

                continue

            spread_bps = (
                geometric_spread_bps_from_pct(
                    corporate_yield_pct=(
                        sovereign_zero_pct
                    ),
                    benchmark_yield_pct=(
                        di_zero_pct
                    ),
                )
            )

            spread.loc[
                obs_date,
                target,
            ] = spread_bps

            provenance.loc[
                obs_date,
                target,
            ] = (
                f"{sovereign_method}; "
                f"{di_method}"
            )

    support = pd.DataFrame(
        support_rows
    ).sort_values("obs_date")

    return (
        spread,
        sovereign_yield,
        di_yield,
        provenance,
        support,
    )


def build_methodology_sheet():
    rows = [
        (
            "Nombre público",
            "Spread soberano BRL por tenor",
        ),
        (
            "Interpretación",
            (
                "Medida de riesgo soberano en moneda local. "
                "No es un CDS contractual."
            ),
        ),
        (
            "Curva soberana",
            (
                "Curva nominal zero-cupón construida mediante "
                "bootstrap BUS/252 de LTN y NTN-F."
            ),
        ),
        (
            "LTN",
            (
                "Anclas zero-cupón directas."
            ),
        ),
        (
            "NTN-F",
            (
                "Bonos de cupón fijo utilizados mediante "
                "cash-flow stripping."
            ),
        ),
        (
            "Curva benchmark",
            (
                "Curva DI zero-cupón seleccionada por fecha: "
                "DI-over cash, futuros DI líquidos y swaps "
                "Pre x DI más allá del último futuro válido."
            ),
        ),
        (
            "Interpolación",
            (
                "Flat-forward ANBIMA dentro del soporte "
                "observado de cada curva."
            ),
        ),
        (
            "Regla pública de soporte",
            (
                "No se extrapola fuera del rango observado "
                "conjunto de las curvas soberana y DI. "
                "Las celdas sin soporte conjunto quedan vacías."
            ),
        ),
        (
            "Spread",
            (
                "[(1 + y_soberano)/(1 + y_DI) - 1] x 10.000, "
                "expresado en puntos básicos."
            ),
        ),
        (
            "Tenores públicos",
            (
                "0,5; 1; 2; 3; 4; 5; 7 y 10 años."
            ),
        ),
        (
            "Fuente soberana",
            str(CONFIG["GOVT_PATH"]),
        ),
        (
            "Fuente YTM soberana",
            str(CONFIG["GOVT_YA_PATH"]),
        ),
        (
            "Fuente DI",
            str(CONFIG["HIST_CURVE_PATH"]),
        ),
        (
            "Fechas",
            (
                "Fechas de observación del panel econométrico "
                "final panel_main_and_robustness_rebuilt_v4.xlsx."
            ),
        ),
    ]

    return pd.DataFrame(
        rows,
        columns=[
            "campo",
            "descripcion",
        ],
    )


def build_surface_html(
    spread,
    provenance,
):
    tenor_values = list(
        spread.columns
    )

    fig = go.Figure(
        data=[
            go.Surface(
                x=tenor_values,
                y=spread.index,
                z=spread.to_numpy(
                    dtype=float
                ),
                colorscale="RdBu_r",
                colorbar=dict(
                    title="Spread (pb)",
                    len=0.72,
                ),
                hovertemplate=(
                    "Plazo: %{x:g} años"
                    "<br>Fecha: %{y|%Y-%m-%d}"
                    "<br>Spread: %{z:.2f} pb"
                    "<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        title=dict(
            text=(
                "Spread soberano BRL por tenor "
                "— curva soberana zero vs. DI zero"
            ),
            x=0.5,
            font=dict(size=22),
        ),
        scene=dict(
            xaxis=dict(
                title="Plazo (años)"
            ),
            yaxis=dict(
                title="Fecha"
            ),
            zaxis=dict(
                title="Spread (pb)"
            ),
            camera=dict(
                eye=dict(
                    x=1.55,
                    y=-1.75,
                    z=1.05,
                )
            ),
            aspectratio=dict(
                x=1.15,
                y=1.85,
                z=0.85,
            ),
            domain=dict(
                x=[0.02, 0.90],
                y=[0.02, 0.92],
            ),
        ),
        height=820,
        margin=dict(
            l=20,
            r=100,
            b=20,
            t=75,
        ),
        paper_bgcolor="white",
    )

    chart_html = pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn",
        config={
            "responsive": True,
            "displaylogo": False,
        },
    )

    coverage = (
        spread.notna()
        .sum()
        .rename("fechas_con_dato")
        .to_frame()
    )

    coverage["total_fechas"] = len(
        spread
    )

    coverage["cobertura_pct"] = (
        coverage["fechas_con_dato"]
        / coverage["total_fechas"]
        * 100.0
    )

    coverage_rows = []

    for tenor, row in coverage.iterrows():
        coverage_rows.append(
            "<tr>"
            f"<td>{float(tenor):g} años</td>"
            f"<td>{int(row['fechas_con_dato'])}</td>"
            f"<td>{int(row['total_fechas'])}</td>"
            f"<td>{float(row['cobertura_pct']):.1f}%</td>"
            "</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Spread soberano BRL por tenor</title>

  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f4f6f8;
      color: #172033;
      font-family: Arial, Helvetica, sans-serif;
    }}

    .page {{
      max-width: 1600px;
      margin: 0 auto;
    }}

    .panel {{
      background: white;
      border: 1px solid #d9e0e7;
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 20px;
      box-shadow: 0 2px 10px rgba(16,24,40,.06);
    }}

    h2 {{
      margin: 0 0 8px;
    }}

    p {{
      color: #667085;
      line-height: 1.5;
    }}

    .method-note {{
      border-left: 4px solid #0b4f8a;
      padding: 10px 12px;
      background: #eef5fa;
      color: #344054;
      border-radius: 6px;
    }}

    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
    }}

    th,
    td {{
      padding: 8px 10px;
      border: 1px solid #e4e7ec;
      text-align: center;
    }}

    th {{
      background: #101828;
      color: white;
    }}
  </style>
</head>

<body>
<div class="page">

  <div class="panel">
    {chart_html}
  </div>

  <div class="panel">
    <h2>Metodología y cobertura</h2>

    <p class="method-note">
      La medida representa el spread soberano BRL por tenor.
      No es un CDS contractual. Para cada fecha se construye una curva soberana nominal
      zero-cupón mediante bootstrap BUS/252 de LTN y NTN-F. Esa curva se
      compara con la curva DI zero-cupón al mismo tenor. El spread se calcula
      geométricamente como
      [(1 + y<sub>soberano</sub>) / (1 + y<sub>DI</sub>) - 1] × 10.000
      y se expresa en puntos básicos.
    </p>

    <p>
      La superficie pública no extrapola fuera del rango observado conjunto
      de ambas curvas. Por eso algunos plazos largos aparecen únicamente en
      parte de la muestra. Las celdas sin soporte simultáneo quedan vacías.
    </p>

    <table>
      <thead>
        <tr>
          <th>Plazo</th>
          <th>Fechas con dato</th>
          <th>Total de fechas</th>
          <th>Cobertura</th>
        </tr>
      </thead>
      <tbody>
        {''.join(coverage_rows)}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>
"""

    HTML_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    HTML_OUT.write_text(
        html,
        encoding="utf-8",
    )


def build_summary_html(
    spread,
    provenance,
):
    rows = []

    for obs_date in reversed(
        spread.index
    ):
        cells = [
            (
                '<td class="date-cell">'
                f'{pd.Timestamp(obs_date).strftime("%Y-%m-%d")}'
                "</td>"
            )
        ]

        for tenor in spread.columns:
            value = spread.loc[
                obs_date,
                tenor,
            ]

            status = provenance.loc[
                obs_date,
                tenor,
            ]

            value_text = (
                f"{float(value):.2f} pb"
                if pd.notna(value)
                else "—"
            )

            klass = (
                "available"
                if pd.notna(value)
                else "missing"
            )

            cells.append(
                f'<td class="{klass}" '
                f'title="{status or "Sin datos"}">'
                f'<span class="value">{value_text}</span>'
                f'<span class="status">{status or "Sin datos"}</span>'
                "</td>"
            )

        rows.append(
            "<tr>"
            + "".join(cells)
            + "</tr>"
        )

    header_cells = [
        "<th>Fecha</th>"
    ]

    label_by_tenor = {
        float(value): label
        for label, value in PUBLIC_TENORS.items()
    }

    for tenor in spread.columns:
        header_cells.append(
            "<th>"
            f"{label_by_tenor[float(tenor)]}"
            "<br>"
            f"<small>{float(tenor):g} años</small>"
            "</th>"
        )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tabla — Spread soberano BRL por tenor</title>

  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f4f6f8;
      color: #172033;
      font-family: Arial, Helvetica, sans-serif;
    }}

    .page {{
      max-width: 1700px;
      margin: 0 auto;
    }}

    .panel {{
      background: white;
      border: 1px solid #d9e0e7;
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 2px 10px rgba(16,24,40,.06);
    }}

    h2 {{
      margin: 0 0 8px;
    }}

    p {{
      color: #667085;
      line-height: 1.5;
    }}

    .method-note {{
      border-left: 4px solid #0b4f8a;
      padding: 10px 12px;
      background: #eef5fa;
      color: #344054;
      border-radius: 6px;
    }}

    .table-scroll {{
      overflow: auto;
      max-height: 760px;
      border: 1px solid #d9e0e7;
      border-radius: 8px;
    }}

    table {{
      border-collapse: separate;
      border-spacing: 0;
      width: max-content;
      min-width: 100%;
      font-size: 12px;
    }}

    th,
    td {{
      padding: 7px 9px;
      border-right: 1px solid #e4e7ec;
      border-bottom: 1px solid #e4e7ec;
      text-align: center;
      white-space: nowrap;
    }}

    th {{
      position: sticky;
      top: 0;
      z-index: 3;
      background: #101828;
      color: white;
    }}

    th:first-child,
    .date-cell {{
      position: sticky;
      left: 0;
      z-index: 2;
    }}

    th:first-child {{
      z-index: 4;
    }}

    .date-cell {{
      background: white;
      font-weight: 700;
    }}

    .available {{
      background: #dbeafe;
    }}

    .missing {{
      background: #f2f4f7;
    }}

    td .value {{
      display: block;
      font-weight: 700;
      color: #172033;
    }}

    td .status {{
      display: block;
      margin-top: 2px;
      font-size: 10px;
      color: #667085;
    }}
  </style>
</head>

<body>
<div class="page">
  <div class="panel">

    <h2>Spread soberano BRL por tenor</h2>

    <p class="method-note">
      Curva soberana nominal zero-cupón de LTN + NTN-F frente a curva DI
      zero-cupón al mismo tenor. Spread geométrico en puntos básicos.
      No es un CDS contractual. Las celdas vacías indican ausencia de
      soporte observado conjunto; no se extrapola en esta tabla pública.
    </p>

    <div class="table-scroll">
      <table>
        <thead>
          <tr>{''.join(header_cells)}</tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>

  </div>
</div>
</body>
</html>
"""

    SUMMARY_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SUMMARY_OUT.write_text(
        html,
        encoding="utf-8",
    )




def _public_instrument_type(
    value,
):
    value = str(value)

    if value == "NTNF":
        return "NTN-F"

    return value


def build_sovereign_audit_tables():
    panel_dates = load_final_panel_dates()

    nominal, yas = (
        load_nominal_sovereign_inputs()
    )

    yas.index = pd.to_datetime(
        yas.index,
        errors="raise",
    ).normalize()

    dc = DayCounts(
        "bus/252",
        calendar="cdr_anbima",
    )

    bootstrap_input_rows = []
    cash_flow_rows = []
    zero_node_rows = []

    for obs_date in panel_dates:
        obs_date = pd.Timestamp(
            obs_date
        ).normalize()

        zero_curve, stats = (
            build_sovereign_zero_curve(
                obs_date=obs_date,
                nominal=nominal,
                yas=yas,
                dc=dc,
            )
        )

        if (
            zero_curve is None
            or zero_curve.empty
        ):
            continue

        active = nominal[
            nominal["ISSUE_DT"].le(
                obs_date
            )
            & nominal["MATURITY"].gt(
                obs_date
            )
        ].copy()

        candidates = []

        for _, bond in active.iterrows():
            instrument_id = bond["id"]

            if instrument_id not in yas.columns:
                continue

            ytm_pct = pd.to_numeric(
                yas.at[
                    obs_date,
                    instrument_id,
                ],
                errors="coerce",
            )

            if (
                pd.isna(ytm_pct)
                or float(ytm_pct) == 0.0
            ):
                continue

            candidates.append(
                (
                    bond,
                    float(ytm_pct),
                )
            )

        ltn_tenors = set()

        for bond, _ in candidates:
            if bond["TYPE"] != "LTN":
                continue

            payment_date = dc.following(
                bond["MATURITY"].date()
            )

            ltn_tenors.add(
                dc.tf(
                    obs_date.date(),
                    payment_date,
                )
            )

        zero_tenors = (
            zero_curve.index.to_numpy(
                dtype=float
            )
        )

        used_ltn = 0
        used_ntnf = 0

        date_cash_flow_rows = []

        for bond, ytm_pct in candidates:
            raw_type = str(
                bond["TYPE"]
            )

            public_type = (
                _public_instrument_type(
                    raw_type
                )
            )

            included = True
            exclusion_reason = ""

            coupon_pct = 0.0
            frequency = np.nan

            if raw_type == "LTN":
                payment_dates = [
                    dc.following(
                        bond["MATURITY"].date()
                    )
                ]

                cash_flow_values = [
                    100.0
                ]

            else:
                coupon_pct = pd.to_numeric(
                    bond["CPN"],
                    errors="coerce",
                )

                frequency = pd.to_numeric(
                    bond["CPN_FREQ"],
                    errors="coerce",
                )

                if (
                    pd.isna(coupon_pct)
                    or pd.isna(frequency)
                ):
                    raise AssertionError(
                        "Missing NTN-F coupon metadata for "
                        f"{bond['id']}."
                    )

                frequency = int(
                    frequency
                )

                if frequency != 2:
                    raise AssertionError(
                        "Unexpected NTN-F coupon "
                        f"frequency {frequency} "
                        f"for {bond['id']}."
                    )

                coupon_cash_flow = (
                    (
                        1.0
                        + float(coupon_pct)
                        / 100.0
                    )
                    ** (
                        1.0
                        / frequency
                    )
                    - 1.0
                ) * 100.0

                expiry = (
                    bond["MATURITY"].date()
                )

                payment_dates = [
                    dc.following(expiry)
                ]

                payment_date = dc.workday(
                    dc.eom(
                        dc.following(
                            expiry
                        ),
                        offset=-7,
                    ),
                    1,
                )

                while (
                    payment_date
                    > dc.following(
                        obs_date.date()
                    )
                ):
                    payment_dates.append(
                        payment_date
                    )

                    payment_date = (
                        dc.workday(
                            dc.eom(
                                payment_date,
                                offset=-7,
                            ),
                            1,
                        )
                    )

                payment_dates = sorted(
                    payment_dates
                )

                cash_flow_values = [
                    coupon_cash_flow
                    for _ in payment_dates
                ]

                cash_flow_values[-1] += (
                    100.0
                )

                if len(payment_dates) == 1:
                    single_tenor = dc.tf(
                        obs_date.date(),
                        payment_dates[0],
                    )

                    if (
                        single_tenor
                        in ltn_tenors
                    ):
                        included = False

                        exclusion_reason = (
                            "NTN-F de un solo flujo "
                            "duplicada por LTN en el "
                            "mismo tenor BUS/252"
                        )

            maturity_payment_date = (
                dc.following(
                    bond["MATURITY"].date()
                )
            )

            maturity_tenor = float(
                dc.tf(
                    obs_date.date(),
                    maturity_payment_date,
                )
            )

            nearest_position = int(
                np.argmin(
                    np.abs(
                        zero_tenors
                        - maturity_tenor
                    )
                )
            )

            exact_node = bool(
                np.isclose(
                    zero_tenors[
                        nearest_position
                    ],
                    maturity_tenor,
                    rtol=0.0,
                    atol=1e-12,
                )
            )

            if included:
                if raw_type == "LTN":
                    used_ltn += 1
                else:
                    used_ntnf += 1

                if exact_node:
                    zero_rate_pct = float(
                        zero_curve.iloc[
                            nearest_position
                        ]
                        * 100.0
                    )

                    zero_method = (
                        "nodo cero exacto"
                    )

                else:
                    zero_rate_pct = float(
                        flat_forward_interpolation(
                            maturity_tenor,
                            zero_curve,
                        )
                        * 100.0
                    )

                    zero_method = (
                        "interpolacion "
                        "flat-forward"
                    )

                if (
                    raw_type == "LTN"
                    and exact_node
                    and abs(
                        zero_rate_pct
                        - ytm_pct
                    ) > 1e-10
                ):
                    raise AssertionError(
                        "Exact LTN zero node does "
                        "not equal observed YTM for "
                        f"{bond['id']} on "
                        f"{obs_date.date()}."
                    )

            else:
                zero_rate_pct = np.nan
                zero_method = "excluido"

            flow_dates_text = " | ".join(
                pd.Timestamp(
                    payment_date
                ).strftime("%Y-%m-%d")
                for payment_date
                in payment_dates
            )

            flow_values_text = " | ".join(
                f"{float(value):.6f}"
                for value
                in cash_flow_values
            )

            bootstrap_input_rows.append(
                {
                    "obs_date": obs_date,
                    "instrument_id": (
                        bond["id"]
                    ),
                    "instrument_type": (
                        public_type
                    ),
                    "issue_date": pd.Timestamp(
                        bond["ISSUE_DT"]
                    ),
                    "maturity_date": pd.Timestamp(
                        bond["MATURITY"]
                    ),
                    "maturity_tenor_bus252": (
                        maturity_tenor
                    ),
                    "ytm_pre_bootstrap_pct": (
                        ytm_pct
                    ),
                    "cupon_pct": float(
                        coupon_pct
                    ),
                    "coupon_frequency": (
                        frequency
                    ),
                    "remaining_cash_flows": (
                        len(payment_dates)
                    ),
                    "first_cash_flow_date": (
                        pd.Timestamp(
                            min(
                                payment_dates
                            )
                        )
                    ),
                    "last_cash_flow_date": (
                        pd.Timestamp(
                            max(
                                payment_dates
                            )
                        )
                    ),
                    "cash_flow_dates": (
                        flow_dates_text
                    ),
                    "cash_flow_values": (
                        flow_values_text
                    ),
                    "included_in_bootstrap": (
                        included
                    ),
                    "zero_rate_at_maturity_pct": (
                        zero_rate_pct
                    ),
                    "zero_rate_method": (
                        zero_method
                    ),
                    "exclusion_reason": (
                        exclusion_reason
                    ),
                }
            )

            for (
                payment_date,
                cash_flow_value,
            ) in zip(
                payment_dates,
                cash_flow_values,
            ):
                row = {
                    "obs_date": obs_date,
                    "instrument_id": (
                        bond["id"]
                    ),
                    "instrument_type": (
                        public_type
                    ),
                    "payment_date": (
                        pd.Timestamp(
                            payment_date
                        )
                    ),
                    "payment_tenor_bus252": (
                        float(
                            dc.tf(
                                obs_date.date(),
                                payment_date,
                            )
                        )
                    ),
                    "cash_flow_value": (
                        float(
                            cash_flow_value
                        )
                    ),
                    "included_in_bootstrap": (
                        included
                    ),
                    "exclusion_reason": (
                        exclusion_reason
                    ),
                }

                date_cash_flow_rows.append(
                    row
                )

                cash_flow_rows.append(
                    row
                )

        if used_ltn != stats["used_ltn"]:
            raise AssertionError(
                "LTN audit count mismatch on "
                f"{obs_date.date()}: "
                f"{used_ltn} != "
                f"{stats['used_ltn']}."
            )

        if used_ntnf != stats["used_ntnf"]:
            raise AssertionError(
                "NTN-F audit count mismatch on "
                f"{obs_date.date()}: "
                f"{used_ntnf} != "
                f"{stats['used_ntnf']}."
            )

        included_flows = pd.DataFrame(
            [
                row
                for row
                in date_cash_flow_rows
                if row[
                    "included_in_bootstrap"
                ]
            ]
        )

        if included_flows.empty:
            raise AssertionError(
                "No included sovereign cash flows "
                f"on {obs_date.date()}."
            )

        for tenor, rate_dec in (
            zero_curve.items()
        ):
            tenor = float(tenor)

            gaps = (
                included_flows[
                    "payment_tenor_bus252"
                ]
                .sub(tenor)
                .abs()
            )

            minimum_gap = float(
                gaps.min()
            )

            exact_mapping = (
                minimum_gap < 1e-10
            )

            if exact_mapping:
                matching = included_flows[
                    np.isclose(
                        included_flows[
                            "payment_tenor_bus252"
                        ],
                        tenor,
                        rtol=0.0,
                        atol=1e-10,
                    )
                ].copy()

            else:
                nearest_index = (
                    gaps.idxmin()
                )

                matching = included_flows.loc[
                    [nearest_index]
                ].copy()

            node_dates = sorted(
                {
                    pd.Timestamp(
                        value
                    ).strftime("%Y-%m-%d")
                    for value
                    in matching[
                        "payment_date"
                    ]
                }
            )

            source_instruments = sorted(
                {
                    str(value)
                    for value
                    in matching[
                        "instrument_id"
                    ]
                }
            )

            source_types = sorted(
                {
                    str(value)
                    for value
                    in matching[
                        "instrument_type"
                    ]
                }
            )

            zero_node_rows.append(
                {
                    "obs_date": obs_date,
                    "node_date": (
                        " | ".join(
                            node_dates
                        )
                    ),
                    "node_tenor_bus252": (
                        tenor
                    ),
                    "zero_rate_pct": (
                        float(rate_dec)
                        * 100.0
                    ),
                    "instruments_with_flow": (
                        " | ".join(
                            source_instruments
                        )
                    ),
                    "instrument_types": (
                        " | ".join(
                            source_types
                        )
                    ),
                    "source_instrument_count": (
                        len(
                            source_instruments
                        )
                    ),
                    "exact_date_mapping": (
                        exact_mapping
                    ),
                    "tenor_mapping_gap": (
                        minimum_gap
                    ),
                }
            )

    bootstrap_inputs = pd.DataFrame(
        bootstrap_input_rows
    ).sort_values(
        [
            "obs_date",
            "instrument_type",
            "maturity_date",
            "instrument_id",
        ]
    )

    cash_flows = pd.DataFrame(
        cash_flow_rows
    ).sort_values(
        [
            "obs_date",
            "payment_date",
            "instrument_type",
            "instrument_id",
        ]
    )

    zero_nodes = pd.DataFrame(
        zero_node_rows
    ).sort_values(
        [
            "obs_date",
            "node_tenor_bus252",
        ]
    )

    return (
        bootstrap_inputs,
        cash_flows,
        zero_nodes,
    )


def _json_default(
    value,
):
    if isinstance(
        value,
        np.generic,
    ):
        return value.item()

    if isinstance(
        value,
        pd.Timestamp,
    ):
        return value.strftime(
            "%Y-%m-%d"
        )

    raise TypeError(
        f"Unsupported JSON type: "
        f"{type(value)!r}"
    )


def _records_by_date(
    frame,
):
    data = frame.copy()

    date_columns = [
        "obs_date",
        "issue_date",
        "maturity_date",
        "first_cash_flow_date",
        "last_cash_flow_date",
    ]

    for column in date_columns:
        if column not in data.columns:
            continue

        data[column] = pd.to_datetime(
            data[column],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")

    data = (
        data.astype(object)
        .where(
            pd.notna(data),
            None,
        )
    )

    result = {}

    for obs_date, group in data.groupby(
        "obs_date",
        sort=True,
    ):
        result[str(obs_date)] = (
            group.drop(
                columns=["obs_date"]
            )
            .to_dict(
                orient="records"
            )
        )

    return result


def build_sovereign_inputs_html(
    support,
):
    display = support.sort_values(
        "obs_date",
        ascending=False,
    ).copy()

    rows = []

    for _, row in display.iterrows():
        obs_date = pd.Timestamp(
            row["obs_date"]
        ).strftime("%Y-%m-%d")

        rows.append(
            "<tr>"
            f"<td>{obs_date}</td>"
            f"<td>{int(row['sovereign_raw_inputs'])}</td>"
            f"<td>{int(row['used_ltn'])}</td>"
            f"<td>{int(row['used_ntnf'])}</td>"
            f"<td>{int(row['sovereign_zero_nodes'])}</td>"
            f"<td>{float(row['sovereign_min_tenor']):.2f}</td>"
            f"<td>{float(row['sovereign_max_tenor']):.2f}</td>"
            "</tr>"
        )

    html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>
Instrumentos soberanos nominales - LTN + NTN-F
</title>

<style>
body {
    font-family: Arial, sans-serif;
    margin: 28px;
    color: #17233c;
    background: white;
}

.lead {
    max-width: 1080px;
    line-height: 1.6;
    color: #52617d;
}

.note {
    max-width: 1080px;
    padding: 14px 16px;
    margin: 20px 0;
    background: #f5f7fb;
    border-left: 4px solid #345fa8;
    line-height: 1.55;
}

.table-wrap {
    overflow-x: auto;
}

table {
    border-collapse: collapse;
    width: 100%;
    font-size: 14px;
}

th,
td {
    padding: 9px 10px;
    border-bottom: 1px solid #dfe5ef;
    text-align: right;
    white-space: nowrap;
}

th:first-child,
td:first-child {
    text-align: left;
}

th {
    background: #f7f9fc;
    position: sticky;
    top: 0;
}
</style>
</head>

<body>

<h1>
Instrumentos soberanos nominales - LTN + NTN-F
</h1>

<p class="lead">
Entradas utilizadas para construir la curva soberana
nominal BRL antes del bootstrap. Las LTN son titulos
zero-cupon y funcionan como anclas cero directas.
Las NTN-F pagan cupones semestrales y se incorporan
mediante sus flujos de intereses y principal.
</p>

<div class="note">
<strong>Convencion:</strong>
BUS/252 con calendario ANBIMA.
El bootstrap utiliza los instrumentos soberanos activos
con rendimiento valido en cada fecha.
La pagina de curva cero presenta el detalle por
instrumento, flujo y nodo para cada fecha de observacion.
</div>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Fecha</th>
<th>Inputs observados</th>
<th>LTN usadas</th>
<th>NTN-F usadas</th>
<th>Nodos cero</th>
<th>Tenor min.</th>
<th>Tenor max.</th>
</tr>
</thead>

<tbody>
__ROWS__
</tbody>
</table>
</div>

</body>
</html>
"""

    html = html.replace(
        "__ROWS__",
        "".join(rows),
    )

    SOV_INPUTS_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOV_INPUTS_OUT.write_text(
        html,
        encoding="utf-8",
    )


def build_sovereign_zero_html(
    sovereign_yield,
    bootstrap_inputs,
    zero_nodes,
):
    tenors = [
        float(value)
        for value
        in sovereign_yield.columns
    ]

    fig = go.Figure(
        data=[
            go.Surface(
                z=sovereign_yield.to_numpy(
                    dtype=float
                ),
                x=tenors,
                y=(
                    sovereign_yield.index
                    .astype(str)
                ),
                colorscale="Turbo",
                colorbar=dict(
                    title="Tasa cero (%)",
                ),
                hovertemplate=(
                    "Plazo: %{x:g} anos"
                    "<br>Fecha: %{y}"
                    "<br>Tasa cero: %{z:.3f}%"
                    "<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        title=dict(
            text=(
                "Curva soberana cero BRL - "
                "LTN + NTN-F post-bootstrap"
            ),
            x=0.5,
            xanchor="center",
            y=0.96,
            yanchor="top",
            font=dict(
                size=22
            ),
        ),
        scene=dict(
            xaxis=dict(
                title=dict(
                    text="Plazo (anos)",
                    font=dict(
                        size=14
                    ),
                ),
                tickfont=dict(
                    size=11
                ),
            ),
            yaxis=dict(
                title=dict(
                    text="Fecha",
                    font=dict(
                        size=14
                    ),
                ),
                tickfont=dict(
                    size=11
                ),
            ),
            zaxis=dict(
                title=dict(
                    text="Tasa cero (%)",
                    font=dict(
                        size=14
                    ),
                ),
                tickfont=dict(
                    size=11
                ),
            ),
            camera=dict(
                eye=dict(
                    x=1.55,
                    y=-1.75,
                    z=1.05,
                )
            ),
            aspectmode="manual",
            aspectratio=dict(
                x=1.15,
                y=1.85,
                z=0.85,
            ),
            domain=dict(
                x=[0.02, 0.90],
                y=[0.02, 0.92],
            ),
        ),
        height=820,
        margin=dict(
            l=20,
            r=100,
            b=20,
            t=70,
        ),
        paper_bgcolor="white",
        font=dict(
            size=12
        ),
    )

    chart_html = pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn",
        config={
            "responsive": True,
            "displaylogo": False,
            "scrollZoom": True,
        },
    )

    coverage = (
        sovereign_yield.notna()
        .sum()
        .rename(
            "fechas_con_dato"
        )
        .to_frame()
    )

    coverage[
        "total_fechas"
    ] = len(
        sovereign_yield
    )

    coverage[
        "cobertura_pct"
    ] = (
        coverage[
            "fechas_con_dato"
        ]
        / coverage[
            "total_fechas"
        ]
        * 100.0
    )

    coverage_rows = []

    for tenor, row in coverage.iterrows():
        coverage_rows.append(
            "<tr>"
            f"<td>{float(tenor):g} anos</td>"
            f"<td>{int(row['fechas_con_dato'])}</td>"
            f"<td>{int(row['total_fechas'])}</td>"
            f"<td>{float(row['cobertura_pct']):.1f}%</td>"
            "</tr>"
        )

    inputs_by_date = (
        _records_by_date(
            bootstrap_inputs
        )
    )

    nodes_by_date = (
        _records_by_date(
            zero_nodes
        )
    )

    dates = sorted(
        set(inputs_by_date)
        | set(nodes_by_date)
    )

    payload = {
        "dates": dates,
        "inputs": inputs_by_date,
        "nodes": nodes_by_date,
    }

    audit_json = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        default=_json_default,
    ).replace(
        "</",
        "<\\/",
    )

    html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>Curva soberana cero BRL</title>

<style>
body {
    margin: 0;
    padding: 24px;
    background: #f4f6f8;
    color: #172033;
    font-family: Arial, Helvetica, sans-serif;
}

.page {
    max-width: 1600px;
    margin: 0 auto;
}

.panel {
    background: white;
    border: 1px solid #d9e0e7;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 20px;
    box-shadow: 0 2px 10px rgba(16,24,40,.06);
}

.lead {
    max-width: 1180px;
    line-height: 1.6;
    color: #52617d;
}

.note {
    border-left: 4px solid #0b4f8a;
    padding: 10px 12px;
    margin: 18px 0;
    background: #eef5fa;
    color: #344054;
    border-radius: 6px;
    line-height: 1.55;
}

.chart-note {
    margin: 10px 4px 2px;
    padding: 10px 12px;
    color: #475467;
    background: #f8fafc;
    border: 1px solid #e4e7ec;
    border-radius: 6px;
    font-size: 14px;
    line-height: 1.5;
}

.chart {
    width: 100%;
    min-height: 820px;
}

.chart .plotly-graph-div {
    min-height: 820px !important;
}

.controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin: 22px 0 14px;
}

.controls label {
    font-weight: 700;
}

.controls select {
    padding: 8px 10px;
    border: 1px solid #cbd4e2;
    border-radius: 5px;
    background: white;
    min-width: 180px;
}

.counter {
    color: #52617d;
    font-size: 14px;
}

.table-wrap {
    overflow-x: auto;
    margin-bottom: 28px;
    border: 1px solid #e1e6ef;
    border-radius: 6px;
}

table {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
}

th,
td {
    padding: 8px 10px;
    border-bottom: 1px solid #e1e6ef;
    text-align: right;
    white-space: nowrap;
    vertical-align: top;
}

th {
    position: sticky;
    top: 0;
    background: #f7f9fc;
    z-index: 1;
}

th:first-child,
td:first-child {
    text-align: left;
}

td.text {
    text-align: left;
    white-space: normal;
    min-width: 180px;
}

td.flows {
    text-align: left;
    white-space: normal;
    min-width: 320px;
    line-height: 1.45;
}

.status-yes {
    font-weight: 700;
}

.status-no {
    font-weight: 700;
}

h2 {
    margin-top: 34px;
}

.small {
    color: #68758d;
    font-size: 13px;
    line-height: 1.5;
}
</style>
</head>

<body>
<div class="page">

<div class="panel">
<h1>Curva soberana cero BRL</h1>

<p class="lead">
Curva nominal zero-cupon derivada de LTN y NTN-F.
Las LTN funcionan como anclas cero directas.
Los cupones y el principal de las NTN-F se separan
mediante bootstrap para obtener tasas cero comparables
por tenor.
</p>

<div class="note">
<strong>Metodologia:</strong>
bootstrap BUS/252 con calendario ANBIMA.
La tabla de instrumentos muestra la YTM observada antes
del bootstrap y la tasa cero al vencimiento despues del
bootstrap. Esta ultima no es una nueva YTM del titulo.
La tabla de nodos contiene las tasas que forman la curva
cero representada en el grafico.
Esta construccion no utiliza NTN-B ni WLA.
Los valores usados se muestran para auditoria; los
archivos fuente originales no se distribuyen.
</div>

<div class="chart">
__CHART__
</div>

<p class="chart-note">
<strong>Nota:</strong>
Los espacios sin superficie corresponden a combinaciones
de fecha y tenor fuera del soporte observado de la curva
soberana. No representan una tasa cero igual a cero.
</p>

</div>

<div class="panel">
<h2>Cobertura por tenor estandar</h2>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Tenor</th>
<th>Fechas con dato</th>
<th>Total fechas</th>
<th>Cobertura</th>
</tr>
</thead>
<tbody>
__COVERAGE_ROWS__
</tbody>
</table>
</div>
</div>

<div class="panel">
<h2>Detalle de construccion por fecha</h2>

<div class="controls">
<label for="audit-date">
Fecha de observacion:
</label>

<select id="audit-date"></select>

<span class="counter"
      id="instrument-counter"></span>

<span class="counter"
      id="node-counter"></span>
</div>

<p class="small">
La primera tabla presenta los instrumentos y flujos
antes del bootstrap, junto con la tasa cero obtenida
al vencimiento. La segunda presenta los nodos
post-bootstrap que forman la curva cero.
</p>

<h3>Instrumentos antes del bootstrap</h3>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Instrumento</th>
<th>Tipo</th>
<th>Emision</th>
<th>Vencimiento</th>
<th>Tenor BUS/252</th>
<th>YTM pre-bootstrap (%)</th>
<th>Cupon (%)</th>
<th>Frecuencia</th>
<th>Flujos restantes</th>
<th>Fechas de flujos</th>
<th>Valores de flujos</th>
<th>Incluido</th>
<th>Tasa cero al vencimiento (%)</th>
<th>Metodo post-bootstrap</th>
<th>Motivo de exclusion</th>
</tr>
</thead>

<tbody id="instrument-body"></tbody>
</table>
</div>

<h3>Nodos de la curva cero post-bootstrap</h3>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Fecha del nodo</th>
<th>Tenor BUS/252</th>
<th>Tasa cero (%)</th>
<th>Instrumentos con flujo</th>
<th>Tipos</th>
<th>Cantidad</th>
<th>Mapeo exacto</th>
<th>Diferencia de tenor</th>
</tr>
</thead>

<tbody id="node-body"></tbody>
</table>
</div>

<script id="audit-data"
        type="application/json">
__AUDIT_JSON__
</script>

<script>
const auditData = JSON.parse(
    document.getElementById(
        "audit-data"
    ).textContent
);

const dateSelect = document.getElementById(
    "audit-date"
);

const instrumentBody = document.getElementById(
    "instrument-body"
);

const nodeBody = document.getElementById(
    "node-body"
);

function escapeHtml(value) {
    if (
        value === null
        || value === undefined
    ) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatNumber(
    value,
    digits = 6
) {
    if (
        value === null
        || value === undefined
        || value === ""
    ) {
        return "";
    }

    return Number(value).toFixed(
        digits
    );
}

function formatFrequency(value) {
    if (
        value === null
        || value === undefined
        || value === ""
    ) {
        return "";
    }

    return String(value);
}

function yesNo(value) {
    return value ? "Si" : "No";
}

function renderTables() {
    const date = dateSelect.value;

    const instruments = (
        auditData.inputs[date]
        || []
    );

    const nodes = (
        auditData.nodes[date]
        || []
    );

    instrumentBody.innerHTML = instruments.map(
        row => `
<tr>
<td>${escapeHtml(row.instrument_id)}</td>
<td>${escapeHtml(row.instrument_type)}</td>
<td>${escapeHtml(row.issue_date)}</td>
<td>${escapeHtml(row.maturity_date)}</td>
<td>${formatNumber(row.maturity_tenor_bus252)}</td>
<td>${formatNumber(row.ytm_pre_bootstrap_pct)}</td>
<td>${formatNumber(row.cupon_pct)}</td>
<td>${escapeHtml(formatFrequency(row.coupon_frequency))}</td>
<td>${escapeHtml(row.remaining_cash_flows)}</td>
<td class="flows">${escapeHtml(row.cash_flow_dates)}</td>
<td class="flows">${escapeHtml(row.cash_flow_values)}</td>
<td class="${row.included_in_bootstrap
    ? "status-yes"
    : "status-no"}">${yesNo(row.included_in_bootstrap)}</td>
<td>${formatNumber(row.zero_rate_at_maturity_pct)}</td>
<td class="text">${escapeHtml(row.zero_rate_method)}</td>
<td class="text">${escapeHtml(row.exclusion_reason)}</td>
</tr>`
    ).join("");

    nodeBody.innerHTML = nodes.map(
        row => `
<tr>
<td>${escapeHtml(row.node_date)}</td>
<td>${formatNumber(row.node_tenor_bus252, 12)}</td>
<td>${formatNumber(row.zero_rate_pct, 9)}</td>
<td class="text">${escapeHtml(row.instruments_with_flow)}</td>
<td>${escapeHtml(row.instrument_types)}</td>
<td>${escapeHtml(row.source_instrument_count)}</td>
<td>${yesNo(row.exact_date_mapping)}</td>
<td>${formatNumber(row.tenor_mapping_gap, 12)}</td>
</tr>`
    ).join("");

    document.getElementById(
        "instrument-counter"
    ).textContent = (
        `${instruments.length} instrumentos`
    );

    document.getElementById(
        "node-counter"
    ).textContent = (
        `${nodes.length} nodos cero`
    );
}

auditData.dates
    .slice()
    .reverse()
    .forEach(
        date => {
            const option = document.createElement(
                "option"
            );

            option.value = date;
            option.textContent = date;

            dateSelect.appendChild(
                option
            );
        }
    );

if (auditData.dates.length > 0) {
    dateSelect.value = (
        auditData.dates[
            auditData.dates.length - 1
        ]
    );
}

dateSelect.addEventListener(
    "change",
    renderTables
);

renderTables();
</script>

</div>
</div>
</body>
</html>
"""

    html = (
        html.replace(
            "__CHART__",
            chart_html,
        )
        .replace(
            "__COVERAGE_ROWS__",
            "".join(
                coverage_rows
            ),
        )
        .replace(
            "__AUDIT_JSON__",
            audit_json,
        )
    )

    SOV_ZERO_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOV_ZERO_OUT.write_text(
        html,
        encoding="utf-8",
    )


def export_workbook(
    spread,
    sovereign_yield,
    di_yield,
    provenance,
    support,
    bootstrap_inputs,
    cash_flows,
    zero_nodes,
):
    XLSX_OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    methodology = (
        build_methodology_sheet()
    )

    with pd.ExcelWriter(
        XLSX_OUT,
        engine="openpyxl",
    ) as writer:
        spread.to_excel(
            writer,
            sheet_name="spread_bps",
        )

        sovereign_yield.to_excel(
            writer,
            sheet_name="sovereign_zero_pct",
        )

        di_yield.to_excel(
            writer,
            sheet_name="DI_zero_pct",
        )

        provenance.to_excel(
            writer,
            sheet_name="provenance",
        )

        support.to_excel(
            writer,
            sheet_name="curve_support",
            index=False,
        )

        methodology.to_excel(
            writer,
            sheet_name="methodology",
            index=False,
        )

        bootstrap_inputs.to_excel(
            writer,
            sheet_name="bootstrap_inputs",
            index=False,
        )

        cash_flows.to_excel(
            writer,
            sheet_name="cash_flows",
            index=False,
        )

        zero_nodes.to_excel(
            writer,
            sheet_name="zero_nodes",
            index=False,
        )


def build_brl_sovereign_spread_dashboard():
    (
        spread,
        sovereign_yield,
        di_yield,
        provenance,
        support,
    ) = build_dashboard_data()

    if spread.empty:
        raise ValueError(
            "BRL sovereign spread surface is empty."
        )

    (
        bootstrap_inputs,
        cash_flows,
        zero_nodes,
    ) = build_sovereign_audit_tables()

    export_workbook(
        spread=spread,
        sovereign_yield=sovereign_yield,
        di_yield=di_yield,
        provenance=provenance,
        support=support,
        bootstrap_inputs=bootstrap_inputs,
        cash_flows=cash_flows,
        zero_nodes=zero_nodes,
    )

    build_sovereign_inputs_html(
        support=support,
    )

    build_sovereign_zero_html(
        sovereign_yield=sovereign_yield,
        bootstrap_inputs=bootstrap_inputs,
        zero_nodes=zero_nodes,
    )

    build_surface_html(
        spread=spread,
        provenance=provenance,
    )

    build_summary_html(
        spread=spread,
        provenance=provenance,
    )

    print(
        "BRL sovereign audit rows: "
        f"{len(bootstrap_inputs)} inputs, "
        f"{len(cash_flows)} cash flows, "
        f"{len(zero_nodes)} zero nodes"
    )

    print(
        "BRL sovereign inputs page saved to "
        f"{SOV_INPUTS_OUT}"
    )

    print(
        "BRL sovereign zero surface saved to "
        f"{SOV_ZERO_OUT}"
    )

    print(
        "BRL sovereign spread surface saved to "
        f"{HTML_OUT}"
    )

    print(
        "BRL sovereign spread table saved to "
        f"{SUMMARY_OUT}"
    )

    print(
        "BRL sovereign provenance workbook saved to "
        f"{XLSX_OUT}"
    )

    print(
        f"Dates: {len(spread)}"
    )

    print(
        f"Tenors: {len(spread.columns)}"
    )

    print(
        "Non-missing cells by tenor:"
    )

    for tenor in spread.columns:
        count = int(
            spread[tenor]
            .notna()
            .sum()
        )

        print(
            f"  {float(tenor):>4g}y: "
            f"{count:>3} / {len(spread)}"
        )


if __name__ == "__main__":
    build_brl_sovereign_spread_dashboard()