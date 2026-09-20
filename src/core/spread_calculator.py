# src/core/spread_calculator.py

import numpy as np
import pandas as pd
from utils.interpolation import interpolate_yield_for_tenor
from calendars.daycounts import DayCounts
from config import CONFIG

# Convenção ANBIMA: Business / 252 dias úteis
DAYCOUNT = DayCounts("bus/252", calendar="cdr_anbima")

def geometric_spread_bps(
    corporate_yield_pct: float,
    benchmark_yield_dec: float,
) -> float:
    """
    Geometric corporate spread under annual effective compounding.

    Parameters
    ----------
    corporate_yield_pct
        Corporate YTM in Bloomberg percentage points.
        Example: 8.53 means 8.53%.

    benchmark_yield_dec
        Zero-curve benchmark in decimal form.
        Example: 0.066 means 6.6%.

    Returns
    -------
    float
        Geometric spread in basis points.
    """

    corporate_yield_dec = (
        float(corporate_yield_pct) / 100.0
    )

    benchmark_yield_dec = float(
        benchmark_yield_dec
    )

    spread_dec = (
        (1.0 + corporate_yield_dec)
        / (1.0 + benchmark_yield_dec)
        - 1.0
    )

    return float(
        spread_dec * 10000.0
    )

# ============================================================================
# Função padrão (corporates, NTNF, NTNB)
# Agora suporta curva soberana real COMBINADA **por data** através dos parâmetros:
#
#   build_real_curve_for_date  -> função constrói curva real (NTNB+WLA) para obs_date
#   ntnb_meta_df               -> metadados das NTN-B (filtradas por CALC_TYP_DES)
#   ntnb_ya_df                 -> yields YA por ISIN
#   wla_yield_func_for_date    -> função WLA(obs_date, tenor)
#
# Se build_real_curve_for_date=None, o comportamento permanece 100% original.
# ============================================================================

def geometric_spread_bps_from_pct(
    corporate_yield_pct: float,
    benchmark_yield_pct: float,
) -> float:
    """
    Geometric spread when both yields are stored in percentage points.

    Example:
        corporate = 12.5 means 12.5%
        benchmark = 11.0 means 11.0%
    """

    corporate_yield_dec = (
        float(corporate_yield_pct) / 100.0
    )

    benchmark_yield_dec = (
        float(benchmark_yield_pct) / 100.0
    )

    spread_dec = (
        (1.0 + corporate_yield_dec)
        / (1.0 + benchmark_yield_dec)
        - 1.0
    )

    return float(
        spread_dec * 10000.0
    )

def compute_spreads(
    corp_base,
    yields_ts,
    yc_table,
    observation_periods,
    tenors_dict,
    build_real_curve_for_date=None,   # <<< NOVO
    ntnb_meta_df=None,
    ntnb_ya_df=None,
    wla_yield_func_for_date=None,
    wla_max_tenor_func_for_date=None,
    allow_curve_extrapolation=True,
    real_curve_cache=None,
):
    """
    Calcula spreads entre yields dos bonds e:
        - curva DI/IPCA interpolada (padrão);
        - OU curva soberana real combinada (WLA + NTN-B via NSS), caso
          build_real_curve_for_date seja fornecido.

    Retorna (corp_bonds_df, skipped_rows_list).
    """

    expanded_rows = []
    skipped = []
    if real_curve_cache is None:
        real_curve_cache = {}

    # --------------------------------------------------------
    # Verificação mínima para curva real soberana combinada
    # --------------------------------------------------------
    using_real_curve = (
        build_real_curve_for_date is not None and
        ntnb_meta_df is not None and
        ntnb_ya_df is not None and
        wla_yield_func_for_date is not None
    )

    for _, bond in corp_base.iterrows():
        bond_id = bond["id"]
        obs_start, obs_end = observation_periods.get(bond_id, (None, None))
        if obs_start is None:
            continue

        # itera sobre as datas da curva DI (ou tabela passada)
        for obs_date, di_row in (yc_table.iterrows() if yc_table is not None else []):
            if not (obs_start <= obs_date <= obs_end):
                continue

            # yield do bond (YAS_BOND_YLD)
            try:
                yas_yld = yields_ts.at[obs_date, bond_id]
            except KeyError:
                skipped.append((bond_id, obs_date, "Missing column or date"))
                continue
            if pd.isna(yas_yld):
                skipped.append((bond_id, obs_date, "NaN yield"))
                continue

            # tenor ANBIMA
            tenor_yrs = DAYCOUNT.tf(obs_date, bond["MATURITY"])
            if tenor_yrs <= 0:
                continue

            # ===========================================================
            #  SE TIVERMOS curva real soberana (NTNB + NSS + WLA)
            #  ela será construída dinamicamente para cada obs_date
            # ===========================================================
            if using_real_curve:
                ref_yield = None

                # -------------------------------------------------------
                # 1. WLA / DAP has priority whenever the corporate tenor
                #    is inside the actually observed WLA maturity range
                #    for that specific observation date.
                # -------------------------------------------------------
                max_wla_tenor = np.nan

                if wla_max_tenor_func_for_date is not None:
                    max_wla_tenor = wla_max_tenor_func_for_date(obs_date)

                if (
                        wla_yield_func_for_date is not None
                        and pd.notna(max_wla_tenor)
                        and tenor_yrs <= float(max_wla_tenor)
                ):
                    ref_yield = wla_yield_func_for_date(
                        obs_date,
                        tenor_yrs,
                    )

                # -------------------------------------------------------
                # 2. Only when the corporate bond lies beyond the
                #    observed WLA range do we use the sovereign NTN-B
                #    zero curve estimated through NSS.
                #
                #    IMPORTANT:
                #    use the raw NSS zero curve here, not CombinedRealCurve,
                #    because we do not want the old fixed-5Y delta shift.
                # -------------------------------------------------------
                else:
                    if obs_date not in real_curve_cache:
                        real_curve_cache[obs_date] = build_real_curve_for_date(
                            obs_date,
                            ntnb_meta_df,
                            ntnb_ya_df,
                            wla_yield_func_for_date,
                            wla_max_tenor_func_for_date,
                        )

                    real_curve = real_curve_cache[obs_date]

                    if real_curve is not None:
                        ref_yield = real_curve.yield_at(
                            tenor_yrs
                        )

                # -------------------------------------------------------
                # 3. If a valid benchmark was found, compute the spread.
                # -------------------------------------------------------
                if ref_yield is not None and np.isfinite(ref_yield):
                    spread = geometric_spread_bps(
                        corporate_yield_pct=yas_yld,
                        benchmark_yield_dec=ref_yield,
                    )

                    expanded_rows.append({
                        "id": bond_id,
                        "OBS_DATE": obs_date,
                        "MATURITY": bond["MATURITY"],
                        "YAS_BOND_YLD": yas_yld,
                        "DI_YIELD": ref_yield,
                        "SPREAD": spread,
                        "CPN_TYP": bond.get("CPN_TYP", "Corp bond"),
                        "CPN": bond.get("CPN", np.nan),
                        "DAYS_TO_MATURITY": (
                                bond["MATURITY"] - obs_date
                        ).days,
                        "TENOR_YRS": tenor_yrs,
                    })

                    continue

                # -------------------------------------------------------
                # 4. For IPCA, do not silently fall through to another
                #    benchmark when neither WLA nor the NTN-B curve is
                #    available.
                # -------------------------------------------------------
                if not allow_curve_extrapolation:
                    skipped.append(
                        (
                            bond_id,
                            obs_date,
                            "No valid WLA or NTN-B zero benchmark",
                        )
                    )
                    continue
            # ===========================================================
            # COMPORTAMENTO ORIGINAL (DI/IPCA interpolada)
            # ===========================================================
            interpolated_di_yield = interpolate_yield_for_tenor(
                obs_date, yc_table, tenor_yrs, tenors_dict, obs_date
            )
            spread = geometric_spread_bps_from_pct(
                corporate_yield_pct=yas_yld,
                benchmark_yield_pct=interpolated_di_yield,
            )

            expanded_rows.append({
                "id": bond_id,
                "OBS_DATE": obs_date,
                "MATURITY": bond["MATURITY"],
                "YAS_BOND_YLD": yas_yld,
                "DI_YIELD": interpolated_di_yield,
                "SPREAD": spread,
                "CPN_TYP": bond.get("CPN_TYP", "Corp bond"),
                "CPN": bond.get("CPN", np.nan),
                "DAYS_TO_MATURITY": (bond["MATURITY"] - obs_date).days,
                "TENOR_YRS": tenor_yrs,
            })

    corp_bonds = pd.DataFrame(expanded_rows)
    if corp_bonds.empty:
        raise ValueError("No valid corporate bond spreads calculated.")

    # bucketização
    names = list(tenors_dict.keys())
    vals = np.array(list(tenors_dict.values()))
    corp_bonds["TENOR_BUCKET"] = corp_bonds["TENOR_YRS"].apply(
        lambda y: names[np.argmin(np.abs(vals - y))]
    )

    return corp_bonds, skipped


# ============================================================================
# Função para LTNs (zero)
# Mantida sem alterações (DI continua sendo baseline)
# ============================================================================
def compute_spreads_ltn(df_ltn: pd.DataFrame, yc_table: pd.DataFrame) -> pd.DataFrame:
    """
    Cálculo de spreads para LTNs usando curva DI.
    """
    df = df_ltn.copy()

    df["MATURITY"] = pd.to_datetime(df["MATURITY"], errors="coerce")
    df["OBS_DATE"] = pd.to_datetime(df["OBS_DATE"], errors="coerce")

    df["TENOR_YRS"] = df.apply(
        lambda r: DAYCOUNT.tf(r["OBS_DATE"], r["MATURITY"])
        if pd.notna(r["OBS_DATE"]) and pd.notna(r["MATURITY"])
        else np.nan,
        axis=1
    )
    df = df[df["TENOR_YRS"] > 0]

    if yc_table is None or yc_table.empty:
        raise ValueError("yc_table vazia: DI indisponível para LTNs")

    if yc_table.shape[0] > 1:
        yc_interp = yc_table.T.mean(axis=1)
    else:
        yc_interp = yc_table.T.iloc[:, 0]

    tenor_map = CONFIG.get("TENORS", {})

    if yc_interp.index.dtype == object:
        yc_interp.index = yc_interp.index.map(tenor_map).astype(float)
    else:
        yc_interp.index = pd.to_numeric(yc_interp.index, errors="coerce")

    yc_interp = yc_interp[~pd.isna(yc_interp.index)]

    df["DI_YIELD"] = df["TENOR_YRS"].apply(
        lambda t: yc_interp.iloc[(abs(yc_interp.index - t)).argmin()]
    )

    df["YAS_BOND_YLD"] = pd.to_numeric(df["YAS_BOND_YLD"], errors="coerce")
    df["DI_YIELD"] = pd.to_numeric(df["DI_YIELD"], errors="coerce")
    df["SPREAD"] = df["DI_YIELD"] - df["YAS_BOND_YLD"]

    names = [str(round(i, 2)) for i in yc_interp.index]
    vals = np.array(list(yc_interp.index))
    df["TENOR_BUCKET"] = df["TENOR_YRS"].apply(
        lambda y: names[np.argmin(np.abs(vals - y))]
    )

    df["CPN_TYP"] = "ZERO"
    df["CPN"] = np.nan
    df["DAYS_TO_MATURITY"] = df.apply(
        lambda r: DAYCOUNT.days(r["OBS_DATE"], r["MATURITY"])
        if pd.notna(r["OBS_DATE"]) and pd.notna(r["MATURITY"])
        else np.nan,
        axis=1
    )

    return df