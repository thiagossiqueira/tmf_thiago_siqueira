import numpy as np
import pandas as pd
from finmath.termstructure.curve_models import flat_forward_interpolation

def interpolate_di_surface(
    surface: pd.DataFrame,
    tenors: dict,
) -> pd.DataFrame:
    """
    Interpolate the nominal DI curve.

    DI market quotes are stored in percentage points
    (e.g. 15.25 = 15.25%), while flat_forward_interpolation()
    expects decimal rates.

    The conversion is therefore:

        percentage points -> decimal -> interpolation
        -> percentage points

    The returned yc_table remains in percentage points so it is
    compatible with Bloomberg YTM fields and
    geometric_spread_bps_from_pct().
    """

    surface_dec = surface.copy()

    surface_dec["yield"] = (
        pd.to_numeric(
            surface_dec["yield"],
            errors="coerce",
        )
        / 100.0
    )

    result_dec = interpolate_surface(
        surface_dec,
        tenors,
    )

    return result_dec * 100.0

def interpolate_raw_di_yield_for_tenor(
    surface: pd.DataFrame,
    obs_date,
    target_tenor: float,
) -> float:
    """
    Interpolate the nominal DI yield directly from the raw selected
    market nodes for a given observation date and residual tenor.

    Raw DI quotes are stored in percentage points
    (e.g. 15.25 = 15.25%). flat_forward_interpolation()
    requires decimal rates, so the curve is converted to decimals
    before interpolation and converted back to percentage points
    on return.

    No intermediate standard-tenor grid is used.
    """

    obs_date = pd.Timestamp(obs_date)

    same_date = surface[
        surface["obs_date"].eq(obs_date)
    ].copy()

    if same_date.empty:
        return np.nan

    same_date["tenor"] = pd.to_numeric(
        same_date["tenor"],
        errors="coerce",
    )

    same_date["yield"] = pd.to_numeric(
        same_date["yield"],
        errors="coerce",
    )

    same_date = same_date.dropna(
        subset=["tenor", "yield"]
    ).sort_values("tenor")

    target_tenor = float(target_tenor)

    # If the requested tenor coincides numerically with an observed
    # market node, return that node directly rather than interpolating.
    # This avoids floating-point edge cases such as
    # 0.246031746031746 vs 0.24603174603174602.
    tenor_values = same_date["tenor"].to_numpy(dtype=float)
    yield_values = same_date["yield"].to_numpy(dtype=float)

    nearest_pos = int(
        np.argmin(
            np.abs(tenor_values - target_tenor)
        )
    )

    if np.isclose(
        tenor_values[nearest_pos],
        target_tenor,
        rtol=0.0,
        atol=1e-12,
    ):
        return float(
            yield_values[nearest_pos]
        )

    if len(same_date) < 2:
        return np.nan

    curve_dec = pd.Series(
        yield_values / 100.0,
        index=tenor_values,
    )

    interpolated_dec = flat_forward_interpolation(
        target_tenor,
        curve_dec,
    )

    return float(
        interpolated_dec * 100.0
    )

def interpolate_surface(surface: pd.DataFrame, tenors: dict, min_points: int = 2) -> pd.DataFrame:
    """
    Interpola a superfície de rendimento com base nos tenores alvo.

    Args:
        surface (pd.DataFrame): DataFrame com colunas ['obs_date', 'tenor', 'yield']
        tenors (dict): Mapeamento do nome do tenor para seu valor em anos
        min_points (int): Mínimo de pontos para realizar interpolação (default=2)

    Returns:
        pd.DataFrame: DataFrame indexado por obs_date, colunas = tenores alvo
    """
    rows = []
    surface["obs_date"] = pd.to_datetime(surface["obs_date"])

    for obs_date, grp in surface.groupby("obs_date"):
        curva = pd.Series(grp["yield"].values, index=grp["tenor"].values).dropna()
        if len(curva) < min_points:
            continue
        interpolated = {k: flat_forward_interpolation(t, curva) for k, t in tenors.items()}
        rows.append({"obs_date": obs_date, **interpolated})

    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("interpolate_surface() retornou DataFrame vazio!")

    return result.set_index("obs_date").sort_index()



def interpolate_yield_for_tenor(
    obs_date,
    yc_table,
    target_tenor,
    tenors,
    curve_id,
):
    """
    Interpolate a DI yield at an exact residual tenor.

    yc_table is stored in percentage points, but
    flat_forward_interpolation() requires decimal rates.
    The returned yield is converted back to percentage points.
    """

    di_row = yc_table.loc[curve_id]

    if "obs_date" in di_row.index:
        di_row = di_row.drop("obs_date")

    curve_pct = pd.to_numeric(
        di_row,
        errors="coerce",
    )

    curve_dec = pd.Series(
        curve_pct.values / 100.0,
        index=[
            tenors[k]
            for k in curve_pct.index
        ],
    )

    interpolated_dec = flat_forward_interpolation(
        target_tenor,
        curve_dec,
    )

    return float(interpolated_dec * 100.0)