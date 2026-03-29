# main.py

import os
import pandas as pd
import numpy as np
from calendars.daycounts import DayCounts
import sys
sys.stdout.reconfigure(encoding="utf-8")

from tqdm import tqdm

# Loaders
from src.utils.filters import (
    filter_corporate_universe,
    filter_government_universe,
    anomaly_filtering_results,
)
from src.utils.file_io import (
    load_corp_bond_data,
    load_govt_bond_data,
    load_yield_surface,
    load_di_surface,
)
from src.utils.interpolation import interpolate_di_surface, interpolate_surface
from src.utils.plotting import show_benchmark_table
from src.core.windowing import build_observation_windows
from src.core.spread_calculator import compute_spreads, compute_spreads_ltn
from src.config import CONFIG

# REAL CURVE (WLA + NTNB)
from src.core.curve_builder import (
    load_real_curve_support,
    build_real_curve_for_obs_date,
)


def remove_unnamed(df: pd.DataFrame) -> pd.DataFrame:
    """Remove colunas Unnamed:* que aparecem no Excel."""
    return df.loc[:, ~df.columns.str.contains("^Unnamed")]


# ============================================================
# BUILD AND SAVE WLA + NTNB REAL SURFACE
# (mesmo padrão do synthetic_cds)
# ============================================================
def build_and_save_real_wla_ntnb_surface(
    input_path="data/real_curve_surface_govt.xlsx",
    xlsx_out="data/wla_ntnb_surface.xlsx",
    html_out="templates/wla_ntnb_surface.html",
    summary_out="templates/wla_ntnb_surface_summary.html"
):
    if not os.path.exists(input_path):
        print(f"⚠ Arquivo não encontrado: {input_path}")
        return

    df = pd.read_excel(input_path)

    if not {"obs_date", "tenor", "yield"}.issubset(df.columns):
        print("⚠ real_curve_surface_govt.xlsx não contém colunas (obs_date, tenor, yield).")
        return

    df["obs_date"] = pd.to_datetime(df["obs_date"], errors="coerce")
    df["tenor"] = pd.to_numeric(df["tenor"], errors="coerce")
    df = df.dropna(subset=["obs_date", "tenor", "yield"])

    # Pivot — igual ao DI/IPCA
    surface = (
        df.pivot_table(
            index="obs_date",
            columns="tenor",
            values="yield",
            aggfunc="mean"
        )
        .sort_index()
    )

    # ordenar colunas numericamente
    surface = surface.reindex(sorted(surface.columns), axis=1)

    # salvar XLSX
    os.makedirs("data", exist_ok=True)
    surface.to_excel(xlsx_out)

    # resumo html
    os.makedirs("templates", exist_ok=True)
    summary_html = (
        surface.tail(30)
        .round(4)
        .to_html(border=0, classes="table table-striped table-sm")
    )
    with open(summary_out, "w", encoding="utf-8") as f:
        f.write(summary_html)

    # superfície Plotly 3D
    import plotly.graph_objects as go

    fig = go.Figure(
        data=[
            go.Surface(
                z=surface.values,
                x=surface.columns.astype(float),
                y=surface.index.astype(str),
                colorscale="Turbo",
            )
        ]
    )

    fig.update_layout(
        title="Real IPCA Surface (WLA + NTNB)",
        scene=dict(
            xaxis_title="Tenor (anos)",
            yaxis_title="Data",
            zaxis_title="Yield (%)",
        ),
        height=820,
    )

    fig.write_html(html_out)
    print(f"✅ WLA+NTNB surface salva em {html_out}")


# ============================================================
# =======================  MAIN FLOW  =========================
# ============================================================
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs("templates", exist_ok=True)

    # ============================================================
    # LOAD NTNB REAL CURVE SUPPORT
    # ============================================================
    ntnb_meta_df, ntnb_ya_df = load_real_curve_support()

    # ============================================================
    # CORPORATE BONDS
    # ============================================================
    corp_base_raw = load_corp_bond_data(CONFIG["CORP_PATH"])

    universes = {
        "di": {
            "yields_ts": load_yield_surface(CONFIG["YA_PATH"]),
            "surface": load_di_surface(CONFIG["HIST_CURVE_PATH"]),
            "tenors": CONFIG["TENORS"],
            "inflation_linked": "N",
            "use_real_curve": False,
        },
        "ipca": {
            "yields_ts": load_yield_surface(CONFIG["YA_PATH"]),
            "surface": None,
            "tenors": CONFIG["REAL_CURVE_TENORS"],
            "inflation_linked": "Y",
            "use_real_curve": True,
        },
    }

    real_surface_corp = []  # armazenar todas superfícies corporativas

    for tipo, params in universes.items():
        log_path = f"data/logs_{tipo}.txt"

        with open(log_path, "w", encoding="utf-8") as log_file:
            def print_fn(*args, **kwargs):
                print(*args, **kwargs)
                print(*args, **kwargs, file=log_file)

            print_fn(f"\n📊 Processando universo: {tipo.upper()}")

            yields_ts = params["yields_ts"]
            tenors = params["tenors"]
            infl = params["inflation_linked"]

            corp_base = corp_base_raw.copy()
            corp_base = corp_base[corp_base["id"].isin(yields_ts.columns)]
            corp_base = filter_corporate_universe(corp_base, infl, log_file)

            print_fn(f"🧮 Bonds após filtro ({tipo}): {len(corp_base)}")

            obs_windows = build_observation_windows(
                corp_base, yields_ts, CONFIG["OBS_WINDOW"]
            )

            if tipo == "di":
                surface = params["surface"]
                yc_table = interpolate_di_surface(surface, tenors)

            else:
                surface_list = []
                common_dates = yields_ts.index.intersection(ntnb_ya_df.index)

                real_curve_cache = {}

                for obs_date in tqdm(common_dates, desc="Corporate IPCA Real Curve"):
                    if obs_date not in real_curve_cache:
                        real_curve_cache[obs_date] = build_real_curve_for_obs_date(
                            obs_date, ntnb_meta_df, ntnb_ya_df
                        )

                    real_curve = real_curve_cache[obs_date]
                    if real_curve is None:
                        continue

                    for label, t in CONFIG["REAL_CURVE_TENORS"].items():
                        surface_list.append(
                            {
                                "obs_date": obs_date,
                                "generic_ticker_id": label,
                                "yield": real_curve.yield_at(t),
                                "tenor": t,
                            }
                        )

                surface = pd.DataFrame(surface_list)
                real_surface_corp.append(surface)

                if surface.empty:
                    raise ValueError("Real IPCA surface (corporate) vazia.")

                yc_table = interpolate_surface(surface, tenors)

            # spreads
            corp_bonds, skipped = compute_spreads(
                corp_base, yields_ts, yc_table, obs_windows, tenors
            )

            print_fn(f"Spreads {tipo}: {len(corp_bonds)} (ignorados {len(skipped)})")

            corp_bonds = anomaly_filtering_results(corp_bonds)
            df_out = corp_bonds[
                ["id", "OBS_DATE", "YAS_BOND_YLD", "DI_YIELD", "SPREAD"]
            ].copy()
            df_out.columns = ["Bond ID", "Obs Date", "Corp Yield (%)", "DI Yield (%)", "Spread (bp)"]
            df_out = remove_unnamed(df_out)
            df_out.to_excel(f"data/corp_bonds_{tipo}_summary.xlsx", index=False)

    # SAVE REAL SURFACE CORPORATE
    if real_surface_corp:
        df_corp_real = pd.concat(real_surface_corp, ignore_index=True)
        df_corp_real = remove_unnamed(df_corp_real)
        df_corp_real.to_excel("data/real_curve_surface_corp.xlsx", index=False)

    # ============================================================
    # GOVERNMENT BONDS
    # ============================================================
    govt_base_raw = load_govt_bond_data(CONFIG["GOVT_PATH"])

    govt_universes = {
        "ltn": {"yields_ts": load_yield_surface(CONFIG["GOVT_YA_PATH"]),
                "use_real_curve": False,
                "tenors": CONFIG["TENORS"],
                "inflation_linked": "N",
                "bond_type": "LTN"},

        "di":  {"yields_ts": load_yield_surface(CONFIG["GOVT_YA_PATH"]),
                "use_real_curve": False,
                "tenors": CONFIG["TENORS"],
                "inflation_linked": "N",
                "bond_type": "NTNF"},

        "ipca": {"yields_ts": load_yield_surface(CONFIG["GOVT_YA_PATH"]),
                  "use_real_curve": True,
                  "tenors": CONFIG["REAL_CURVE_TENORS"],
                  "inflation_linked": "Y",
                  "bond_type": "NTNB"},
    }

    real_surface_govt = []

    for tipo, params in govt_universes.items():

        log_path = f"data/govt_logs_{tipo}.txt"
        with open(log_path, "w", encoding="utf-8") as log_file:

            def print_fn(*args, **kwargs):
                print(*args, **kwargs)
                print(*args, **kwargs, file=log_file)

            print_fn(f"\n📊 GOVT: {tipo.upper()}")

            yields_ts = params["yields_ts"]
            tenors = params["tenors"]

            govt_base = govt_base_raw.copy()
            govt_base = govt_base[govt_base["id"].isin(yields_ts.columns)]
            govt_base = filter_government_universe(
                govt_base, params["inflation_linked"], params["bond_type"], log_file
            )

            print_fn(f"Bonds após filtro ({tipo}): {len(govt_base)}")

            if tipo == "ltn":
                yc_table = interpolate_di_surface(load_di_surface(CONFIG["HIST_CURVE_PATH"]), tenors)

                if govt_base.empty:
                    continue

                govt_list = []
                for bid in govt_base["id"].unique():
                    if bid not in yields_ts.columns:
                        continue

                    df_sub = pd.DataFrame({
                        "id": bid,
                        "OBS_DATE": yields_ts.index,
                        "YAS_BOND_YLD": yields_ts[bid],
                    })
                    df_sub = df_sub.merge(govt_base[["id", "MATURITY"]], on="id", how="left")
                    govt_list.append(df_sub)

                if not govt_list:
                    continue

                df_exp = pd.concat(govt_list, ignore_index=True)
                govt_bonds = compute_spreads_ltn(df_exp, yc_table)
                govt_bonds = anomaly_filtering_results(govt_bonds, is_ltn=True)

                df_out = govt_bonds[["id", "OBS_DATE", "YAS_BOND_YLD", "DI_YIELD", "SPREAD"]]
                df_out.columns = ["Bond ID", "Obs Date", "Govt Yield (%)", "DI Yield (%)", "Spread (bp)"]
                df_out = remove_unnamed(df_out)
                df_out.to_excel("data/govt_bonds_ltn_summary.xlsx", index=False)
                continue

            # GOVERNMENT IPCA = REAL CURVE
            if tipo == "ipca":
                surface_list = []
                common_dates = yields_ts.index.intersection(ntnb_ya_df.index)

                real_curve_cache = {}

                for obs_date in tqdm(common_dates, desc="Govt IPCA Real Curve"):
                    if obs_date not in real_curve_cache:
                        real_curve_cache[obs_date] = build_real_curve_for_obs_date(
                            obs_date, ntnb_meta_df, ntnb_ya_df
                        )
                    real_curve = real_curve_cache[obs_date]
                    if real_curve is None:
                        continue
                    for label, t in CONFIG["REAL_CURVE_TENORS"].items():
                        surface_list.append(
                            {"obs_date": obs_date,
                             "generic_ticker_id": label,
                             "yield": real_curve.yield_at(t),
                             "tenor": t}
                        )

                surface = pd.DataFrame(surface_list)
                real_surface_govt.append(surface)

                if surface.empty:
                    raise ValueError("Real IPCA surface (govt) vazia.")

                yc_table = interpolate_surface(surface, tenors)

                govt_bonds, skipped = compute_spreads(
                    govt_base, yields_ts, yc_table,
                    build_observation_windows(govt_base, yields_ts, CONFIG["OBS_WINDOW"]),
                    tenors,
                )

                govt_bonds = anomaly_filtering_results(govt_bonds)
                df_out = govt_bonds[["id", "OBS_DATE", "YAS_BOND_YLD", "DI_YIELD", "SPREAD"]]
                df_out.columns = ["Bond ID", "Obs Date", "Govt Yield (%)", "DI Yield (%)", "Spread (bp)"]
                df_out = remove_unnamed(df_out)
                df_out.to_excel("data/govt_bonds_ipca_summary.xlsx", index=False)
                continue

            # GOVERNMENT DI
            yc_table = interpolate_di_surface(load_di_surface(CONFIG["HIST_CURVE_PATH"]), tenors)
            govt_bonds, skipped = compute_spreads(
                govt_base, yields_ts, yc_table,
                build_observation_windows(govt_base, yields_ts, CONFIG["OBS_WINDOW"]),
                tenors,
            )

            govt_bonds = anomaly_filtering_results(govt_bonds)
            df_out = govt_bonds[["id", "OBS_DATE", "YAS_BOND_YLD", "DI_YIELD", "SPREAD"]]
            df_out.columns = ["Bond ID", "Obs Date", "Govt Yield (%)", "DI Yield (%)", "Spread (bp)"]
            df_out = remove_unnamed(df_out)
            df_out.to_excel(f"data/govt_bonds_{tipo}_summary.xlsx", index=False)

    # SAVE REAL SURFACE GOVT
    if real_surface_govt:
        df_govt_real = pd.concat(real_surface_govt, ignore_index=True)
        df_govt_real = remove_unnamed(df_govt_real)
        df_govt_real.to_excel("data/real_curve_surface_govt.xlsx", index=False)

    # ============================================================
    # GENERATE WLA+NTNB SURFACE
    # ============================================================
    build_and_save_real_wla_ntnb_surface()

    # ============================================================
    # BENCHMARK MERGE (unchanged)
    # ============================================================
    df_di = pd.read_excel("data/govt_bonds_di_summary.xlsx")
    df_ipca = pd.read_excel("data/govt_bonds_ipca_summary.xlsx")
    df_ltn = pd.read_excel("data/govt_bonds_ltn_summary.xlsx")

    df_di["TYPE"] = "NTNF"
    df_ipca["TYPE"] = "NTNB"
    df_ltn["TYPE"] = "LTN"

    govt_all = pd.concat([df_ltn, df_di, df_ipca], ignore_index=True)
    govt_data = load_govt_bond_data(CONFIG["GOVT_PATH"])[["id", "MATURITY"]]

    govt_all = govt_all.merge(govt_data, left_on="Bond ID", right_on="id", how="left")
    govt_all["Maturity"] = govt_all["MATURITY"]
    govt_all.drop(columns=["MATURITY", "id"], inplace=True)

    DAYCOUNT = DayCounts("bus/252", calendar="cdr_anbima")
    govt_all["Days to Maturity"] = govt_all.apply(
        lambda r: DAYCOUNT.days(r["Obs Date"], r["Maturity"]) / 252
        if pd.notna(r["Obs Date"]) and pd.notna(r["Maturity"]) else None,
        axis=1
    )

    govt_all.to_excel("data/govt_bonds_all_consolidated.xlsx", index=False)

    benchmarks = govt_all[["Bond ID", "TYPE", "Maturity", "Days to Maturity"]].drop_duplicates()
    benchmarks.to_excel("data/govt_benchmark_summary_table.xlsx", index=False)

    html_output = show_benchmark_table(benchmarks)
    with open("templates/govt_benchmark_summary_table.html", "w", encoding="utf-8") as f:
        f.write(html_output)