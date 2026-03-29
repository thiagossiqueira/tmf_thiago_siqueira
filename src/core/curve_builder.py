# src/core/curve_builder.py

import pandas as pd
import numpy as np

from calendars.daycounts import DayCounts
from src.utils.file_io import load_govt_bond_data, load_yield_surface
from src.config import CONFIG
from src.finmath.termstructure.ntnb_real_curve import (
    load_ntnb_metadata,
    build_real_curve_for_date,
)
from src.finmath.termstructure.combined_real_curve import CombinedRealCurve

DAYCOUNT_BUS252 = DayCounts("bus/252", calendar="cdr_anbima")

# -------------------------------------------------------------------
# WLA cache (carregado uma única vez para todas as datas)
# -------------------------------------------------------------------
_WLA_YC_TABLE: pd.DataFrame | None = None  # index: OBS_DATE, columns: t_years (float)


def _load_wla_yc_table() -> pd.DataFrame:
    """
    Carrega e interpola a curva WLA IPCA apenas uma vez.

    Resultado: DataFrame com:
      - index: datas (OBS_DATE)
      - columns: tenores em anos (float), ex: 0.25, 0.5, 1.0, 2.0, ...
    """
    global _WLA_YC_TABLE
    if _WLA_YC_TABLE is not None:
        return _WLA_YC_TABLE

    from src.utils.file_io import load_ipca_surface
    from src.utils.interpolation import interpolate_surface

    # Carrega a surface bruta (WLA IPCA)
    surface = load_ipca_surface(CONFIG["WLA_CURVE_PATH"])
    tenors = CONFIG["WLA_TENORS"]  # ex: {"3-month": 0.25, "6-month": 0.5, ...}

    # Interpola usando infra existente (mesma usada antes)
    yc_table_raw = interpolate_surface(surface, tenors)
    # yc_table_raw.index -> datas
    # yc_table_raw.columns -> labels ("3-month", "6-month", ...)

    # Mapeia colunas para anos (float)
    col_map = {}
    for label, t_years in tenors.items():
        if label in yc_table_raw.columns:
            col_map[label] = float(t_years)

    if not col_map:
        # Nenhuma coluna bateu; melhor falhar explicitamente
        raise ValueError("WLA interpolation returned no matching tenor columns.")

    yc_numeric = yc_table_raw[list(col_map.keys())].copy()
    yc_numeric = yc_numeric.rename(columns=col_map)  # agora colunas são floats (t_years)
    yc_numeric = yc_numeric.sort_index()  # ordena por data, por segurança

    _WLA_YC_TABLE = yc_numeric
    return _WLA_YC_TABLE


# ============================================================
# 1. Carregar metadados + YA de NTNB, já alinhados
# ============================================================
def load_real_curve_support():
    """
    Carrega:
      - metadados das NTN-B (via load_ntnb_metadata, index = 'id')
      - matriz de yields YA para esses mesmos 'id' (GOVT_YA_PATH)

    Retorna:
      (ntnb_meta_df, ntnb_ya_df)
    """
    # Metadados NTNB a partir de domestic_sovereign_curve_brazil.xlsx
    ntnb_meta_df = load_ntnb_metadata(CONFIG["GOVT_PATH"])

    # Yields de governo (toda a matriz)
    ya_all = load_yield_surface(CONFIG["GOVT_YA_PATH"])
    # load_yield_surface:
    #   - lê sheet "ya_values_only"
    #   - primeira coluna -> OBS_DATE (index)
    #   - colunas restantes -> IDs (strings strip())

    # Alinhar usando 'id'
    meta_ids = ntnb_meta_df.index.astype(str).tolist()
    ya_cols = ya_all.columns.astype(str).tolist()

    overlap = [c for c in ya_cols if c in meta_ids]
    ntnb_ya_df = ya_all[overlap].copy()

    # DEBUG opcional
    print("\n[REAL CURVE SUPPORT] NTNB meta count:", len(ntnb_meta_df))
    print("[REAL CURVE SUPPORT] YA NTNB columns:", len(ntnb_ya_df.columns))
    print("[REAL CURVE SUPPORT] Overlap sample:", overlap[:10])

    return ntnb_meta_df, ntnb_ya_df


# ============================================================
# 2. Wrapper para WLA: yield real curta para uma data
# ============================================================
def wla_yield_for_date(obs_date: pd.Timestamp, t_years: float) -> float:
    """
    Função helper para obter WLA(t) em uma data, de forma EFICIENTE.

    Mudanças principais:
      - Carrega e interpola a surface WLA UMA ÚNICA VEZ (_load_wla_yc_table).
      - Para cada chamada:
          1) Escolhe a data de referência mais próxima (<= obs_date; se nenhuma,
             usa a primeira disponível).
          2) Escolhe o tenor t_years mais próximo entre as colunas (em anos).
    """
    yc_table = _load_wla_yc_table()  # DataFrame index=datetimes, cols=float (t_years)

    if yc_table.empty:
        return float("nan")

    # Garante que obs_date é Timestamp
    if not isinstance(obs_date, pd.Timestamp):
        obs_date = pd.to_datetime(obs_date)

    # Escolher a data efetiva:
    #   - ideal: última data <= obs_date
    #   - se não houver (obs_date antes do início), usar a primeira disponível
    dates = yc_table.index
    mask = dates <= obs_date
    if mask.any():
        obs_date_eff = dates[mask].max()
    else:
        obs_date_eff = dates.min()

    row = yc_table.loc[obs_date_eff]

    # Colunas são tenores em anos (float)
    tenor_array = np.array(row.index, dtype=float)
    t = float(t_years)

    # Encontra tenor mais próximo
    idx = np.argmin(np.abs(tenor_array - t))
    return float(row.iloc[idx])


# ============================================================
# 3. Builder para uma CombinedRealCurve por data
# ============================================================
def build_real_curve_for_obs_date(
    obs_date: pd.Timestamp,
    ntnb_meta_df: pd.DataFrame,
    ntnb_ya_df: pd.DataFrame,
) -> CombinedRealCurve | None:
    """
    Construção de CombinedRealCurve (WLA + NTNB) para uma data específica,
    usando:
      - ntnb_meta_df (index = 'id')
      - ntnb_ya_df (matrix de yields por 'id')
      - wla_yield_for_date como perna curta.
    """
    return build_real_curve_for_date(
        obs_date=obs_date,
        meta_df=ntnb_meta_df,
        ya_df=ntnb_ya_df,
        wla_yield_func_for_date=wla_yield_for_date,
    )