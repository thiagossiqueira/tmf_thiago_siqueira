from dataclasses import dataclass

import pandas as pd

from src.finmath.termstructure.curve_models import (
    flat_forward_interpolation,
)


@dataclass
class CombinedRealCurve:
    wla_func: callable
    model_curve: callable
    t_switch: float
    t_blend_end: float

    def __post_init__(self):
        self.t_switch = float(self.t_switch)
        self.t_blend_end = float(self.t_blend_end)

        if self.t_blend_end <= self.t_switch:
            raise ValueError(
                "t_blend_end must be greater than t_switch"
            )

        # Last actually observed WLA zero-rate point.
        self.wla_switch_yield = float(
            self.wla_func(self.t_switch)
        )

        # NSS zero rate at the maturity of the first valid
        # NTN-B lying beyond the WLA observed range.
        self.nss_blend_end_yield = float(
            self.model_curve.yield_at(self.t_blend_end)
        )

        # Kept only as a diagnostic measure of the difference
        # between WLA and NSS at the WLA boundary.
        self.delta = (
            self.wla_switch_yield
            - self.model_curve.yield_at(self.t_switch)
        )

        # Two zero-rate nodes defining the bridge.
        self.bridge_curve = pd.Series(
            [
                self.wla_switch_yield,
                self.nss_blend_end_yield,
            ],
            index=[
                self.t_switch,
                self.t_blend_end,
            ],
            dtype=float,
        )

    def yield_at(self, t: float) -> float:
        t = float(t)

        # 1. Inside observed WLA support:
        #    use WLA directly.
        if t <= self.t_switch:
            return float(self.wla_func(t))

        # 2. Between the last WLA point and the first
        #    valid NTN-B maturity:
        #    connect the two zero-rate nodes with the same
        #    flat-forward interpolation used elsewhere.
        if t < self.t_blend_end:
            return float(
                flat_forward_interpolation(
                    t,
                    self.bridge_curve,
                )
            )

        # 3. From the first NTN-B maturity onward:
        #    use the fitted sovereign NTN-B zero curve directly.
        return float(
            self.model_curve.yield_at(t)
        )