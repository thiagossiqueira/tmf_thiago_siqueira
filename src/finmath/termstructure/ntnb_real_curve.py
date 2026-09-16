# src/finmath/termstructure/ntnb_real_curve.py

import numpy as np
import pandas as pd

from calendars.daycounts import DayCounts

from src.finmath.termstructure.curve_models import fit_nss_yield_curve
from src.finmath.termstructure.combined_real_curve import CombinedRealCurve


# ANBIMA convention for sovereign curves
DAYCOUNT_BUS252 = DayCounts("bus/252", calendar="cdr_anbima")


# =====================================================================
# 1. Load NTNB metadata (using correct identifier column: "ID")
# =====================================================================
def load_ntnb_metadata(govt_path: str) -> pd.DataFrame:
    """
    Load NTNB metadata from domestic_sovereign_curve_brazil.xlsx,
    using the column 'ID' (with "Corp" suffix) as the identifier.

    This EXACTLY matches YA govt columns such as:
        "BRSTNCNTB4U6 Corp"
        "BRSTNCNTB682 Corp"
    """

    df = pd.read_excel(govt_path, sheet_name="db_values_only")

    # Identifier column is "ID" (uppercase) — not "id", not ISIN
    if "ID" not in df.columns:
        raise ValueError("Column 'ID' not found in government metadata Excel.")

    df["ID"] = df["ID"].astype(str).str.strip()

    # Filter only NTNB (inflation-linked) bonds
    df["CALC_TYP_DES"] = df["CALC_TYP_DES"].astype(str).str.upper().str.strip()
    df = df[df["CALC_TYP_DES"] == "BRAZIL I/L BOND"].copy()

    # Parse maturity and first coupon date
    df["MATURITY"] = pd.to_datetime(
        df["MATURITY"],
        errors="coerce"
    )

    df["FIRST_CPN_DT"] = pd.to_datetime(
        df["FIRST_CPN_DT"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["ID", "MATURITY", "FIRST_CPN_DT"]
    )

    # Ensure coupon fields exist
    for col in ["CPN", "CPN_FREQ", "CPN_TYP"]:
        if col not in df.columns:
            df[col] = np.nan

    # Use ID as index (this matches YA tickers)
    df = df.set_index("ID")

    return df


# =====================================================================
# 2. Load NTNB yields from govt_ya.v1.xlsx
# =====================================================================
def load_ntnb_yields(ya_path: str, id_index) -> pd.DataFrame:
    """
    Load NTNB YA yields using the SAME IDs as metadata.
    These IDs look like "BRSTNCNTB4U6 Corp" and appear as YA columns.
    """

    df = pd.read_excel(ya_path, sheet_name="ya_values_only")

    # Keep the column names exactly, just strip whitespace
    df.columns = [str(c).strip() for c in df.columns]

    # First column = date
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)

    meta_ids = list(id_index)

    # Select only columns that match metadata NTNB IDs
    cols = [c for c in df.columns if c in meta_ids]

    # DEBUG
    print("\n[DEBUG] Raw YA columns:", df.columns.tolist()[:20])
    print("[DEBUG] Expected NTNB IDs:", meta_ids[:20])
    print("[DEBUG] Matching NTNB YA columns:", cols)

    # Extract only those columns
    df = df[cols].apply(pd.to_numeric, errors="coerce")

    return df



# =====================================================================
# 3. Build normalized NTN-B future cash flows
# =====================================================================
def build_ntnb_cash_flows(
    meta_row: pd.Series,
    obs_date: pd.Timestamp,
    principal: float = 100.0,
) -> pd.Series:
    """
    Build future normalized cash flows for a standard NTN-B.

    NTN-B convention:
      - 6% annual real coupon
      - semiannual coupon payments
      - semiannual coupon factor:
            (1 + 0.06) ** 0.5 - 1
      - principal normalized to 100
      - only cash flows strictly after obs_date are returned

    The normalization means that historical VNA is not required for
    constructing the real zero-rate curve.
    """

    obs_date = pd.Timestamp(obs_date).normalize()

    first_coupon = pd.Timestamp(
        meta_row["FIRST_CPN_DT"]
    ).normalize()

    maturity = pd.Timestamp(
        meta_row["MATURITY"]
    ).normalize()

    annual_coupon = float(meta_row["CPN"]) / 100.0
    frequency = int(meta_row["CPN_FREQ"])

    if frequency != 2:
        raise ValueError(
            f"Unexpected NTN-B coupon frequency: {frequency}"
        )

    # Brazilian NTN-B semiannual coupon convention:
    # not simply 6% / 2.
    semiannual_coupon_rate = (
        (1.0 + annual_coupon) ** (1.0 / frequency)
        - 1.0
    )

    coupon_amount = (
        principal * semiannual_coupon_rate
    )

    # Build complete coupon schedule from first coupon date
    # through maturity.
    payment_dates = []

    d = first_coupon

    while d <= maturity:
        payment_dates.append(d)
        d = d + pd.DateOffset(
            months=int(12 / frequency)
        )

    # Defensive guard: ensure maturity is included exactly once.
    if maturity not in payment_dates:
        payment_dates.append(maturity)

    payment_dates = sorted(
        set(payment_dates)
    )

    cash_flows = {}

    for payment_date in payment_dates:

        # We only need future cash flows as of obs_date.
        if payment_date <= obs_date:
            continue

        amount = coupon_amount

        # Principal is repaid at maturity.
        if payment_date == maturity:
            amount += principal

        cash_flows[
            payment_date.date()
        ] = float(amount)

    return pd.Series(
        cash_flows,
        dtype=float,
    ).sort_index()



# =====================================================================
# 3. Build real sovereign curve for ONE DATE using NSS
# =====================================================================
def build_real_curve_for_date(
    obs_date: pd.Timestamp,
    meta_df: pd.DataFrame,
    ya_df: pd.DataFrame,
    wla_yield_func_for_date,
) -> CombinedRealCurve | None:
    """
    Build the REAL sovereign curve for a single observation date.

    Steps:
      1. Collect (tenor, yield) pairs for NTNB using ANBIMA bus/252.
      2. Fit NSS yield curve over NTNB yields.
      3. Combine:
            WLA(t)  for 0–5 years
            NTN-B NSS curve for >5 years
         through CombinedRealCurve.
    """

    # No data for this date → no curve
    if ya_df.empty or obs_date not in ya_df.index:
        return None

    row = ya_df.loc[obs_date]

    t_list = []
    y_list = []

    # For each NTNB ID in metadata
    for sec_id in meta_df.index:
        if sec_id not in row.index:
            continue

        y = row[sec_id]
        if pd.isna(y):
            continue

        mat = meta_df.loc[sec_id, "MATURITY"]
        if pd.isna(mat):
            continue

        # ANBIMA bus/252 tenor
        try:
            t_years = DAYCOUNT_BUS252.tf(obs_date.to_pydatetime().date(), mat.date())
        except Exception:
            continue

        if t_years <= 0:
            continue

        t_list.append(float(t_years))
        y_list.append(float(y) / 100.0)  # % → decimal

    # Need enough points for NSS fit
    if len(t_list) < 4:
        return None

    t_arr = np.array(t_list, dtype=float)
    y_arr = np.array(y_list, dtype=float)

    # Fit NSS yield curve
    nss_curve = fit_nss_yield_curve(t_arr, y_arr)

    # Short-end anchor: WLA(t) for this obs_date
    def wla_func(t: float) -> float:
        return wla_yield_func_for_date(obs_date, t)

    # CombinedRealCurve expects model_curve.yield_at(t)
    # nss_curve already provides .yield_at(t)
    combined = CombinedRealCurve(
        wla_func=wla_func,
        model_curve=nss_curve,   # ← USE THE CURVE OBJECT, NOT A FUNCTION
        t_switch=5.0,
    )

    return combined
