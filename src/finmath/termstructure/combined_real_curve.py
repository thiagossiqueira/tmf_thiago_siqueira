from dataclasses import dataclass

@dataclass
class CombinedRealCurve:
    wla_func: callable
    model_curve: callable
    t_switch: float = 5.0

    def __post_init__(self):
        wla_5 = self.wla_func(self.t_switch)
        model_5 = self.model_curve.yield_at(self.t_switch)
        self.delta = wla_5 - model_5

    def yield_at(self, t: float) -> float:
        if t <= self.t_switch:
            return float(self.wla_func(t))
        return float(self.model_curve.yield_at(t) + self.delta)
