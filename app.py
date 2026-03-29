from flask import Flask, render_template, send_file
from routes.filters_routes import filters_blueprint
import pandas as pd
import numpy as np
import os

from datetime import datetime
from markupsafe import Markup
from src.config import CONFIG

# ========================================================================
# REAL IPCA SURFACE (WLA + NTNB) — FULL REVISED ROUTE
# ========================================================================
from src.utils.file_io import load_ipca_surface
from src.utils.interpolation import interpolate_surface

app = Flask(__name__, template_folder="templates")
app.register_blueprint(filters_blueprint)


# ----------- PÁGINA INICIAL ------------------------
@app.route("/")
def index():
    logs_di = logs_ipca = ""
    try:
        with open("data/logs_di.txt", "r", encoding="utf-8") as f:
            logs_di = f.read()
        with open("data/logs_ipca.txt", "r", encoding="utf-8") as f:
            logs_ipca = f.read()
    except FileNotFoundError:
        logs_di = "⚠️ Logs DI não encontrados."
        logs_ipca = "⚠️ Logs IPCA não encontrados."
    return render_template("index.html", logs_di=logs_di, logs_ipca=logs_ipca)

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
        return send_file("templates/di_surface.html")
    elif tipo == "ipca":
        return send_file("templates/ipca_surface.html")
    elif tipo == "wla_ntnb":
        return send_file("templates/wla_ntnb_surface.html")
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


# ----------- DOWNLOAD DE EXCEL ---------------------
@app.route("/download/<prefixo>")
def download(prefixo):
    if prefixo == "di":
        return send_file(
            "data/corp_bonds_di_summary.xlsx",
            download_name="corp_bonds_di_summary.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    elif prefixo == "ipca":
        return send_file(
            "data/corp_bonds_ipca_summary.xlsx",
            download_name="corp_bonds_ipca_summary.xlsx",
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

# --- BRL synthetic risk (CDS-BRL) ---
@app.route("/brl-risk/surface")
def brl_risk_surface():
    return send_file("templates/brl_risk_spread_surface.html")

@app.route("/brl-risk/table")
def brl_risk_table():
    return send_file("templates/brl_risk_summary.html")

@app.route("/brl-risk/download")
def brl_risk_download():
    return send_file(
        "data/synthetic_cds_brl_surface.xlsx",
        download_name="synthetic_cds_brl_surface.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- Synthetic CDS-BRL applied to corporate panel ---
@app.route("/panel-cds/download")
def panel_cds_download():
    """
    Permite descargar el panel de bonos corporativos con la columna Synthetic_CDS_BRL agregada.
    """
    file_path = "datos_y_modelos/db/output_panel_data/panel_data_with_cds.xlsx"
    try:
        return send_file(
            file_path,
            download_name="panel_data_with_cds.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except FileNotFoundError:
        return "❌ Archivo panel_data_with_cds.xlsx no encontrado.", 404


# ---------------------------------------------------------
# NOVA ROTA — JSON da curva real (WLA + NTNB)
# ---------------------------------------------------------
@app.route("/data/wla_ntnb")
def data_wla_ntnb():
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

if __name__ == "__main__":
    app.run(debug=True)
