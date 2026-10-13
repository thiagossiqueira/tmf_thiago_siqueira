# Real Brazil 3M DI Rate Adjusted for Expected IPCA

## Purpose

This directory contains the reproducible construction of a **Brazilian real 3-month monetary-rate measure** used in the final econometric revisions of the Master's thesis:

> *The determinants of corporate bond spreads in local currency in Brazil: a panel study 2010–2025.*

The variable was constructed during the jury-revision process after thesis director **Prof. Martín Grandes** requested that the final specification include a Brazilian short-term monetary-rate measure adjusted for inflation expectations, described in the proposed regression table as:

> **SELIC 3M FWD RATE (CENTRAL BANK 3M FWD ADJUSTED FOR INFLATION EXPECTATIONS)**

The implementation operationalizes that request using the already validated Brazilian 3-month DI market-implied nominal rate and an independent measure of expected IPCA inflation from Banco Central do Brasil's Focus survey.

The underlying source should therefore be described precisely as a **Brazil 3M DI market-implied rate adjusted for expected IPCA**, rather than as a literal forward-starting SELIC contract.

---

## Why this variable was constructed

The final thesis specification requires nominal short-term interest-rate expectations to be expressed in real terms.

For the United States, the project already constructs a Real Fed 3M measure by combining:

1. a nominal 3-month forward/market rate; and
2. horizon-consistent expected CPI inflation.

The Brazil variable follows the same economic logic.

A nominal Brazilian 3M DI rate already existed and had been validated in the project. What was missing was an independent, point-in-time expected-inflation series with a horizon consistent with the approximately three-month nominal rate.

Using realized future inflation would introduce look-ahead bias.

Using the project's WLA / DAP (ID x IPCA) real-rate futures curve to infer inflation and then deflate the same nominal DI curve would also be undesirable for this purpose because it would mechanically combine two market curves and make the resulting "expected inflation" measure partly circular.

For that reason, the inflation expectation is sourced independently from the **Banco Central do Brasil Focus survey**.

---

## Request and construction metadata

- **Requested by:** Prof. Martín Grandes, thesis director.
- **Context:** jury-revision / final econometric specification.
- **Requested construct:** Brazilian 3-month monetary rate adjusted for inflation expectations.
- **Construction date:** 12-Oct-2026.
- **Focus retrieval date:** 12-Oct-2026, when the reproducible builder was executed.
- **Panel horizon covered:** 2010-12-30 through 2025-06-30.
- **Frozen panel dates covered:** 175 / 175.
- **Missing required values:** 0.
- **Frozen panel overwritten:** No.

---

## Directory contents

The reproducible workflow uses:

### Scripts

- `scripts/build_real_brazil_3m_focus.py`
- `scripts/build_real_brazil_3m_rate.py`

### Generated outputs

- `focus_ipca_3m_expected_panel_dates.csv`
- `real_brazil_3m_focus_panel_dates.csv`

### Upstream project inputs

- `datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt.xlsx`
- `datos_y_modelos/db/brazil_macroeconomic_data/brazil_3m_di_forward/brazil_3m_di_ycsw0089_monthly.xlsx`
- `datos_y_modelos/db/one-day_interbank_deposit_futures_contract_di/di_curve.v6.xlsx`

The econometrics panel is used only to obtain the canonical panel observation dates. It is not modified by either builder.

---

## Nominal rate

### Primary source

The nominal leg is the existing project series:

`datos_y_modelos/db/brazil_macroeconomic_data/brazil_3m_di_forward/brazil_3m_di_ycsw0089_monthly.xlsx`

Bloomberg curve:

`YCSW0089 Index`

Curve point:

`3M`

The series represents the 3-month point of the Brazilian **BM&F Pre x DI / DI1** market curve.

The associated futures contract/member ticker changes through time. Examples include:

- `ODQ11 Comdty` on 2011-04-29
- `ODQ20 Comdty` on 2020-04-30
- `ODQ24 Comdty` on 2024-04-30

### Important naming convention

The Bloomberg 3M curve point is a **market-implied Brazilian DI short rate**.

It should not be described in the underlying data/code as a literal forward-starting SELIC rate.

Preferred internal terminology:

- `nominal_brazil_3m_di_pct`
- `real_brazil_3m_focus`
- `real_brazil_3m_focus_exact`

In thesis tables or explanatory text it may be described as a Brazil Real 3M DI / SELIC-market-implied short-rate measure, provided the source convention is explained.

### Independent canonical validation

The nominal monthly series is independently checked against:

`datos_y_modelos/db/one-day_interbank_deposit_futures_contract_di/di_curve.v6.xlsx`

For every one of the 175 panel dates, the builder matches:

- exact frozen-panel observation date;
- exact DI futures member ticker; and
- exact observed market rate.

Result:

**Maximum difference between the monthly YCSW0089 rate and the exact-date canonical DI contract rate: 0.0 basis points.**

Thus the nominal leg is preserved exactly as previously validated; it is not reconstructed or interpolated again here.

---

## Expected inflation

### Source

Expected inflation is obtained from the **Banco Central do Brasil Focus / Sistema Expectativas de Mercado** OData service.

Selection:

- **Indicator:** `IPCA`
- **Statistic:** `Mediana`
- **Filter:** `baseCalculo = 0`
- **Resource:** `ExpectativaMercadoMensais`

Official sources:

- Banco Central Focus page:  
  https://www.bcb.gov.br/publicacoes/focus

- Banco Central Open Data — Expectativas de Mercado:  
  https://dadosabertos.bcb.gov.br/dataset/expectativas-mercado

- OData service documentation:  
  https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/documentacao

- OData monthly-expectations endpoint used by the builder:  
  https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais

### Vintage convention

For each frozen-panel observation date `t`, the query uses the Focus data available for that **exact observation date**.

No future Focus vintage is substituted.

This preserves the point-in-time information set and prevents look-ahead bias.

### Forecast horizon

For every panel observation date, the expected-inflation horizon is the **next three full calendar months**.

For example, for:

`2011-04-29`

the builder uses:

- May 2011 IPCA median: `0.43%`
- June 2011 IPCA median: `0.25%`
- July 2011 IPCA median: `0.30%`

The current calendar month is not included.

Coverage was checked over all frozen-panel dates:

- Panel dates: **175**
- Dates with all three required Focus monthly forecasts: **175**
- Missing forecast horizons: **0**
- Fallbacks or imputations: **None**

---

## Inflation transformation

Let the three monthly Focus IPCA medians, expressed in percentage points, be:

`pi_1`, `pi_2`, and `pi_3`.

### Step 1 — compound the next three monthly expectations

The expected price-level increase over the next three full calendar months is:

```text
expected_ipca_3m
    = (1 + pi_1 / 100)
    * (1 + pi_2 / 100)
    * (1 + pi_3 / 100)
    - 1
```

The project stores the same quantity in percentage points as:

```text
expected_ipca_3m_pct
    = expected_ipca_3m * 100
```

### Step 2 — annualize the three-month expectation

The three-calendar-month expectation is annualized as:

```text
expected_ipca_ann_pct
    = ((1 + expected_ipca_3m)^4 - 1) * 100
```

The exponent of four is intentional.

The Focus expectation represents a fixed three-calendar-month horizon. Annualizing it using each DI futures contract's slightly varying BUS/252 residual tenor would mix two different horizon conventions and introduce false precision.

A separate comparison was performed against tenor-specific annualization using the actual DI contract `Term`. Across the 175 dates, the maximum difference in annualized expected inflation was approximately **0.5183 percentage point**. That comparison confirmed that the choice matters numerically, but it did not change the conceptual decision: the fixed three-calendar-month Focus horizon is annualized with a factor of four.

This convention is also consistent with the project's Real Fed 3M construction, where an annualized quarterly expected-inflation measure is compared with an annualized nominal 3-month interest rate.

---

## Real-rate definitions

### Primary measure

The primary thesis measure uses the standard short-rate approximation:

```text
real_brazil_3m_focus
    = nominal_brazil_3m_di_pct
    - expected_ipca_ann_pct
```

or, in compact notation:

```text
r ~= i - E(pi)
```

This is the same conceptual convention used for the project's primary Real Fed 3M measure.

### Exact Fisher companion

For robustness and auditability, the builder also calculates:

```text
real_brazil_3m_focus_exact
    = (
        (1 + nominal_brazil_3m_di_pct / 100)
        /
        (1 + expected_ipca_ann_pct / 100)
        - 1
      ) * 100
```

The Fisher version is retained as a companion measure.

It does **not** replace the primary subtraction-based specification unless explicitly required in a robustness test.

---

## Why Focus rather than WLA / DAP implied inflation

The project also contains a Brazilian real-rate futures curve derived from WLA / DAP (ID x IPCA).

That curve is useful as an independent market-real-rate cross-check, but it is **not** used to create the primary expected-inflation adjustment here.

The reason is methodological.

If expected inflation were first inferred from nominal DI and real WLA/DAP rates and the resulting expected inflation were then used to deflate the same nominal DI rate, the operation would be largely mechanical and would tend to reproduce the WLA/DAP real rate.

The thesis director's request was better interpreted as a nominal Brazilian short-term rate **adjusted for an independent inflation expectation**.

Banco Central do Brasil Focus provides that independent expectation.

Accordingly:

- **Focus IPCA expectation:** primary inflation-expectation input.
- **WLA / DAP real curve:** external market cross-check only.
- **Realized future IPCA:** not used, to avoid look-ahead bias.

---

## Reproducible build

The construction is divided into two stages.

### Stage 1 — build Focus expected IPCA

Script:

`scripts/build_real_brazil_3m_focus.py`

Run from the repository root:

```bash
python ./scripts/build_real_brazil_3m_focus.py
```

Output:

`datos_y_modelos/db/brazil_macroeconomic_data/real_brazil_3m/focus_ipca_3m_expected_panel_dates.csv`

The script:

1. reads the distinct observation dates from the frozen econometrics panel;
2. queries the official BCB Focus OData service;
3. selects the next three full calendar months;
4. retrieves the monthly IPCA median for each target month;
5. compounds the three monthly expectations;
6. annualizes the resulting three-month expectation;
7. checks date coverage, uniqueness, missingness, and predetermined validation dates;
8. writes the CSV only after validation succeeds.

The builder uses the Python standard library for the web request and therefore does not require the third-party `requests` package.

### Stage 2 — build Real Brazil 3M rate

Script:

`scripts/build_real_brazil_3m_rate.py`

Run:

```bash
python ./scripts/build_real_brazil_3m_rate.py
```

Output:

`datos_y_modelos/db/brazil_macroeconomic_data/real_brazil_3m/real_brazil_3m_focus_panel_dates.csv`

The script:

1. reads the validated Focus expected-inflation file;
2. reads the existing YCSW0089 nominal 3M DI series;
3. aligns the nominal series by calendar month to the exact frozen-panel observation date;
4. obtains the associated DI futures member ticker;
5. independently checks that member ticker against the exact panel date in `di_curve.v6.xlsx`;
6. verifies that the nominal YCSW0089 rate equals the canonical exact-date contract rate;
7. computes the primary real-rate measure;
8. computes the Fisher-exact companion;
9. validates row count, uniqueness, missingness, canonical source agreement, and fixed checkpoints;
10. writes the output only after all validations pass.

The frozen econometrics panel is **read-only** in this process and is not overwritten.

---

## Validation outcome

Construction completed successfully on **12-Oct-2026**.

Final coverage:

- Observations: **175 monthly panel dates**
- First date: **2010-12-30**
- Last date: **2025-06-30**
- Missing required values: **0**
- Nominal DI vs exact-date canonical DI maximum difference: **0.0 bp**

Selected validation checkpoints:

| Observation date | DI contract | Nominal Brazil 3M DI | Expected IPCA, annualized | Primary real rate | Fisher real rate |
|---|---|---:|---:|---:|---:|
| 2011-04-29 | ODQ11 Comdty | 12.050% | 3.990845% | 8.059155% | 7.749870% |
| 2020-04-30 | ODQ20 Comdty | 2.958% | 0.237565% | 2.720435% | 2.713988% |
| 2024-04-30 | ODQ24 Comdty | 10.341% | 2.303863% | 8.037137% | 7.856142% |

These checkpoints are hard-coded validation guards in the second-stage builder.

---

## Output fields

The final file `real_brazil_3m_focus_panel_dates.csv` retains both the estimation variable and audit fields.

Key fields include:

- `obs_date`
- `nominal_brazil_3m_di_pct`
- `member_ticker`
- `di_tenor_bus252`
- `expected_ipca_3m_pct`
- `expected_ipca_ann_pct`
- `ipca_exp_m1_pct`
- `ipca_exp_m2_pct`
- `ipca_exp_m3_pct`
- `target_m1`
- `target_m2`
- `target_m3`
- `real_brazil_3m_focus`
- `real_brazil_3m_focus_exact`
- `canonical_di_rate_pct`
- `nominal_di_canonical_diff_bp`

These fields allow a reviewer to reconstruct the calculation for any observation without relying only on the final real-rate column.

---

## External source references

### Banco Central do Brasil — Focus expectations

Focus publication page:

https://www.bcb.gov.br/publicacoes/focus

Open Data dataset — Expectativas de Mercado:

https://dadosabertos.bcb.gov.br/dataset/expectativas-mercado

OData documentation:

https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/documentacao

Monthly expectations endpoint used by the builder:

https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais

### B3 — DI1 futures contract

Official B3 DI1 contract specification:

https://www.b3.com.br/lumis/portal/file/fileDownload.jsp?fileId=8A828D2951C9C37701521D31E9CF661C

B3 documents the DI1 contract as the standardized one-day interbank deposit-rate futures contract and quotes the rate as an **effective annual interest rate on a 252-business-day basis**.

B3 DI Index methodology:

https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-calculo-do-indice-di/

### Bloomberg

The historical nominal curve used in the project is:

`YCSW0089 Index`

Bloomberg historical data require Bloomberg Terminal/data-service access and therefore do not have a fully reproducible public historical-data URL.

For independent validation without relying only on the Bloomberg workbook, the repository preserves the canonical DI contract observations in:

`datos_y_modelos/db/one-day_interbank_deposit_futures_contract_di/di_curve.v6.xlsx`

The second-stage builder verifies the Bloomberg-selected 3M member contract against that exact-date canonical dataset for every frozen-panel date.

---

## Data lineage

The intended lineage is:

```text
Frozen panel observation dates
        |
        +--> BCB Focus monthly IPCA medians
        |       |
        |       +--> next three full calendar months
        |       +--> compounded 3M expected IPCA
        |       +--> annualized expected IPCA
        |
        +--> YCSW0089 3M DI market rate
                |
                +--> exact-date/member-ticker check
                     against canonical di_curve.v6.xlsx

annualized nominal Brazil 3M DI
        -
annualized expected IPCA
        =
real_brazil_3m_focus

and, as companion:

Fisher(nominal DI, expected IPCA)
        =
real_brazil_3m_focus_exact
```

---

## Reproducibility and data-freeze principle

The construction follows the project's reproducibility policy:

```text
canonical inputs
    -> deterministic transformations
    -> validated derived variable
    -> econometric estimation dataset
```

Important safeguards:

- No regression is estimated inside these scripts.
- No frozen-panel variable is overwritten.
- The Focus input is point-in-time and does not use future vintages.
- Realized future inflation is not used.
- The nominal DI leg is independently reconciled to exact-date canonical contract data.
- Output is written only after validation passes.
- The primary and Fisher real-rate variants are both preserved for auditability.

The resulting Real Brazil 3M variable should enter the final econometric workflow only after this construction and validation step has passed.

---

## Replication checklist

A reviewer wishing to reproduce the files should:

1. clone the repository;
2. confirm that the frozen panel and nominal/canonical DI inputs listed above are present;
3. have internet access to the Banco Central do Brasil OData service;
4. run:

```bash
python ./scripts/build_real_brazil_3m_focus.py
python ./scripts/build_real_brazil_3m_rate.py
```

5. confirm that Stage 1 reports:
   - 175 rows;
   - range 2010-12-30 to 2025-06-30;
   - zero missing values;

6. confirm that Stage 2 reports:
   - 175 rows;
   - range 2010-12-30 to 2025-06-30;
   - zero missing required values;
   - maximum nominal-vs-canonical DI difference of 0.0 bp;
   - the three validation checkpoints shown above.

If those checks pass, the constructed series matches the validated project implementation as of 12-Oct-2026.
