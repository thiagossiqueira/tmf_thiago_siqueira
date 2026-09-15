# src/utils/file_io.py

import pandas as pd

def load_yield_surface(path):
    df = pd.read_excel(path, sheet_name="ya_values_only")
    df.rename(columns={df.columns[0]: "OBS_DATE"}, inplace=True)
    df["OBS_DATE"] = pd.to_datetime(df["OBS_DATE"])
    df = df.set_index("OBS_DATE").sort_index()

    # Manter " Corp" nos IDs
    df.columns = df.columns.astype(str).str.strip()
    return df

def load_corp_bond_data(path):
    df = pd.read_excel(path, sheet_name="db_values_only")
    df["id"] = df["id"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["id"])
    return df

def load_govt_bond_data(path):
    """
    Carrega a base de dados de títulos soberanos e padroniza campos-chave.
    Inclui mapeamento CALC_TYP_DES → SECURITY_TYP (LTN, NTNF, NTNB, LFT).
    """
    df = pd.read_excel(path, sheet_name="db_values_only")

    # Padronização básica
    df["id"] = df["id"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["id"])

    # Garante que CRNCY e CPN_TYP existam (evita erro no filtro)
    for col in ["CRNCY", "CPN_TYP", "INFLATION_LINKED_INDICATOR"]:
        if col not in df.columns:
            df[col] = None

    # -----------------------------------------------------------
    # 🔧 Mapeamento CALC_TYP_DES → SECURITY_TYP
    # -----------------------------------------------------------
    if "CALC_TYP_DES" in df.columns:
        df["CALC_TYP_DES"] = df["CALC_TYP_DES"].astype(str).str.upper().str.strip()

        mapping = {
            "BRAZIL: BBCS/LTNS": "LTN",
            "BRAZIL BBCS/LTNS": "LTN",
            "BRAZIL LFT ANN-OVR": "LFT",
            "BRAZIL FIXED CPN": "NTNF",
            "BRAZIL I/L BOND": "NTNB",
        }

        df["SECURITY_TYP"] = df["CALC_TYP_DES"].map(mapping)
    else:
        df["SECURITY_TYP"] = None

    # Fallback: se CALC_TYP_DES não existir, tenta usar 'papel'
    if df["SECURITY_TYP"].isna().all() and "papel" in df.columns:
        df["SECURITY_TYP"] = df["papel"].astype(str).str.upper().str.strip()

    return df

def load_di_surface(path):
    curve_df = pd.read_excel(path, sheet_name="only_values")
    curve_df["Curve date"] = pd.to_datetime(curve_df["Curve date"])

    surface = curve_df.rename(columns={
        "Curve date": "obs_date",
        "Generic ticker": "generic_ticker_id",
        "Term": "tenor",
        "px_last": "yield"
    })[["obs_date", "generic_ticker_id", "yield", "tenor"]].copy()

    if "volume" in curve_df.columns:
        surface["volume"] = pd.to_numeric(curve_df["volume"], errors="coerce")
        surface = surface.dropna(subset=["volume"])
        surface = surface[surface["volume"] > 1000]

    surface = surface.dropna(subset=["yield", "tenor"])
    surface = surface[surface["yield"] > 0]
    surface["curve_id"] = surface["generic_ticker_id"] + surface["obs_date"].dt.strftime("%Y%m%d")
    surface = surface.drop_duplicates(subset=["curve_id"], keep="last")

    return surface

def load_ipca_surface(path):
    """
    Load the historical WLA / DAP real-rate surface.

    Bloomberg/B3 DAP quotes are stored in percentage points
    (e.g. 7.46 = 7.46%). They are converted here to decimal
    rates (0.0746) because the curve interpolation functions
    operate on decimal rates.

    Zero and negative real rates are valid observations and
    must not be removed. Only rows with missing yield or tenor
    are excluded.
    """

    df = pd.read_excel(
        path,
        sheet_name="only_values"
    )

    df["Curve date"] = pd.to_datetime(
        df["Curve date"]
    )

    surface = df.rename(
        columns={
            "Curve date": "obs_date",
            "Generic ticker": "generic_ticker_id",
            "Term": "tenor",
            "px_last": "yield",
        }
    )[
        [
            "obs_date",
            "generic_ticker_id",
            "yield",
            "tenor",
        ]
    ].copy()

    # Ensure numeric fields
    surface["yield"] = pd.to_numeric(
        surface["yield"],
        errors="coerce"
    )

    surface["tenor"] = pd.to_numeric(
        surface["tenor"],
        errors="coerce"
    )

    # Remove only genuinely unavailable observations
    surface = surface.dropna(
        subset=[
            "yield",
            "tenor",
        ]
    )

    # Bloomberg/B3:
    # 7.46 means 7.46%
    #
    # Curve mathematics:
    # 0.0746 means 7.46%
    surface["yield"] = surface["yield"] / 100.0

    # Unique observation identifier
    surface["curve_id"] = (
        surface["generic_ticker_id"].astype(str)
        + surface["obs_date"].dt.strftime("%Y%m%d")
    )

    surface = surface.drop_duplicates(
        subset=["curve_id"],
        keep="last"
    )

    return surface