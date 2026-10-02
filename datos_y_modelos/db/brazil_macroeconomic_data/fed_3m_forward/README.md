# Fed 3M Forward audit source

## Purpose

This folder documents the Bloomberg source series used for the thesis baseline variable `fed_3m_forward` during the jury-revision Data Freeze Gate.

## Canonical source

- **Bloomberg ticker:** `USSOC Curncy`
- **Field:** `PX_LAST`
- **Instrument:** 3-month USD Overnight Indexed Swap (OIS) fixed rate
- **Curve context:** `YCSW0042 Index` (USD OIS curve)
- **Units:** percent / percentage points (for example, `0.1830` means 0.1830%)
- **Native frequency:** daily market observations

`FEDL01 Index` is **not** the source of the panel variable. `FEDL01 Index` is the U.S. Federal Funds Effective Rate and its historical month-end values do not match `fed_3m_forward` in the econometric panel.

## Monthly extraction convention

The audit series was extracted in BQNT from `USSOC Curncy` using `PX_LAST` with calendar-month-end dates and `fill='PREV'`.

This means the monthly value is the **last available Bloomberg market quote at month-end**. If the calendar month-end is not a quotation day, Bloomberg carries forward the most recent available quote.

Important date-label distinction:

- the BQNT monthly extract may label the row with the **calendar month-end** (for example, `2011-04-30`);
- the inherited market quote may actually come from the **last business/quotation day** (for example, `2011-04-29`);
- the thesis panel historically stores the actual observation/business-day date in cases such as `2011-04-29`, `2011-07-29`, and `2011-12-30`.

Therefore comparisons to the panel should be performed by month and value unless the underlying Bloomberg quote date is explicitly recovered.

## Independent source identification check

BQNT reproduced the first panel observations exactly from `USSOC Curncy / PX_LAST`:

| Panel observation date | Panel value | Bloomberg `USSOC Curncy` |
|---|---:|---:|
| 2010-12-31 | 0.1830 | 0.1830 |
| 2011-01-31 | 0.1585 | 0.1585 |
| 2011-02-28 | 0.1425 | 0.1425 |
| 2011-03-31 | 0.1315 | 0.1315 |
| 2011-04-29 | 0.1170 | 0.1170 |

This resolves the source/ticker audit as **PASS**.

## Raw-series audit

A daily BQNT history check over 2010-2025 confirmed that `USSOC Curncy` has observations throughout the thesis sample. The daily series contains non-quoted calendar days (for example weekends) as missing values, as expected for a market series.

The raw-series audit is therefore **PASS**.

## Monthly-convention audit

The 2011 monthly extraction reproduces the panel sequence exactly when `PX_LAST` is sampled at calendar month-end with previous-value fill. The monthly-convention audit is therefore **PASS**.

## Files

### `fed_3m_forward_ussoc_monthly_2010_2025.csv`

Canonical BQNT monthly source extract for the Data Freeze Gate audit.

Columns:

- `calendar_month_end`: calendar month-end label returned for the monthly extraction
- `ticker`: Bloomberg security identifier (`USSOC Curncy`)
- `field`: Bloomberg historical field (`PX_LAST`)
- `px_last_pct`: observed 3-month USD OIS rate in percentage points

The file contains **192 monthly observations** from January 2010 through December 2025 and no missing `PX_LAST` values.

## Data Freeze Gate status

As of this file version:

1. **Source/ticker:** PASS
2. **Raw series:** PASS
3. **Monthly convention:** PASS
4. **Panel match:** IN PROGRESS — full-sample comparison against distinct monthly `fed_3m_forward` observations in `panel_main_and_robustness.xlsx` still required
5. **Transformation/scaling:** NOT YET AUDITED
6. **Economic label:** NOT YET AUDITED

Do not rerun thesis regressions until all baseline explanatory variables have passed the Data Freeze Gate and the econometric panel is frozen.
