# WLA / DAP Historical Curve Reconstruction

## Purpose

This note documents how the historical Brazilian real-rate futures curve used in the thesis can be reconstructed and independently checked.

The relevant instrument is the **DAP / ID x IPCA futures curve** traded at B3. In Bloomberg, the generic family is identified by `WLA Index`.

The thesis sample covered month-end observations from **2010-01-29 to 2025-06-30**.

Two replication routes are documented below:

1. **Public / no Bloomberg license:** use B3 historical daily files.
2. **Bloomberg license available:** use either Excel/BDS or BQuant/BQL.

The B3 route is the appropriate independent replication path for a reviewer without Bloomberg access.

---

## 1. Public replication using B3

B3 historical daily files are available at:

https://b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/

For a given historical date:

1. Open the page above.
2. Select the desired date.
3. Download **Boletim de Negociação — BVBG.086.01 PriceReport**.
4. In the downloaded file, identify the **DAP** futures contracts.
5. Use the contract settlement / adjustment rate for the historical curve.
6. Order the live contracts by their actual maturity / valuation date.

This allows a reviewer to validate the same underlying B3 settlement information without a Bloomberg license.

### Example validation performed

For **2018-09-28**, Bloomberg returned:

- `WLV18 Index`
- `PX_LAST = 0.000`

The corresponding B3 PriceReport for that date showed the DAP V18 contract with an official adjustment rate of `0.000`, confirming that the Bloomberg zero was a valid market observation rather than a missing-value placeholder.

This is important because the curve construction must retain valid:

- positive rates;
- zero rates; and
- negative rates.

Only genuinely missing observations should be treated as unavailable.

---

## 2. Bloomberg Excel replication

With Bloomberg Excel access, the historical futures chain for a given date can be retrieved with:

```excel
=BDS("WLA Index","FUT_CHAIN","CHAIN_DATE=20240131","INCLUDE_EXPIRED_CONTRACTS=N")
```

Change `CHAIN_DATE=20240131` to the historical date to be replicated.

For example:

```excel
=BDS("WLA Index","FUT_CHAIN","CHAIN_DATE=20200630","INCLUDE_EXPIRED_CONTRACTS=N")
```

The returned chain should contain the contracts that were live on that date.

### Important

The number of live contracts is **not constant over time**.

For example:

- 2020-06-30 had 14 live contracts;
- 2024-01-31 had 23 live contracts;
- 2025-06-30 had 21 live contracts.

Therefore, historical generic positions must not be reconstructed by assuming a fixed number of contracts or by assuming that `WL1`, `WL2`, ..., `WL21` correspond to 1, 2, ..., 21 months.

The correct procedure is to reconstruct the actual live contract chain on each date and order contracts by their true maturity / valuation date.

---

## 3. Bloomberg BQuant / BQL replication

The accompanying notebook:

`wla_historical_curve_reconstruction.ipynb`

uses BQuant/BQL to:

1. request the historical `WLA Index` futures universe for each month-end;
2. retrieve each specific contract ticker;
3. retrieve `PX_LAST`;
4. retrieve `FUTURES_VALUATION_DATE`;
5. sort contracts by actual valuation date;
6. assign a historical chain position;
7. preserve missing, zero, negative and positive observations;
8. export the full historical panel to Excel and CSV.

The exported raw dataset contains:

- `CHAIN_DATE`
- `CHAIN_POSITION`
- `Ticker`
- `FUTURES_VALUATION_DATE`
- `PX_LAST`

For the thesis window the resulting raw extraction contains:

- **186 month-end dates**
- **3,143 contract-date observations**
- **966 missing PX_LAST values**
- **2 zero rates**
- **86 negative rates**
- **2,089 positive rates**

No rate-sign filter is applied to the raw Bloomberg extraction.

---

## 4. Why `FUTURES_VALUATION_DATE` matters

The old spreadsheet approach treated generic positions as if they represented fixed monthly maturities.

That is not correct.

`WL1 Index`, `WL2 Index`, etc. are generic rolling positions in the live futures chain. Contract spacing is irregular and changes over time.

For curve construction, tenor must be calculated from:

```text
historical observation date -> actual futures valuation date
```

rather than from:

```text
generic position -> assumed number of months
```

The thesis code subsequently converts this date difference into the Brazilian **BUS/252** year fraction using the same calendar convention used elsewhere in the empirical pipeline.

---

## 5. Raw-data treatment

The raw historical extract deliberately preserves all observations.

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

Missing observations should remain unavailable at the raw-data stage. They should not be replaced automatically.

This means a rule such as:

```python
surface = surface[surface["yield"] > 0]
```

is inappropriate for the DAP/WLA real-rate curve because it would incorrectly delete valid zero and negative real rates.

---

## 6. Reproducibility note

The public B3 route is the independent source available to reviewers without Bloomberg.

Bloomberg Excel/BQL is used as a convenient data-retrieval layer, while the underlying contracts and settlement information originate from the B3-listed DAP market.

The raw extraction is intentionally kept separate from the subsequent thesis transformations. Tenor calculation, unit conversion, interpolation and corporate-spread construction should be performed in the thesis Python pipeline so that all conventions are explicit and version-controlled.
