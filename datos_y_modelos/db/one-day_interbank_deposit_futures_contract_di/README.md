# Brazil DI Curve Reconstruction (2010–2025)

## Reproducibility notes for `di_curve.v6.xlsx`

This folder documents the reconstruction of the Brazilian nominal local reference curve used in the thesis **“The determinants of corporate bond spreads in local currency in Brazil: a panel study 2010–2025.”** The objective of the data work is to produce a transparent, auditable monthly panel of short-, medium-, and long-end nominal BRL reference-rate instruments that can later be used to interpolate a same-date local reference curve.

The final workbook documented here is:

- `di_curve.v6.xlsx`

The BQuant/BQNT acquisition and audit code is stored in:

- `di_curve_bqnt_download_and_audit.ipynb`

Two intermediate audit files produced by the notebook are useful to retain with the repository:

- `di_futures_2010_2025_raw.xlsx`
- `di_generic_mapping_od1_od60_2010_2025.xlsx`

---

## 1. Final `di_curve.v6.xlsx` structure

`di_curve.v6.xlsx` contains one values-only worksheet named `only_values`.

Validated dimensions:

- Period: **2010-01-29 to 2025-06-30**
- Frequency: **monthly**
- Canonical observation dates: **186**
- Rows: **13,392**
- Rows per date: **72**
  - Cash: **1**
  - DI futures: **46**
  - Pre × DI swaps: **25**

Columns:

| Column | Meaning |
|---|---|
| `id` | Unique row identifier |
| `Months` | Legacy relative-month metadata |
| `Relative days` | Legacy relative-day metadata |
| `Relative months` | Legacy relative-month metadata |
| `Curve date` | Canonical monthly observation date |
| `Generic ticker` | Bloomberg generic/instrument identifier used in the workbook |
| `Settlement date` | Legacy settlement metadata where applicable |
| `Settlement days` | Legacy settlement-day metadata |
| `End of Month date` | Legacy name; for futures this may represent the contract valuation/maturity date used to construct tenor |
| `End of Month days` | Business-day distance used for tenor construction |
| `Term` | Tenor in years on a BUS/252 basis |
| `px_last` | Bloomberg market quote |
| `volume` | Futures MTD trading volume; sentinel value for cash/swaps |
| `Type` | Instrument leg: `Cash`, `future`, or `Swap` |
| `Specific ticker` | Dated ODA futures contract where available |

The `Type` field is essential. It allows downstream code to apply different eligibility rules to cash, futures, and swaps even when tenors overlap.

---

## 2. Canonical monthly date grid

The sample contains one observation per month from January 2010 through June 2025, for a total of 186 months.

The working process initially used month-end dates. A later audit against the usable Bloomberg/B3 trading dates identified 21 months where the prior date needed to be replaced by the preceding usable observation date.

The 21 validated replacements are:

| Original date | Canonical date |
|---|---|
| 2010-12-31 | 2010-12-30 |
| 2011-12-30 | 2011-12-29 |
| 2012-12-31 | 2012-12-28 |
| 2013-03-29 | 2013-03-28 |
| 2013-12-31 | 2013-12-30 |
| 2014-12-31 | 2014-12-30 |
| 2015-12-31 | 2015-12-30 |
| 2016-12-30 | 2016-12-29 |
| 2017-02-28 | 2017-02-24 |
| 2017-12-29 | 2017-12-28 |
| 2018-03-30 | 2018-03-29 |
| 2018-05-31 | 2018-05-30 |
| 2018-12-31 | 2018-12-28 |
| 2019-12-31 | 2019-12-30 |
| 2020-12-31 | 2020-12-30 |
| 2021-12-31 | 2021-12-30 |
| 2022-02-28 | 2022-02-25 |
| 2022-12-30 | 2022-12-29 |
| 2023-12-29 | 2023-12-28 |
| 2024-03-29 | 2024-03-28 |
| 2024-12-31 | 2024-12-30 |

These dates are treated as the authoritative monthly observation grid. The reconstruction does **not** interpolate across observation dates and does **not** substitute prices from a later date.

---

## 3. Curve legs

### 3.1 Cash: `BZDIOVRA Index`

The beginning of the curve is the Brazilian DI Over rate (`BZDIOVRA Index`).

The Bloomberg Excel retrieval used for the corrected-date refresh is exact-date daily history:

```excel
=BDH($F2,L$1,$E2,$E2,"per=d","days=trading","CDR=BZ","dts=h","QtTyp=P")
```

The change from `per=m` to `per=d` was necessary because the monthly-history request returned zero on some corrected observation dates even though the exact daily market observation existed.

#### Cash tenor

The DI Over rate represents a one-business-day interbank deposit rate, annualized on a 252-business-day basis. The cash node is therefore normalized to:

```text
Term = 1 / 252 = 0.003968253968253968
```

for **all 186 dates**.

This avoids accidentally interpreting a multi-calendar-day holiday/weekend gap as more than one DI business-day accrual period.

Public B3 references:

- https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-apuracao-da-taxa/
- https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-calculo-do-indice-di/
- https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-calcudo-acumulado-de-di/

#### Cash volume field

A futures-style trading-volume screen is not economically applicable to the DI Over cash quote. To preserve compatibility with the existing data schema, the cash rows use the hardcoded sentinel:

```text
volume = 1,000,000
```

This value is **not an observed market volume** and must not be interpreted as such.

---

### 3.2 DI / ODA futures

The futures leg was reconstructed in BQuant using Bloomberg BQL/BQNT.

Key Bloomberg fields/functions:

- historical futures universe: `bq.univ.futures("ODA Comdty", dates=...)`
- generic-to-specific mapping: `FUT_CUR_GEN_TICKER`
- exact-date quote: `PX_LAST`
- actual futures maturity/valuation date: `FUTURES_VALUATION_DATE`
- daily futures volume: `PX_VOLUME`

#### Why generic tickers were audited

The original spreadsheet had constructed some generic names from chronological month numbers (`od` + month number). The WLA reconstruction showed that this type of manual positional labeling can be wrong. Therefore, DI generic labels were independently checked using Bloomberg's historical `FUT_CUR_GEN_TICKER` field rather than inferred from calendar position.

The audit queried `OD1 Comdty` through `OD60 Comdty` for all 186 observation dates.

Audit result:

- `OD1`–`OD48`: Bloomberg returned a specific underlying contract on all 186 dates.
- `OD49`–`OD60`: no underlying contract was returned on any of the 186 dates.
- No date/specific-contract combination mapped to more than one generic ticker.

This gives an auditable generic-to-specific relation such as:

```text
OD1 Comdty  -> ODF25 Comdty
OD13 Comdty -> ODF26 Comdty
OD16 Comdty -> ODJ26 Comdty
```

on 2024-12-30.

#### Exact-date futures price

`PX_LAST` is requested on the canonical observation date. No monthly-period fill is used for the futures price.

#### Futures maturity / tenor

`FUTURES_VALUATION_DATE` is retained as the actual dated-contract maturity/valuation field. This is preferable to inferring maturity from a generic number.

#### Futures volume convention

The legacy workbook had used Bloomberg monthly historical volume. Exact-date BQNT `PX_VOLUME`, however, is a daily value. To make the BQNT reconstruction comparable with the legacy field without introducing look-ahead, monthly-to-date futures volume is reconstructed as:

```text
MTD volume(date t)
    = sum of daily PX_VOLUME
      from the first calendar day of t's month
      through canonical observation date t
```

Two anchor checks exactly reproduced the legacy monthly volume:

| Date | Contract | PX_LAST | Reconstructed MTD volume |
|---|---|---:|---:|
| 2010-12-30 | ODF11 Comdty | 10.650 | 15,290,095 |
| 2024-12-30 | ODF25 Comdty | 12.154 | 11,617,795 |

This validates the MTD accumulation convention.

#### Liquidity screen

The intended liquidity/data-quality screen is:

```text
volume > 1,000
```

but it should apply **only to futures**. The screen was originally introduced because very low-volume futures nodes produced implausible spikes in the curve.

It must not be applied as an economic filter to the cash or swap legs.

---

### 3.3 Pre × DI swaps

The workbook contains 25 pre × DI swap quotes (`BCSF*PDV Curncy`) spanning short through long tenors. The swap leg provides especially important long-end coverage where futures are sparse or missing.

The corrected-date Bloomberg retrieval also uses exact-date daily history:

```excel
=BDH($F2,L$1,$E2,$E2,"per=d","days=trading","CDR=BZ","dts=h","QtTyp=P")
```

Missing Bloomberg quotes are retained as missing. They are not filled from another date and are not replaced by interpolated market observations at the data-acquisition stage.

As with cash, a futures-style volume field is not applicable. For schema compatibility:

```text
volume = 1,000,000
```

for swap rows.

This is a sentinel value, not observed trading volume.

---

## 4. Overlapping tenors are intentional in the raw dataset

Cash, futures, and swaps can have the same or nearly the same tenor. This is intentional at the raw-data stage.

The principle is:

1. preserve available market observations;
2. keep the source type (`Cash`, `future`, `Swap`) explicit;
3. apply source eligibility/priority rules only when constructing the actual interpolated curve.

A raw overlap is therefore not treated as a data error.

The downstream curve builder should not blindly average all overlapping instruments. It should select eligible nodes by type, liquidity, price availability, and the intended futures/swap splice.

The thesis design is to use the DI market for the short/medium nominal BRL curve and pre × DI swaps for the longer end. The precise splice should be implemented explicitly in code rather than implicitly by row ordering.

---

## 5. Validation status of `di_curve.v6.xlsx`

Validated properties of the current workbook:

| Test | Result |
|---|---:|
| Unique canonical dates | 186 |
| First date | 2010-01-29 |
| Last date | 2025-06-30 |
| Rows per date | 72 |
| Cash rows | 186 |
| Futures rows | 8,556 |
| Swap rows | 4,650 |
| Total rows | 13,392 |
| Cash prices present | 186 / 186 |
| Swap prices present | 4,184 / 4,650 |
| Futures rows with specific ticker | 7,998 / 8,556 |
| Corrected replacement dates present | 21 / 21 |
| Cash `Term` | exactly `1/252` on 186 / 186 rows |
| Cash sentinel volume | 1,000,000 on 186 / 186 rows |
| Swap sentinel volume | 1,000,000 on 4,650 / 4,650 rows |

The remaining missing swap prices are preserved as missing observations rather than fabricated values.

---

## 6. Important review point: current futures slots in `v6`

`di_curve.v6.xlsx` still preserves the earlier 46-row-per-date futures layout:

```text
OD1–OD43, OD54, OD57, OD59
```

The later Bloomberg mapping audit showed:

```text
OD1–OD48  -> valid specific contract on all 186 dates
OD49–OD60 -> no specific contract on any date
```

Consequently:

- `OD54`, `OD57`, and `OD59` in `v6` have no specific ticker, price, or futures volume on all 186 dates and are therefore inert after normal availability filters.
- `OD44`–`OD48` are not present in the `v6` snapshot even though the Bloomberg mapping audit found valid specific contracts.

This is deliberately documented rather than silently changed in the historical workbook. Before the **final production curve** is frozen, the curve-construction step should explicitly decide whether to expand the futures leg to `OD1`–`OD48` and remove the empty legacy placeholders.

The notebook provides the OD1–OD60 audit needed to make that decision reproducibly.

---

## 7. Reproduction workflow

### Prerequisites

- Bloomberg BQuant / BQNT environment
- Bloomberg entitlement to the relevant DI/ODA and swap data
- Python packages:
  - `bql`
  - `pandas`
  - `openpyxl`

### Step A — Build the 186 canonical dates

Run the canonical-date cell in `di_curve_bqnt_download_and_audit.ipynb`.

### Step B — Rebuild futures market data

Run the BQNT futures acquisition section. It retrieves:

- historical generic-to-specific mapping;
- exact-date `PX_LAST`;
- `FUTURES_VALUATION_DATE`;
- MTD `PX_VOLUME`.

The notebook writes:

```text
di_futures_2010_2025_raw.xlsx
```

### Step C — Re-run the generic audit

Query `OD1`–`OD60` on each canonical date using historical `FUT_CUR_GEN_TICKER`.

The notebook writes:

```text
di_generic_mapping_od1_od60_2010_2025.xlsx
```

### Step D — Refresh cash and swap quotes

Use the exact-date Bloomberg Excel formula:

```excel
=BDH($F2,L$1,$E2,$E2,"per=d","days=trading","CDR=BZ","dts=h","QtTyp=P")
```

Then paste the refreshed results as values into the values-only production workbook.

### Step E — Apply final schema conventions

- Cash `Term = 1/252`.
- Cash `volume = 1,000,000` sentinel.
- Swap `volume = 1,000,000` sentinel.
- Futures retain observed/reconstructed MTD volume.
- Missing market prices remain missing.

### Step F — Validate before curve construction

Run the final audit section in the notebook against `di_curve.v6.xlsx` (or the next production version).

---

## 8. Downstream implementation rules

The data workbook is an acquisition/staging layer. The downstream curve builder should follow these rules:

1. Use the **same observation date** for the market curve and the security being priced.
2. Never average DI curve observations across different dates.
3. Apply `volume > 1000` to **futures only**.
4. Do not reject cash or swaps because their `volume` is a sentinel.
5. Exclude missing/zero price nodes before interpolation.
6. Resolve overlapping tenors by an explicit source-priority/splice rule rather than by row order.
7. Use BUS/252 for nominal Brazilian curve tenor conventions where applicable.
8. Preserve the raw inputs so every selected curve node can be traced back to its Bloomberg security and observation date.

---

## 9. Why these changes were made

The reconstruction was driven by jury-review requirements concerning the definition of the corporate spread and the local benchmark. The audit identified several risks in the earlier implementation:

- month-end dates that were not usable trading observations;
- monthly Bloomberg formulas returning zero on replacement dates despite valid exact-date data;
- generic futures labels inferred from chronological month numbers rather than Bloomberg's historical mapping;
- daily versus monthly futures-volume semantics;
- a global volume screen that could incorrectly eliminate non-futures curve legs;
- cash tenor being affected by calendar gaps rather than represented consistently as one DI business day.

Each of these points is now either corrected in `v6` or explicitly exposed as a documented review item before final curve estimation.

---

## 10. Repository suggestion

A minimal reproducibility folder can be organized as:

```text
data/
  di_curve.v6.xlsx
  di_futures_2010_2025_raw.xlsx
  di_generic_mapping_od1_od60_2010_2025.xlsx

notebooks/
  di_curve_bqnt_download_and_audit.ipynb

README.md
```

The raw Bloomberg-derived files should be stored only if permitted by the relevant Bloomberg data licensing and repository-access rules. If raw licensed data cannot be committed, retain the notebook and README and document where the authorized data file is stored internally.

---

## 11. References

### B3

- B3 — Metodologia de Apuração da Taxa DI:  
  https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-apuracao-da-taxa/

- B3 — Metodologia de Cálculo Acumulado de DI:  
  https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-calcudo-acumulado-de-di/

- B3 — Metodologia de Cálculo do Índice DI:  
  https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/di/metodologia-de-calculo-do-indice-di/

### Bloomberg fields used

- `PX_LAST`
- `PX_VOLUME`
- `FUTURES_VALUATION_DATE`
- `FUT_CUR_GEN_TICKER`
- historical futures universe: `bq.univ.futures(...)`

Bloomberg field definitions and BQL/BQNT access require a Bloomberg-authorized environment.
