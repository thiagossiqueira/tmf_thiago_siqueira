from pathlib import Path
import json
from flask import Flask, render_template, send_file
import pandas as pd
import os


# ========================================================================
# REAL IPCA SURFACE (WLA + NTNB) — FULL REVISED ROUTE
# ========================================================================

app = Flask(__name__, template_folder="templates")

PUBLIC_DEPLOYMENT = os.getenv("PUBLIC_DEPLOYMENT", "0") == "1"
SENSITIVE_ARTIFACT_KEYS = {"panel_input", "wp12c_leverage_csv"}

@app.context_processor
def deployment_context():
    return {"public_deployment": PUBLIC_DEPLOYMENT}



# ----------- PÁGINA INICIAL ------------------------
@app.route("/")
def index():
    dashboard_status = {
        "wla_ntnb_surface": os.path.exists("templates/wla_ntnb_surface.html"),
        "wla_ntnb_data": os.path.exists("data/real_curve_surface_govt.xlsx"),

        "di_surface": os.path.exists("templates/di_surface.html"),
        "ipca_surface_legacy": os.path.exists("templates/ipca_surface.html"),

        "spread_di_surface": os.path.exists("templates/di_spread_surface.html"),
        "spread_ipca_surface": os.path.exists("templates/ipca_spread_surface.html"),
        "spread_di_table": os.path.exists("templates/summary_DI_table.html"),
        "spread_ipca_table": os.path.exists("templates/summary_IPCA_table.html"),

        "summary_di": os.path.exists("templates/di_summary_table.html"),
        "summary_ipca": os.path.exists("templates/ipca_summary_table.html"),
        "benchmark_summary": os.path.exists("templates/benchmark_summary_table.html"),

        "sov_di_surface": os.path.exists("templates/govt_di_surface.html"),
        "sov_ipca_surface": os.path.exists("templates/govt_ipca_surface.html"),
        "sov_di_spread": os.path.exists("templates/govt_di_spread_surface.html"),
        "sov_ipca_spread": os.path.exists("templates/govt_ipca_spread_surface.html"),
        "sov_benchmark_summary": os.path.exists("templates/govt_benchmark_summary_table.html"),

        "brl_risk_surface": os.path.exists("templates/brl_risk_spread_surface.html"),
        "brl_risk_table": os.path.exists("templates/brl_risk_summary.html"),

        "corp_summary": os.path.exists("data/corp_bonds_summary.xlsx"),
        "panel_input": os.path.exists(
            "datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt_v4.xlsx"
        ),
    }

    return render_template(
        "index.html",
        status=dashboard_status
    )

# ----------- SPREADS SUPERFÍCIE 3D -----------------
@app.route("/spread/<prefixo>")
def spread(prefixo):
    if prefixo not in ["di", "ipca"]:
        prefixo = "di"
    return send_file(f"templates/{prefixo}_spread_surface.html")


# ----------- TABELAS DOS SPREADS ------------------
@app.route("/spread-table/<prefixo>")
def spread_table(prefixo):
    file_map = {
        "di": "summary_DI_table.html",
        "ipca": "summary_IPCA_table.html"
    }
    if prefixo not in file_map:
        prefixo = "di"
    return send_file(f"templates/{file_map[prefixo]}")


# ----------- TABELAS DAS CURVAS INTERPOLADAS ------
@app.route("/summary/<prefixo>")
def summary(prefixo):
    if prefixo == "di":
        return send_file("templates/di_summary_table.html")
    elif prefixo == "ipca":
        return send_file("templates/ipca_summary_table.html")
    else:
        return "Tipo inválido", 400

# ----------- CURVAS DI e IPCA (WLA) ----------------
@app.route("/surface/<tipo>")
def surface(tipo):
    if tipo == "di":
        return render_template("di_surface.html")
    elif tipo == "ipca":
        return send_file("templates/ipca_surface.html")
    elif tipo == "wla_ntnb":
        return render_template("wla_ntnb_surface.html")
    else:
        return "Tipo inválido", 400


# ----------- FULL TABLES (Opcional) ----------------
@app.route("/summary-full")
def summary_full():
    df = pd.read_excel("data/corp_bonds_summary.xlsx")
    return render_template("summary_full.html", summary_data=df.to_dict(orient="records"))


@app.route("/wla-summary-full")
def wla_summary_full():
    with open("templates/ipca_summary_table.html") as f:
        content = f.read()
    return render_template("ipca_summary_full.html", table_html=content)



@app.route("/di-curve/download")
def di_curve_download():
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403
    file_path = "data/di_surface_with_provenance.xlsx"

    if not os.path.exists(file_path):
        return "Archivo DI con procedencia no encontrado.", 404

    return send_file(
        file_path,
        download_name="di_surface_with_provenance.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/wla-ntnb/download")
def wla_ntnb_download():
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403
    file_path = "data/wla_ntnb_surface_with_provenance.xlsx"

    if not os.path.exists(file_path):
        return "Archivo WLA+NTNB con procedencia no encontrado.", 404

    return send_file(
        file_path,
        download_name="wla_ntnb_surface_with_provenance.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ----------- DOWNLOAD DE EXCEL ---------------------
@app.route("/download/<prefixo>")
def download(prefixo):
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403
    if prefixo == "di":
        return send_file(
            "data/corp_bonds_di_summary.xlsx",
            download_name="corp_bonds_di_summary.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    elif prefixo == "ipca":
        return send_file(
            "data/final_spread_backing_v4.xlsx",
            download_name="final_spread_backing_v4.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    elif prefixo == "benchmark":
        return send_file(
            "data/benchmark_summary_table.xlsx",
            download_name="benchmark_summary_table.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        return "Tipo inválido", 400

@app.route("/benchmark-summary")
def benchmark_summary():
    return render_template("benchmark_summary_table.html")


#check later
# 3D Surface Chart (already done for DI, do for IPCA too)
@app.route("/sov_surface/<prefixo>")
def sov_surface(prefixo):
    if prefixo not in ["di", "ipca"]:
        prefixo = "di"
    return send_file(f"templates/govt_{prefixo}_surface.html")

# Spread Charts (3D spread charts)
@app.route("/sov_spread/<prefixo>")
def sov_spread(prefixo):
    if prefixo not in ["di", "ipca"]:
        prefixo = "di"
    return send_file(f"templates/govt_{prefixo}_spread_surface.html")

# Spread Tables (HTML)
@app.route("/sov-spread-table/<prefixo>")
def sov_spread_table(prefixo):
    if prefixo not in ["di", "ipca"]:
        prefixo = "di"
    return send_file(f"templates/govt_summary_{prefixo.upper()}_table.html")

# Table Downloads (XLSX)
@app.route("/sov-download/<prefixo>")
def sov_download(prefixo):
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403
    if prefixo not in ["di", "ipca"]:
        return "Tipo inválido", 400
    return send_file(
        f"data/govt_bonds_{prefixo}_summary.xlsx",
        download_name=f"govt_bonds_{prefixo}_summary.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Final benchmark summary
@app.route("/sov-benchmark-summary")
def sov_benchmark_summary():
    return render_template("govt_benchmark_summary_table.html")

# ✅ nova rota: download do consolidado de títulos soberanos
@app.route("/sov-download/all")
def download_govt_all():
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403
    """
    Permite baixar o arquivo consolidado de títulos soberanos (LTN + NTNF + NTNB).
    """
    file_path = "data/govt_bonds_all_consolidated.xlsx"
    if not os.path.exists(file_path):
        return "❌ Arquivo govt_bonds_all_consolidated.xlsx não encontrado.", 404
    return send_file(
        file_path,
        download_name="govt_bonds_all_consolidated.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- Spread soberano BRL por tenor ---
@app.route("/brl-risk/surface")
def brl_risk_surface():
    return send_file("templates/brl_risk_spread_surface.html")

@app.route("/brl-risk/table")
def brl_risk_table():
    return send_file("templates/brl_risk_summary.html")

@app.route("/brl-risk/download")
def brl_risk_download():
    return (
        "Direct sovereign-spread workbook download is disabled. "
        "The source artifact is retained for audit and provenance only.",
        410,
    )

# --- Retired legacy sovereign-risk panel endpoint ---
@app.route("/panel-cds/download")
def panel_cds_download():
    return (
        "Legacy sovereign-risk panel endpoint retired. "
        "Use the final econometric panel and sovereign_spread_brl instead.",
        410,
    )


# ---------------------------------------------------------
# NOVA ROTA — JSON da curva real (WLA + NTNB)
# ---------------------------------------------------------
@app.route("/data/wla_ntnb")
def data_wla_ntnb():
    if PUBLIC_DEPLOYMENT:
        return "Datos detallados deshabilitados en el despliegue p?blico.", 403
    path = "data/real_curve_surface_govt.xlsx"
    if not os.path.exists(path):
        return "Arquivo real_curve_surface_govt.xlsx não encontrado. Rode main.py.", 500

    df = pd.read_excel(path)

    # ensure expected columns
    if not {"obs_date", "tenor", "yield"}.issubset(df.columns):
        return "Arquivo inválido. Esperado colunas: obs_date, tenor, yield.", 500

    df["obs_date"] = pd.to_datetime(df["obs_date"], errors="coerce")
    df["tenor"] = pd.to_numeric(df["tenor"], errors="coerce")

    df = df.dropna(subset=["obs_date", "tenor", "yield"])

    # pivot tenor → columns
    pivot = df.pivot_table(
        index="obs_date",
        columns="tenor",
        values="yield",
        aggfunc="mean"
    ).sort_index()

    # sort tenor columns numerically
    tenor_cols_sorted = sorted(pivot.columns.tolist())

    # rename columns as strings
    pivot.columns = [str(c) for c in tenor_cols_sorted]

    # convert index to string for JSON purposes
    out = [
        {"obs_date": str(idx), **{str(col): float(val) for col, val in row.items()}}
        for idx, row in pivot.iterrows()
    ]

    # also display a small debug HTML table
    html = "<h3>WLA + NTNB Surface Data</h3>"
    html += f"<p>Tenor columns detected: {', '.join(str(t) for t in tenor_cols_sorted)}</p>"
    html += pivot.tail(20).round(4).to_html(classes='table table-striped')

    return html


# ========================================================================
# JURY DASHBOARD — FROZEN ECONOMETRIC ARTIFACTS
# ========================================================================

ECON_ARTIFACTS = {
    # Principal specification — WP-12C
    "wp12c_table": {
        "label": "WP-12C — Tabla principal M1–M8",
        "path": "src/econometrics/wp12c_reestimation/Table5_Final_Eight_Models_Total_Debt_Assets_FE_DK.txt",
        "group": "Principal",
    },
    "wp12c_do": {
        "label": "WP-12C — Stata .do",
        "path": "src/econometrics/wp12c_final_m1_m8_total_debt_assets_fe_dk.do",
        "group": "Principal",
    },
    "wp12c_log": {
        "label": "WP-12C — Stata log",
        "path": "src/econometrics/wp12c_reestimation/WP12C_Final_M1_M8_Total_Debt_Assets_FE_DK.log",
        "group": "Principal",
    },
    "wp12c_audit": {
        "label": "WP-12C — Auditoría del fallback de leverage",
        "path": "output/Informes jurado/wp12c_director_specified_leverage_fallback_audit.txt",
        "group": "Principal",
    },
    "wp12c_coverage": {
        "label": "WP-12C — Auditoría de cobertura Total Debt / Total Assets",
        "path": "output/Informes jurado/wp12c_total_debt_to_total_assets_coverage_audit.txt",
        "group": "Principal",
    },
    "wp12c_leverage_csv": {
        "label": "WP-12C — Serie Total Debt / Total Assets",
        "path": "output/Informes jurado/WP12C_total_debt_to_total_assets_4648.csv",
        "group": "Principal",
    },

    # Annex A — leverage robustness
    "wp12a_table": {
        "label": "WP-12A — Robustez de leverage",
        "path": "src/econometrics/wp12a_reestimation/Table5_Final_Eight_Models_No_Trading_Days_FE_DK.txt",
        "group": "Anexo A",
    },
    "wp12a_do": {
        "label": "WP-12A — Stata .do",
        "path": "src/econometrics/wp12a_final_m1_m8_no_trading_days_fe_dk.do",
        "group": "Anexo A",
    },
    "wp12a_log": {
        "label": "WP-12A — Stata log",
        "path": "src/econometrics/wp12a_reestimation/WP12A_Final_M1_M8_No_Trading_Days_FE_DK.log",
        "group": "Anexo A",
    },

    # Annex B — SND bond-liquidity robustness
    "wp12b_table": {
        "label": "WP-12B — Robustez de liquidez SND",
        "path": "src/econometrics/wp12b_reestimation/WP12B_SND_Liquidity_Annex_M1_M8_FE_DK.txt",
        "group": "Anexo B",
    },
    "wp12b_do": {
        "label": "WP-12B — Stata .do",
        "path": "src/econometrics/wp12b_snd_liquidity_annex_fe_dk.do",
        "group": "Anexo B",
    },
    "wp12b_log": {
        "label": "WP-12B — Stata log",
        "path": "src/econometrics/wp12b_reestimation/WP12B_SND_Liquidity_Annex_FE_DK.log",
        "group": "Anexo B",
    },

    # DK sensitivity — WP-07
    "wp07_table": {
        "label": "WP-07 — Sensibilidad del bandwidth Driscoll–Kraay",
        "path": "src/econometrics/wp07_reestimation/Table5_WP07_FE_DK.txt",
        "group": "Diagnósticos",
    },
    "wp07_do": {
        "label": "WP-07 — Stata .do",
        "path": "src/econometrics/wp07_dk_bandwidth_sensitivity.do",
        "group": "Diagnósticos",
    },
    "wp07_log": {
        "label": "WP-07 — Stata log",
        "path": "src/econometrics/wp07_reestimation/wp07_dk_bandwidth_sensitivity.log",
        "group": "Diagnósticos",
    },
    "wp07_audit": {
        "label": "WP-07 — Auditoría de sensibilidad DK",
        "path": "output/Informes jurado/wp07_dk_bandwidth_sensitivity_audit.txt",
        "group": "Diagnósticos",
    },

    # Frozen econometric input
    "panel_input": {
        "label": "Panel econométrico congelado",
        "path": "datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt_v4.xlsx",
        "group": "Inputs",
    },
}


def _econometric_artifact_manifest():
    manifest = []
    for key, meta in ECON_ARTIFACTS.items():
        item = dict(meta)
        item["key"] = key
        item["exists"] = os.path.exists(meta["path"])
        manifest.append(item)
    return manifest


@app.route("/transparency")
def transparency():
    manifest_path = Path(
        "data/variable_provenance_manifest.json"
    )
    figures_path = Path(
        "data/thesis_figure_manifest.csv"
    )

    if not manifest_path.exists():
        return "Variable provenance manifest not found.", 404

    if not figures_path.exists():
        return "Thesis figure manifest not found.", 404

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    figures_df = pd.read_csv(figures_path)
    figures = figures_df.to_dict(orient="records")

    for figure in figures:
        output_file = Path(figure["output_file"])

        try:
            figure["static_file"] = (
                output_file
                .relative_to("static")
                .as_posix()
            )
        except ValueError:
            return (
                "Figure path is outside the static directory: "
                f"{output_file}"
            ), 500

    return render_template(
        "transparency.html",
        final_panel=manifest["final_panel"],
        variables=manifest["variables"],
        figures=figures,
    )


@app.route("/econometrics")
def econometrics():
    return render_template(
        "econometrics.html",
        artifacts=_econometric_artifact_manifest()
    )


@app.route("/artifact/view/<key>")
def artifact_view(key):
    meta = ECON_ARTIFACTS.get(key)
    if meta is None:
        return "Artefacto no permitido.", 404

    if PUBLIC_DEPLOYMENT and key in SENSITIVE_ARTIFACT_KEYS:
        return "Visualizaci?n deshabilitada en el despliegue p?blico.", 403

    file_path = meta["path"]
    if not os.path.exists(file_path):
        return f"Archivo no encontrado: {file_path}", 404

    suffix = Path(file_path).suffix.lower()
    if suffix not in {".txt", ".log", ".do", ".csv"}:
        return "Este tipo de archivo está disponible solo para descarga.", 400

    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return render_template(
        "artifact_view.html",
        artifact=meta,
        artifact_key=key,
        content=content
    )


@app.route("/artifact/download/<key>")
def artifact_download(key):
    meta = ECON_ARTIFACTS.get(key)
    if meta is None:
        return "Artefacto no permitido.", 404

    if PUBLIC_DEPLOYMENT and key in SENSITIVE_ARTIFACT_KEYS:
        return "Descarga deshabilitada en el despliegue p?blico.", 403

    file_path = meta["path"]
    if not os.path.exists(file_path):
        return f"Archivo no encontrado: {file_path}", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path)
    )


@app.route("/spread-transparency")
def spread_transparency():
    return render_template("spread_transparency.html")


@app.route("/spread-transparency/download")
def spread_transparency_download():
    if PUBLIC_DEPLOYMENT:
        return "Descarga deshabilitada en el despliegue p?blico.", 403

    file_path = "data/final_spread_backing_v4.xlsx"
    if not os.path.exists(file_path):
        return "Spread backing file not found.", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name="final_spread_backing_v4.xlsx"
    )


if __name__ == "__main__":
    app.run(debug=True)

