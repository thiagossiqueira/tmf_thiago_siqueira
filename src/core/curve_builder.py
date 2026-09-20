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
# -------------------------------------------------------------------
# WLA raw-surface cache
# -------------------------------------------------------------------
_WLA_SURFACE: pd.DataFrame | None = None


def _load_wla_surface() -> pd.DataFrame:
    """
    Load the historical WLA / DAP real-rate surface once.

    The surface preserves the actual contract tenors observed on each
    historical date instead of collapsing them onto a fixed tenor grid.
    """
    global _WLA_SURFACE

    if _WLA_SURFACE is not None:
        return _WLA_SURFACE

    from src.utils.file_io import load_ipca_surface

    surface = load_ipca_surface(
        CONFIG["WLA_CURVE_PATH"]
    ).copy()

    surface["obs_date"] = pd.to_datetime(
        surface["obs_date"]
    )

    surface = surface.sort_values(
        ["obs_date", "tenor"]
    )

    _WLA_SURFACE = surface

    return _WLA_SURFACE


def wla_max_tenor_for_date(
    obs_date: pd.Timestamp,
) -> float:
    """
    Return the maximum observed WLA / DAP contract tenor
    available on the effective curve date.

    This is used to prevent extrapolation beyond the actual
    maturity range of the WLA market.
    """

    surface = _load_wla_surface()

    if surface.empty:
        return float("nan")

    obs_date = pd.Timestamp(
        obs_date
    ).normalize()

    available_dates = pd.DatetimeIndex(
        surface["obs_date"].unique()
    ).sort_values()

    eligible_dates = available_dates[
        available_dates <= obs_date
    ]

    if len(eligible_dates) > 0:
        obs_date_eff = eligible_dates.max()
    else:
        obs_date_eff = available_dates.min()

    grp = surface[
        surface["obs_date"] == obs_date_eff
    ]

    if grp.empty:
        return float("nan")

    return float(
        grp["tenor"].max()
    )

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
def wla_yield_for_date(
    obs_date: pd.Timestamp,
    t_years: float,
) -> float:
    """
    Return the WLA / DAP zero rate for an arbitrary tenor.

    Uses the actual WLA contracts available on the effective
    observation date and ANBIMA flat-forward interpolation.
    """

    from finmath.termstructure.curve_models import (
        flat_forward_interpolation,
    )

    surface = _load_wla_surface()

    if surface.empty:
        return float("nan")

    obs_date = pd.Timestamp(
        obs_date
    ).normalize()

    available_dates = pd.DatetimeIndex(
        surface["obs_date"].unique()
    ).sort_values()

    eligible_dates = available_dates[
        available_dates <= obs_date
    ]

    if len(eligible_dates) > 0:
        obs_date_eff = eligible_dates.max()
    else:
        obs_date_eff = available_dates.min()

    grp = surface[
        surface["obs_date"] == obs_date_eff
    ].copy()

    if grp.empty:
        return float("nan")

    curve = (
        grp
        .sort_values("tenor")
        .groupby("tenor")["yield"]
        .last()
    )

    if curve.empty:
        return float("nan")

    return float(
        flat_forward_interpolation(
            float(t_years),
            curve,
        )
    )

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
        wla_max_tenor_func_for_date=wla_max_tenor_for_date,
    )