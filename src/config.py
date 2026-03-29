# config.py
from pathlib import Path

# Detecta o diretório raiz do projeto automaticamente
REPO_ROOT = Path(__file__).resolve()
while not (REPO_ROOT / ".git").exists() and REPO_ROOT != REPO_ROOT.parent:
    REPO_ROOT = REPO_ROOT.parent

# Caminhos centralizados para os arquivos de dados
CONFIG = {
    "CORP_PATH": REPO_ROOT / "datos_y_modelos" / "Domestic" / "universo_brazil_deb_des.xlsx",
    "GOVT_PATH": REPO_ROOT / "datos_y_modelos" / "Domestic" / "domestic_sovereign_curve_brazil.xlsx",
    "YA_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "brazil_domestic_corp_bonds" / "ya.v1.xlsx",
    "GOVT_YA_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "brazil_domestic_govt_bonds" / "govt_ya.v1.xlsx",
    "HIST_CURVE_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "one-day_interbank_deposit_futures_contract_di" / "hist_di_curve_contracts_db.v1.xlsx",
    "WLA_CURVE_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "id_x_ipca_spread_futures" / "hist_ipca_curve_contracts_db.xlsx",
    "SYNTHETIC_CDS_PATH": REPO_ROOT / "data" / "synthetic_cds_brl_surface.xlsx",
    "PANEL_DATA_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "output_panel_data" / "panel_data.xlsx",
    "PANEL_DATA_OUTPUT_PATH": REPO_ROOT / "datos_y_modelos" / "db" / "output_panel_data" / "panel_data_with_cds.xlsx",

    "SOVEREIGN_REAL_CURVE": {
    "path": REPO_ROOT / "datos_y_modelos" / "Domestic" / "domestic_sovereign_curve_brazil.xlsx",
    "sheet_name": "db_values_only",
    "use_nss": True,
    },


    "TENORS": {
        "12-year": 12.0,
        "11-year": 11.0,
        "10-year": 10.0,
        "9-year": 9.0,
        "8-year": 8.0,
        "7-year": 7.0,
        "6-year": 6.0,
        "5-year": 5.0,
        "3-year": 3.0,
        "2-year": 2.0,
        "1-year": 1.0,
        "6-month": 0.5,
        "3-month": 0.25,
        "1-month": 1.0 / 12,
        "1-day": 1.0 / 252,
    },

    "WLA_TENORS": {
        "3-month": 0.25,
        "6-month": 0.5,
        "1-year": 1.0,
        "2-year": 2.0,
        "3-year": 3.0,
        "4-year": 4.0,
        "5-year": 5.0
    },

    "REAL_CURVE_TENORS": {
        "1-year": 1.0,
        "2-year": 2.0,
        "3-year": 3.0,
        "4-year": 4.0,
        "5-year": 5.0,
        "7-year": 7.0,
        "10-year": 10.0,
        "15-year": 15.0,
        "20-year": 20.0,
        "25-year": 25.0,
        "30-year": 30.0,
    },


    "OBS_WINDOW": 11323  # total days since [(2025 - 1994) x 365.25] >>> CONFIG["OBS_WINDOW"] = int((pd.Timestamp.today() - pd.Timestamp("1994-01-01")).days)


}