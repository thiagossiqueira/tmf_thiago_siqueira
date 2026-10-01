# Brazil 3M DI Market-Implied Rate

## Purpose

This folder contains the monthly Brazilian 3-month market-implied short-term interest-rate series used for WP-04 of the thesis:

**Determinantes de los diferenciales de bonos corporativos en moneda local en Brasil: panel 2010–2025**

WP-04 is the referee-response work package:

> Clarify SELIC baseline non-inclusion and run referee-only SELIC 3M Forward check(s).

The baseline thesis specification does not add SELIC as an additional explanatory variable. The series documented here is collected separately for referee-only robustness analysis.

## Files

- `brazil_3m_di_ycsw0089_monthly.csv` — monthly Bloomberg series, 2010-12 through 2025-12.
- `TFM_WP04_Brazil_3M_DI_YCSW0089.ipynb` — reproducible Bloomberg BQuant/BQL extraction notebook.
- `README.md` — this documentation.

## Bloomberg source

- Curve: `YCSW0089 Index`
- Tenor: `3M`
- Market: BM&F Pre x DI / DI1 futures
- Environment: Bloomberg BQuant / Bloomberg Query Language (BQL)
- Frequency: calendar month-end
- Sample: 2010-12-31 through 2025-12-31

## Economic interpretation

The series is the 3-month point on Bloomberg's BM&F Pre x DI curve.

The underlying instruments are Brazilian one-day interbank deposit (DI1) futures. DI futures embed market expectations of future Brazilian short-term interest rates. Because CDI/DI closely tracks the SELIC policy rate, the 3M DI curve point is a forward-looking measure of domestic monetary conditions.

## Terminology

The raw variable should be referred to as `brazil_3m_di` or `Brazil 3M DI market-implied rate`.

It should not automatically be called a literal `SELIC 3M forward-starting rate`. The observation is the 3-month point on the Pre x DI curve from the observation date, which differs from a true 3M x 6M forward-starting rate.

## Relationship to `fed_3m_forward`

This series does **not** replace the existing `fed_3m_forward` variable in the econometric panel.

`fed_3m_forward` remains the international short-rate control. The Brazil 3M DI series is an additional domestic monetary-policy expectations proxy for WP-04 robustness checks.

## Reproduction

Run `TFM_WP04_Brazil_3M_DI_YCSW0089.ipynb` inside Bloomberg BQuant with access to `bql` and `pandas`.

The notebook requests the historical 3M member of `YCSW0089 Index` at each month-end and stores both the historical curve rate and the Bloomberg member ticker.

Core BQL logic:

```python
universe = bq.univ.curvemembers(
    symbols="YCSW0089 Index",
    tenors=["3M"],
    dates=d
)

items = {
    "Curve Rate": bq.data.curve_rate(dates=d),
    "Ticker": bq.data.id(),
}
```

## Output columns

| Column | Description |
|---|---|
| `obs_date` | Requested calendar month-end date |
| `curve` | Bloomberg curve identifier |
| `tenor` | Requested tenor |
| `curve_rate` | Historical 3M DI curve rate |
| `member_ticker` | Bloomberg DI futures instrument representing the historical 3M curve point |
| `bloomberg_date` | Date returned by Bloomberg |
| `status` | Extraction status |

## Units

`curve_rate` is an annualized percentage rate. Example: `11.15` = `11.15%` per year.

## Month-end convention

The notebook generates calendar month-end dates using pandas frequency `M`.

No manual forward-fill, backward-fill, interpolation, or date substitution is performed.

## WP-04 econometric use

After validation and merge into the econometric panel, candidate referee-only specifications include:

1. Brazil 3M DI included together with nominal `fed_3m_forward`.
2. Brazil 3M DI included while `fed_3m_forward` is omitted.

The purpose is diagnostic: assess whether a forward-looking domestic short-rate measure adds incremental information and whether its inclusion materially changes the coefficients of interest.

These checks do not redefine the baseline model.

## Validation before regression use

Before merging into the panel, verify:

1. Complete historical coverage over 2010-2025.
2. Missing observations.
3. Duplicate month-end observations.
4. Historical curve membership.
5. Rate units and scaling.
6. Requested dates versus Bloomberg-returned dates.
7. Plausibility relative to the SELIC/CDI cycle.
8. Correlation with existing macro controls.
9. Multicollinearity diagnostics in the robustness regressions.

## Permanent local location

Save all three files under:

`C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira\datos_y_modelos\db\brazil_macroeconomic_data\brazil_3m_di_forward`

## Data provenance

Source: Bloomberg Professional / Bloomberg Query Language (BQL)

Curve: `YCSW0089 Index`

Tenor: `3M`

No Bloomberg observations are hard-coded in the notebook.
