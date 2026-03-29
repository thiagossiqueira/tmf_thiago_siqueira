# synthetic_cds_brl.py
import os
import numpy as np
import pandas as pd

from calendars.daycounts import DayCounts
from src.config import CONFIG
from src.utils.plotting import plot_surface_spread_with_bonds

DAYCOUNT = DayCounts("bus/252", calendar="cdr_anbima")


def _nearest_bucket(x: float, names, vals):
    """Retorna o nome do bucket mais próximo do tenor em anos x"""
    if np.isnan(x):
        return None
    idx = int(np.argmin(np.abs(vals - x)))
    return names[idx]


def build_and_save_synthetic_cds_surface(
    consolidated_path="data/govt_bonds_all_consolidated.xlsx",
    html_out="templates/brl_risk_spread_surface.html",
    xlsx_out="data/synthetic_cds_brl_surface.xlsx",
    summary_out="templates/brl_risk_summary.html",
    zmin=-200, zmax=1000
):
    # -------- carregamento
    if not os.path.exists(consolidated_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {consolidated_path}")

    df = pd.read_excel(consolidated_path)

    # normaliza datas/colunas esperadas
    df.rename(
        columns={
            "Bond ID": "id",
            "Obs Date": "OBS_DATE",
            "Govt Yield (%)": "GOVT_YLD",
            "DI Yield (%)": "RF_YLD",  # DI p/ LTN/NTNF e WLA/IPCA p/ NTNB
            "Spread (bp)": "SPREAD_BP",
            "Days to Maturity": "TENOR_YRS",
        },
        inplace=True,
    )

    # datas
    df["OBS_DATE"] = pd.to_datetime(df["OBS_DATE"], errors="coerce")

    # se não houver TENOR_YRS (anos úteis 252), tenta calcular a partir de Maturity
    if "TENOR_YRS" not in df.columns or df["TENOR_YRS"].isna().all():
        if "Maturity" in df.columns:
            df["Maturity"] = pd.to_datetime(df["Maturity"], errors="coerce")
            df["TENOR_YRS"] = df.apply(
                lambda r: DAYCOUNT.days(r["OBS_DATE"], r["Maturity"]) / 252
                if pd.notna(r["OBS_DATE"]) and pd.notna(r["Maturity"])
                else np.nan,
                axis=1,
            )
        else:
            raise ValueError("Não há 'Days to Maturity' nem 'Maturity' para calcular TENOR_YRS.")

    # remove linhas inválidas
    df = df.dropna(subset=["OBS_DATE", "TENOR_YRS", "SPREAD_BP"])

    # --------- bucketing de tenores (une DI e IPCA/WLA)
    tenors_all = dict(CONFIG["TENORS"])
    tenors_all.update(CONFIG.get("WLA_TENORS", {}))
    names = list(tenors_all.keys())
    vals = np.array(list(tenors_all.values()), dtype=float)

    df["TENOR_BUCKET"] = df["TENOR_YRS"].astype(float).apply(
        lambda x: _nearest_bucket(x, names, vals)
    )

    # --------- dataframe de auditoria (para overlay no gráfico)
    audit = df[["id", "OBS_DATE", "TENOR_BUCKET", "SPREAD_BP"]].copy()
    audit.rename(columns={"SPREAD_BP": "SPREAD"}, inplace=True)

    # adiciona colunas opcionais vazias (para compatibilidade com plotting)
    for col in ["CPN_TYP", "CPN", "MATURITY"]:
        if col not in audit.columns:
            audit[col] = ""

    # --------- superfície: média do spread por data x bucket
    surface = (
        df.pivot_table(
            index="OBS_DATE", columns="TENOR_BUCKET", values="SPREAD_BP", aggfunc="mean"
        )
        .sort_index()
    )

    # ordena colunas no eixo de tenores
    tenor_order = sorted(tenors_all.items(), key=lambda x: x[1])
    ordered_cols = [k for k, _ in tenor_order if k in surface.columns]
    surface = surface[ordered_cols]

    # --------- salva uma planilha com a superfície
    os.makedirs("data", exist_ok=True)
    surface.to_excel(xlsx_out)

    # --------- salva um resumo HTML (tabela simples)
    os.makedirs("templates", exist_ok=True)
    summary_html = surface.tail(30).round(2).to_html(
        border=0, classes="table table-striped", index=True
    )
    with open(summary_out, "w", encoding="utf-8") as f:
        f.write(summary_html)

    # --------- plota a superfície 3D (reuso do plot existente)
    fig = plot_surface_spread_with_bonds(
        df_surface=surface,
        audit=audit,
        title="Sovereign BRL Risk (Synthetic) – Spread Surface (bp)",
        zmin=zmin,
        zmax=zmax,
    )
    fig.write_html(html_out)

    print(f"✅ Superfície salva em: {html_out}")
    print(f"✅ Excel salvo em: {xlsx_out}")
    print(f"✅ Resumo (tabela) salvo em: {summary_out}")
    return surface, audit


if __name__ == "__main__":
    build_and_save_synthetic_cds_surface()
