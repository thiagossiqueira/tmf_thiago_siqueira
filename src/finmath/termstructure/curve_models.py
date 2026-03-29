from typing import Union, Collection, Optional, Tuple

import warnings

import numpy as np
import pandas as pd
import scipy.optimize as opt

from calendars import DayCounts
from calendars.custom_date_types import Date, TODAY

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ANBIMA_LAMBDAS = np.array([2.2648, 0.3330])

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def forward_rate(t1: float, t2: float, zero_curve: pd.Series) -> float:
    """Discrete forward rate between t1 and t2 (years) from a zero-curve."""
    t1, t2 = sorted([t1, t2])
    y1 = flat_forward_interpolation(t1, zero_curve)
    y2 = flat_forward_interpolation(t2, zero_curve)

    return (((1.0 + y2) ** t2) / ((1.0 + y1) ** t1)) ** (1 / (t2 - t1)) - 1.0


def _clean_curve(
    curve: pd.Series,
    dc: Optional[DayCounts] = None,
    ref_date: Optional[Date] = None,
) -> pd.Series:
    """Ensure curve index is numerical (year-fractions)."""
    date_types = list(Date.__args__) + [pd.Timestamp]

    if all(isinstance(t, tuple(date_types)) for t in curve.index):
        assert ref_date is not None, "Parameter ref_date as Date required!"
        assert dc is not None, "Parameter dc as DayCounts required!"
        dates = [dc.tf(pd.to_datetime(ref_date).date(), t) for t in curve.index]
        clean_curve = pd.Series(curve.values, dates).astype(float)
    else:
        clean_curve = pd.Series(curve.values, [float(t) for t in curve.index]).astype(
            float
        )

    return clean_curve.dropna().sort_index()


def flat_forward_interpolation(
    t: Union[float, Date],
    zero_curve: pd.Series,
    dc: Optional[DayCounts] = None,
    ref_date: Optional[Date] = None,
) -> float:
    """ANBIMA flat-forward interpolation (piecewise-constant forward rates)."""
    if isinstance(t, (float, int)):
        t = float(t)
        clean_curve = _clean_curve(zero_curve)
    else:
        if not isinstance(dc, DayCounts):
            raise TypeError("Parameter t as Date requires parameter dc as DayCounts")
        if not isinstance(ref_date, tuple(Date.__args__) + (pd.Timestamp,)):
            raise TypeError("Parameter t as Date requires parameter ref_date as Date")
        t = dc.tf(pd.to_datetime(ref_date).date(), t)
        clean_curve = _clean_curve(zero_curve, dc=dc, ref_date=ref_date)

    zero_curve = clean_curve.sort_index()
    t0, tn = min(zero_curve.index), max(zero_curve.index)

    if t <= t0:
        y = zero_curve[t0]
    elif t >= tn:
        y = zero_curve[tn]
    else:
        t1, y1 = [(x, y) for x, y in zero_curve.items() if x < t][-1]
        t2, y2 = [(x, y) for x, y in zero_curve.items() if x > t][0]
        y = ((1.0 + y1) ** ((t1 / t) * (t2 - t) / (t2 - t1))) * (
            (1.0 + y2) ** ((t2 / t) * (t - t1) / (t2 - t1))
        ) - 1.0

    return y


# ---------------------------------------------------------------------------
# Nelson-Siegel-Svensson parametric curve
# ---------------------------------------------------------------------------


class NelsonSiegelSvensson:
    def __init__(
        self,
        prices: Union[float, Collection[float]],
        cash_flows: Union[pd.Series, Collection[pd.Series]],
        day_count_convention: str = "bus/252",
        calendar: str = "cdr_anbima",
        ref_date: Date = TODAY,
        lambdas: Optional[np.array] = ANBIMA_LAMBDAS,
    ):
        if isinstance(prices, float):
            prices = [prices]
        if isinstance(cash_flows, pd.Series):
            cash_flows = [cash_flows]

        self.ref_date = ref_date
        self.dc = DayCounts(dc=day_count_convention, calendar=calendar)

        self.lambdas = np.ones(2) if lambdas is None else lambdas
        self.betas = self.estimate_betas(
            prices=prices,
            cash_flows=cash_flows,
            dc=self.dc,
            ref_date=self.ref_date,
            lambdas=self.lambdas,
        )

    # --- static helpers ----------------------------------------------------

    @staticmethod
    def rate_for_ytm(betas=np.zeros(4), lambdas=ANBIMA_LAMBDAS, ytm: float = 1.0):
        l1 = lambdas[0]
        f1 = lambda x: (1.0 - np.exp(-l1 * x)) / (l1 * x)
        y = betas[0] + betas[1] * f1(ytm)
        f2 = lambda x: f1(x) - np.exp(-l1 * x)
        y += betas[2] * f2(ytm)
        l2 = lambdas[1]
        g1 = lambda x: (1.0 - np.exp(-l2 * x)) / (l2 * x)
        g2 = lambda x: g1(x) - np.exp(-l2 * x)
        y += betas[3] * g2(ytm)
        return y

    # --- pricing -----------------------------------------------------------

    def bond_price(
        self,
        cf: pd.Series,
        dc: Optional[DayCounts] = None,
        ref_date: Optional[Date] = None,
        betas: Optional[np.array] = None,
        lambdas: Optional[np.array] = None,
    ):
        dc = dc or self.dc
        ref_date = ref_date or self.ref_date
        betas = betas if betas is not None else self.betas
        lambdas = lambdas if lambdas is not None else self.lambdas

        pv = 0.0
        for d, dpay in cf.items():
            ytm = dc.tf(ref_date, d)
            y = self.rate_for_ytm(betas=betas, lambdas=lambdas, ytm=ytm)
            pv += dpay / ((1.0 + y) ** ytm)
        return pv

    def price_errors(
        self,
        prices: Union[float, Collection[float]],
        cash_flows: Union[pd.Series, Collection[pd.Series]],
        dc: Optional[DayCounts] = None,
        ref_date: Optional[Date] = None,
        betas: Optional[np.array] = None,
        lambdas: Optional[np.array] = None,
    ):
        assert len(prices) == len(cash_flows), "Not the same number of prices and CFs!"
        dc = dc or self.dc
        ref_date = ref_date or self.ref_date

        pe = 0.0
        for p, cf in zip(prices, cash_flows):
            theo = self.bond_price(
                cf, dc, ref_date=ref_date, betas=betas, lambdas=lambdas
            )
            w = 1.0 / dc.tf(ref_date, max(cf.index))  # TODO: duration weight
            pe += w * ((p - theo) / p) ** 2.0
        return pe

    # --- parameter estimation ---------------------------------------------

    def estimate_betas(
        self,
        prices: Union[float, Collection[float]],
        cash_flows: Union[pd.Series, Collection[pd.Series]],
        dc: Optional[DayCounts],
        ref_date: Optional[Date],
        lambdas: Optional[np.array],
    ):
        obj = lambda x: self.price_errors(
            prices=prices,
            cash_flows=cash_flows,
            dc=dc,
            ref_date=ref_date,
            betas=x,
            lambdas=lambdas,
        )

        res = opt.minimize(obj, np.zeros(4), method="SLSQP")
        if res.status != 0:
            raise ArithmeticError(f"Optimization failed: {res.message}")
        return res.x


# ---------------------------------------------------------------------------
# Generic bootstrap from bond cash-flows
# ---------------------------------------------------------------------------


class CurveBootstrap:
    def __init__(
        self,
        cash_flows: Collection[pd.Series],
        rates: Optional[Union[float, Collection[float]]] = None,
        prices: Optional[Union[float, Collection[float]]] = None,
        day_count_convention: str = "bus/252",
        calendar: str = "cdr_anbima",
        ref_date: Date = TODAY,
    ):
        assert rates is not None or prices is not None, "Need rates or prices!"
        assert all(isinstance(x, pd.Series) for x in cash_flows), (
            "Parameter cash_flows must be Collection[pd.Series]"
        )

        if isinstance(rates, float):
            rates = [rates]
        if isinstance(prices, float):
            prices = [prices]
        if rates is not None and prices is not None:
            warnings.warn("Both rates and prices given, dropping prices!")
            prices = None

        self.ref_date = ref_date
        self.dc = DayCounts(dc=day_count_convention, calendar=calendar)

        self.zero_curve = self._initial_zero_curve(
            cash_flows=cash_flows,
            rates=rates,
            prices=prices,
            dc=self.dc,
            ref_date=self.ref_date,
        )

        self.bootstrap(cash_flows=cash_flows, rates=rates, prices=prices)

    # ------------------------------------------------------------------ #
    # private helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _initial_zero_curve(
        cash_flows: Collection[pd.Series],
        rates: Optional[Collection[float]] = None,
        prices: Optional[Collection[float]] = None,
        dc: Optional[DayCounts] = None,
        ref_date: Optional[Date] = None,
    ) -> pd.Series:
        if rates is not None:
            bonds = zip(cash_flows, rates)
            is_rates = True
        else:
            bonds = zip(cash_flows, prices)
            is_rates = False

        ytm, curve = [], []
        for cf, y in bonds:
            if len(cf) == 1:  # zero-coupon
                d = pd.to_datetime(cf.index[-1]).date()
                t = dc.tf(ref_date, d)
                r = float(y) if is_rates else (cf.iloc[-1] / float(y)) ** (1.0 / t) - 1.0
                ytm.append(t)
                curve.append(r)

        return pd.Series(curve, index=ytm).sort_index()

    def rate_for_date(self, t: Union[float, Date]) -> float:
        return flat_forward_interpolation(t, self.zero_curve, self.dc, self.ref_date)

    # ------------------------- PV helpers ------------------------------- #

    @staticmethod
    def _bond_pv_for_rate(
        expanded_rate: float,
        zero_curve: pd.Series,
        bond_cash_flows: pd.Series,
        dc: Optional[DayCounts] = None,
        ref_date: Optional[Date] = None,
    ) -> float:
        zero_curve_end = max(zero_curve.index)
        ytm = dc.tf(ref_date, max(bond_cash_flows.index))
        expanded_point = pd.Series([expanded_rate], index=[ytm])
        zero_curve = pd.concat([zero_curve, expanded_point]).sort_index()

        pv = 0.0
        for d, c in bond_cash_flows.items():
            t = dc.tf(ref_date, d)
            if t > zero_curve_end:
                y = flat_forward_interpolation(t, zero_curve, dc, ref_date)
                pv += c / ((1.0 + y) ** t)
        return pv

    @staticmethod
    def _bond_strip(
        zero_curve: pd.Series,
        bond_cash_flows: pd.Series,
        dc: Optional[DayCounts] = None,
        ref_date: Optional[Date] = None,
        rate: Optional[float] = None,
        price: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        assert rate is not None or price is not None, "Need rate or price!"

        maturity = dc.tf(ref_date, max(bond_cash_flows.index))
        zero_curve_end = max(zero_curve.index)
        assert zero_curve_end <= maturity, "Bond maturity < zero-curve end!"

        if price is None:
            price = sum(
                c / ((1.0 + rate) ** dc.tf(ref_date, d))
                for d, c in bond_cash_flows.items()
            )

        pv_known = 0.0
        for d, c in bond_cash_flows.sort_index().items():
            t = dc.tf(ref_date, d)
            if t <= zero_curve_end:
                y = flat_forward_interpolation(t, zero_curve, dc, ref_date)
                pv_known += c / ((1.0 + y) ** t)

        return price, pv_known, maturity

    # -------------------- robust curve expansion ------------------------ #

    def _expand_zero_curve(
        self,
        bond_cash_flows: pd.Series,
        rate: Optional[float] = None,
        price: Optional[float] = None,
    ):
        """
        Add one point to the zero-curve so the PV of `bond_cash_flows`
        matches either `price` or `rate`.

        Uses Brent bracketing root-finder; falls back to bounded SLSQP when
        the sign of the price gap cannot be bracketed within [-5 %, 100 %].
        """
        price, pv_known, ytm = self._bond_strip(
            zero_curve=self.zero_curve,
            bond_cash_flows=bond_cash_flows,
            dc=self.dc,
            ref_date=self.ref_date,
            rate=rate,
            price=price,
        )

        def price_gap(r: float) -> float:
            pv_tail = self._bond_pv_for_rate(
                expanded_rate=r,
                zero_curve=self.zero_curve,
                bond_cash_flows=bond_cash_flows,
                dc=self.dc,
                ref_date=self.ref_date,
            )
            return (pv_tail + pv_known) - price

        lower, upper = -0.05, 1.00  # generous bracket: -5 % … 100 %
        try:
            root = opt.brentq(price_gap, lower, upper, maxiter=500)
        except (ValueError, RuntimeError):
            # Fallback: minimise squared error, bounded at r >= 0
            res = opt.minimize(
                lambda x: price_gap(x) ** 2,
                self.zero_curve.iloc[-1],
                method="SLSQP",
                bounds=[(0.0, None)],
                options={"ftol": 1e-12, "maxiter": 1000},
            )
            if res.status != 0:
                raise ArithmeticError(f"Bootstrap failed: {res.message}")
            root = float(res.x)

        expanded_point = pd.Series([root], index=[ytm])
        return pd.concat([self.zero_curve, expanded_point]).sort_index()

    # ---------------------------- main loop ----------------------------- #

    def bootstrap(
        self,
        cash_flows: Collection[pd.Series],
        rates: Optional[Collection[float]] = None,
        prices: Optional[Collection[float]] = None,
    ):
        assert rates is not None or prices is not None, "Need rates or prices!"
        tmax = max(self.zero_curve.index)

        for i, cf in enumerate(cash_flows):
            if len(cf) == 1:
                continue  # already dealt with zero-coupon bonds
            maturity = self.dc.tf(self.ref_date, max(cf.index))
            if maturity <= tmax:
                continue  # maturity already covered by existing curve

            if prices is not None and (rates is None or rates[i] is None):
                new_curve = self._expand_zero_curve(cf, rate=None, price=prices[i])
            elif rates is not None and (prices is None or prices[i] is None):
                new_curve = self._expand_zero_curve(cf, rate=rates[i], price=None)
            else:
                continue  # both given (warning issued earlier)

            self.zero_curve = new_curve

# ======================================================================
# Lightweight NSS (yield-based) used for NTNB real curve fitting
# Reuses the same nss_func logic already used for CDS synthetic curve.
# ======================================================================

from scipy.optimize import curve_fit

def nss_func(t, beta0, beta1, beta2, tau1, tau2):
    """
    Simplified NSS yield function (beta3 locked at zero).
    Matches the existing implementation used in add_synthetic_cds_to_panel.py.
    """
    t = np.maximum(t, 1e-6)
    term1 = (1 - np.exp(-t / tau1)) / (t / tau1)
    term2 = term1 - np.exp(-t / tau1)
    term3 = ((1 - np.exp(-t / tau2)) / (t / tau2)) - np.exp(-t / tau2)
    return beta0 + beta1 * term1 + beta2 * term2 + 0.0 * term3


# ---------------------------------------------------------------------------
# Robust NSS yield-curve fit (for NTNB real curve etc.)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Robust NSS yield-curve fit (Option D: bounds + safeguards + fallbacks)
# ---------------------------------------------------------------------------

def fit_nss_yield_curve(maturities: np.ndarray, yields: np.ndarray):
    """
    Production-grade NSS fitting with:
        - bounds on parameters (beta0, beta1, beta2, tau1, tau2)
        - safe exponentials (no overflow/underflow)
        - clipping to realistic real-yield ranges (-10% to +30%)
        - protection against complex numbers
        - fallback to flat curve when fitting fails

    ALWAYS returns an object with .yield_at(t) -> float
    """

    maturities = np.asarray(maturities, dtype=float)
    yields = np.asarray(yields, dtype=float)

    # -----------------------------------------------
    # 1. Clean inputs
    # -----------------------------------------------
    mask = np.isfinite(maturities) & np.isfinite(yields) & (maturities > 0)
    maturities = maturities[mask]
    yields = yields[mask]

    if len(maturities) < 4:
        y_flat = float(np.nanmean(yields)) if len(yields) else 0.0
        return _FlatNSSCurve(y_flat)

    # -----------------------------------------------
    # 2. Variance test (if too flat, skip NSS)
    # -----------------------------------------------
    y_std = np.nanstd(yields)
    if y_std < 1e-5:
        y_flat = float(np.nanmean(yields))
        return _FlatNSSCurve(y_flat)

    # -----------------------------------------------
    # 3. Safe NSS functional form
    # -----------------------------------------------
    def safe_nss_func(t, beta0, beta1, beta2, tau1, tau2):
        t = np.maximum(np.asarray(t), 1e-6)
        tau1 = np.maximum(tau1, 1e-4)
        tau2 = np.maximum(tau2, 1e-4)

        x1 = t / tau1
        x2 = t / tau2

        # safe exponentials
        x1 = np.clip(x1, -700, 700)
        x2 = np.clip(x2, -700, 700)

        term1 = (1 - np.exp(-x1)) / x1
        term2 = term1 - np.exp(-x1)
        term3 = ((1 - np.exp(-x2)) / x2) - np.exp(-x2)

        y = beta0 + beta1 * term1 + beta2 * term2

        # if imaginary numbers appear, return real part
        if np.iscomplexobj(y):
            y = np.real(y)

        # clip to plausible real yields
        return np.clip(y, -0.10, 0.30)

    # -----------------------------------------------
    # 4. Bounded curve_fit
    # -----------------------------------------------
    beta0_0 = float(np.nanmean(yields))
    p0 = [beta0_0, 0.0, 0.0, 2.0, 8.0]

    bounds = (
        [-0.10, -0.30, -0.30, 1e-4, 1e-4],  # lower
        [ 0.30,  0.30,  0.30, 50.0, 50.0],  # upper
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            warnings.simplefilter("ignore", category=opt.OptimizeWarning)

            params, _ = opt.curve_fit(
                safe_nss_func,
                maturities,
                yields,
                p0=p0,
                bounds=bounds,
                maxfev=20000,
            )
    except Exception:
        return _FlatNSSCurve(beta0_0)

    beta0, beta1, beta2, tau1, tau2 = params

    # -----------------------------------------------
    # 5. Robust curve object
    # -----------------------------------------------
    class _RobustNSSYieldCurve:
        def __init__(self, b0, b1, b2, t1, t2):
            self.b0 = float(b0)
            self.b1 = float(b1)
            self.b2 = float(b2)
            self.t1 = float(max(t1, 1e-4))
            self.t2 = float(max(t2, 1e-4))

        def yield_at(self, t: float) -> float:
            t = max(float(t), 1e-6)

            x1 = t / self.t1
            x2 = t / self.t2

            x1 = np.clip(x1, -700, 700)
            x2 = np.clip(x2, -700, 700)

            term1 = (1 - np.exp(-x1)) / x1
            term2 = term1 - np.exp(-x1)
            term3 = ((1 - np.exp(-x2)) / x2) - np.exp(-x2)

            y = self.b0 + self.b1 * term1 + self.b2 * term2

            if np.iscomplexobj(y):
                y = np.real(y)

            return float(np.clip(y, -0.10, 0.30))

    return _RobustNSSYieldCurve(beta0, beta1, beta2, tau1, tau2)


# ---------------------------------------------------------------------------
# Flat curve fallback
# ---------------------------------------------------------------------------

class _FlatNSSCurve:
    """
    Safe fallback: constant yield curve.
    """
    def __init__(self, y_flat: float):
        self.y_flat = float(y_flat)

    def yield_at(self, t: float) -> float:
        return float(self.y_flat)
