# WLA / DAP Historical Curve Reconstruction

## Purpose

This note documents how the historical Brazilian real-rate futures curve used in the thesis can be reconstructed and independently checked.

The relevant instrument is the **DAP / ID x IPCA futures curve** traded at B3. In Bloomberg, the generic family is identified by `WLA Index`.

The thesis sample contains **186 monthly curve observations from January 2010 through June 2025**.

Two replication routes are documented:

1. **Public / no Bloomberg license:** B3 historical daily files.
2. **Bloomberg license available:** Bloomberg Excel/BDS or BQuant/BQL.

The B3 route is the independent replication path for a reviewer without Bloomberg access.

---

## 1. Final monthly-date convention

The monthly curve date is the **actual usable WLA/DAP market observation date for the month**.

The first reconstruction used 186 generic weekday business-month-end candidate dates. A later audit found **21 candidate dates on which Bloomberg returned the historical WLA chain but every contract had `PX_LAST = NaN`**.

Those months were re-queried on the preceding usable WLA/DAP trading date. The final dataset still contains **186 monthly observations**, but these 21 dates were corrected:

| Original candidate | Corrected trading date |
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

The corrected date is retained as the actual observation date. For example, the December 2010 curve is dated **2010-12-30**; its market quotes are not relabeled as 2010-12-31.

### Why the mapping is explicit

The ANBIMA calendar used for BUS/252 day-count calculations is not, by itself, a sufficient source for identifying every B3/DAP trading closure. In particular, some year-end dates can be treated differently by the day-count calendar and by actual exchange quote availability.

For this reason, the 21 corrections were validated against actual Bloomberg/BQuant WLA quote availability and preserved explicitly as an audit trail.

---

## 2. Public replication using B3

B3 historical daily files are available at:

https://b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/

For a historical observation date:

1. Open the B3 historical daily bulletin page.
2. Select the **actual trading date** used by the monthly curve.
3. Download **Boletim de Negociação — BVBG.086.01 PriceReport**.
4. Identify the **DAP** futures contracts.
5. Use the official contract adjustment / settlement rate corresponding to the historical curve input.
6. Order live contracts by their actual maturity / valuation date.

This allows a reviewer to validate the underlying B3 settlement information without a Bloomberg license.

### Example validation

For **2018-09-28**, Bloomberg returned:

- `WLV18 Index`
- `PX_LAST = 0.000`

The corresponding B3 PriceReport showed the DAP V18 contract with an official adjustment rate of `0.000`, confirming that the Bloomberg zero was a valid market observation rather than a missing-value placeholder.

Therefore, the curve construction must retain legitimate:

- positive rates;
- zero rates; and
- negative rates.

Only genuinely missing observations (`NaN`) are unavailable.

---

## 3. Bloomberg Excel replication

With Bloomberg Excel access, the historical futures chain for a given date can be retrieved with:

```excel
=BDS("WLA Index","FUT_CHAIN","CHAIN_DATE=20240131","INCLUDE_EXPIRED_CONTRACTS=N")
```

Change `CHAIN_DATE` to the historical date to be replicated.

For example:

```excel
=BDS("WLA Index","FUT_CHAIN","CHAIN_DATE=20200630","INCLUDE_EXPIRED_CONTRACTS=N")
```

### Important: the chain length varies over time

The number of live contracts is not constant. Examples observed during the reconstruction include:

- 2020-06-30: 14 live contracts;
- 2024-01-31: 23 live contracts;
- 2025-06-30: 21 live contracts.

Historical generic positions must therefore not be reconstructed by assuming a fixed number of contracts or by treating `WL1`, `WL2`, ..., `WL21` as 1, 2, ..., 21 months.

The correct procedure is to reconstruct the actual live contract chain on each date and order the specific contracts by their true `FUTURES_VALUATION_DATE`.

---

## 4. Bloomberg BQuant / BQL replication

The notebook:

`wla_historical_curve_reconstruction.ipynb`

implements the acquisition and audit procedure.

The central function requests:

```python
universe = bq.univ.futures("WLA Index", dates=d)

items = {
    "Ticker": bq.data.id(),
    "PX_LAST": bq.data.px_last(dates=d),
    "FUTURES_VALUATION_DATE": bq.data.futures_valuation_date(),
}
```

For every date, the returned contracts are sorted by `FUTURES_VALUATION_DATE`, and only then is `CHAIN_POSITION` assigned.

The raw acquisition fields are:

- `CHAIN_DATE`
- `CHAIN_POSITION`
- `Ticker`
- `FUTURES_VALUATION_DATE`
- `PX_LAST`

### Acquisition workflow

1. Generate 186 weekday business-month-end **candidate** dates for January 2010–June 2025.
2. Query the full historical WLA futures chain on each candidate date.
3. Count non-missing `PX_LAST` observations by date.
4. Identify candidate dates on which the entire chain has missing `PX_LAST`.
5. Re-query the validated preceding WLA/DAP trading date for those months.
6. Save those 21 queries separately as `wla_replacement_dates_21_raw.xlsx`.
7. Remove the obsolete all-missing date blocks and insert the 21 corrected trading-date blocks.
8. Audit date coverage, duplicates, quote signs, and missing observations.
9. Export the corrected authoritative raw panel.

### Corrected thesis-window raw-data audit

For the frozen jury-revision dataset, the corrected panel contains:

- **186 usable monthly dates**;
- **3,144 contract-date rows**;
- **2,463 non-missing `PX_LAST` observations**;
- **681 missing individual `PX_LAST` observations**;
- **2 zero rates**;
- **99 negative rates**;
- **2,362 positive rates**.

These are audit statistics for the frozen thesis dataset. They are not filters to be imposed on future downloads.

---

## 5. Why `FUTURES_VALUATION_DATE` matters

The original spreadsheet approach treated generic positions as if they represented fixed monthly maturities. That is not correct.

`WL1 Index`, `WL2 Index`, etc. are generic rolling positions in the live futures chain. Contract spacing is irregular and changes over time.

For curve construction, tenor must therefore be calculated from:

```text
actual historical observation date -> actual futures valuation date
```

rather than from:

```text
generic position -> assumed number of months
```

The thesis code subsequently converts this date difference into the Brazilian **BUS/252** year fraction using the same day-count convention used elsewhere in the empirical pipeline.

---

## 6. Raw-data treatment

The acquisition deliberately preserves all observed rate signs.

### Keep

```text
PX_LAST > 0
PX_LAST = 0
PX_LAST < 0
```

All three can be legitimate DAP real-rate observations.

### Missing

```text
PX_LAST = NaN
```

Missing individual quotes remain unavailable. They are not automatically replaced or imputed.

Therefore, a rule such as:

```python
surface = surface[surface["yield"] > 0]
```

is inappropriate for the WLA/DAP real-rate curve because it would incorrectly delete valid zero and negative real rates.

---

## 7. Files and audit trail

The relevant files are:

- `wla_historical_curve_reconstruction.ipynb`  
  Reproducible Bloomberg/BQuant acquisition and validation notebook.

- `wla_replacement_dates_21_raw.xlsx`  
  Raw Bloomberg audit file for the 21 corrected trading dates.

- `wla_historical_chain_2010_2025_raw.xlsx`  
  Corrected authoritative raw WLA chain after replacing the 21 all-missing candidate-date blocks.

- `hist_ipca_curve_contracts_db.xlsx`  
  Legacy-compatible production workbook consumed by the thesis Python pipeline.

- `download_file.py`  
  Small BQuant/Jupyter helper used to save files and expose a browser download button. It does not alter market data or curve calculations.

### Production workbook audit after the date correction

The corrected `hist_ipca_curve_contracts_db.xlsx` returns:

- **186 raw curve dates**;
- **186 usable curve dates** through `load_ipca_surface()`;
- **2,463 usable WLA observations**;
- no completely missing monthly curve date.

The BQuant replacement download does not require volume for the real curve. The production `load_ipca_surface()` function does not use volume.

---

## 8. Downstream thesis transformations

The raw acquisition is intentionally separated from subsequent transformations.

The thesis Python pipeline is responsible for:

1. calculating BUS/252 tenor from `CHAIN_DATE` to `FUTURES_VALUATION_DATE`;
2. converting Bloomberg/B3 rate quotes from percentage points to decimal rates;
3. excluding only genuinely unavailable observations when constructing the usable surface;
4. preserving valid zero and negative real rates;
5. interpolating the WLA curve at the tenors required by the corporate-spread calculation.

This separation makes the data acquisition, curve construction, and spread calculation independently auditable and version-controlled.

---

## 9. Reproducibility principle

Bloomberg/BQL is used as a convenient historical data-retrieval layer. The underlying contracts are B3-listed DAP futures, and the public B3 route provides the independent validation path.

The key reproducibility rule is that the monthly observation must correspond to a date on which usable WLA/DAP market data actually exist. A generic calendar month-end must not be retained merely because it is a weekday if the historical market data are unavailable on that date.
