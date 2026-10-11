# Real Fed 3M Robustness Input

## Purpose

This folder contains the raw official inputs and documentation used to construct a **real U.S. 3-month interest-rate robustness variable** for the thesis:

> *Determinantes de los diferenciales de bonos corporativos en moneda local en Brasil: panel 2010–2025*

The objective is to test a real version of the existing U.S. 3-month nominal-rate control by subtracting an **expected short-horizon U.S. inflation rate**, rather than backward-looking realized inflation.

---

## Why this robustness was requested

The baseline econometric specification uses a nominal U.S. 3-month OIS rate:

```text
Bloomberg ticker: USSOC Curncy
Panel variable:   fed_3m_forward
```

The inherited panel name `fed_3m_forward` is economically imprecise: the underlying Bloomberg instrument used in the thesis workflow is a **spot 3-month USD Overnight Indexed Swap (OIS) fixed rate**, not a forward-starting 3m×6m contract.

On 10–11 October 2026, thesis director **Martín Grandes** asked to check whether this short U.S. rate could also be expressed in **real terms**, i.e. after netting/subtracting inflation.

The director's request was conceptual: test a real version of the U.S. 3-month rate.

The implementation decision made for the thesis is to use a **forward-looking expected-inflation measure with an appropriately short horizon**, rather than trailing realized inflation.

---

## Requested by

**Martín Grandes**  
Thesis director.

Director instruction, paraphrased from the October 2026 discussion:

> Check whether the Fed 3M / flat-forward rate can also be shown in real terms by netting out inflation.

The choice of the Philadelphia Fed Survey of Professional Forecasters (SPF), and specifically its next-quarter CPI expectation, is the thesis author's methodological implementation of that request.

---

## Why the previous real-rate construction was rejected

A legacy script contained:

```text
fed_3m_real = fed_3m_forward - us_cpi_yoy
```

That construction was rejected for this robustness exercise because it combines:

- a forward-looking / short-horizon nominal 3-month market rate; with
- backward-looking 12-month realized CPI inflation.

The revised construction uses **expected inflation**, not trailing inflation, and follows the logic used in recognized short real-rate measures.

---

# Raw source files

## 1. `Mean_CPI_Level.xlsx`

### Source

**Federal Reserve Bank of Philadelphia — Survey of Professional Forecasters (SPF)**

Direct download URL used:

```text
https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/data-files/files/Mean_CPI_Level.xlsx?sc_lang=en&hash=988348DA9D1AA5EE5B778F6B760F7A1C
```

Related SPF CPI page:

```text
https://www.philadelphiafed.org/surveys-and-data/cpi-spf
```

SPF documentation:

```text
https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-documentation.pdf
```

### Download details

- **Downloaded:** 11 October 2026
- **Downloaded by:** Thiago Siqueira
- **Source institution:** Federal Reserve Bank of Philadelphia
- **Stored as:**

```text
datos_y_modelos/db/brazil_macroeconomic_data/real_fed_3m/Mean_CPI_Level.xlsx
```

### Variable selected

The intended inflation-expectations input is:

```text
CPI3
```

For an SPF survey conducted in quarter `t`, `CPI3` is the mean forecast of **headline CPI inflation for the next quarter (`t+1`)**.

The series is expressed as an **annualized quarter-over-quarter inflation rate in percentage points**, so it can be compared directly with the nominal annualized 3-month OIS rate.

---

## 2. `spf-release-dates.txt`

### Source

**Federal Reserve Bank of Philadelphia — Deadline and Release Dates for the Survey of Professional Forecasters**

Direct download URL used:

```text
https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-release-dates.txt?hash=CE16E2057464DBD7A139FFE6188B48EC&sc_lang=en
```

### Download details

- **Downloaded:** 11 October 2026
- **Downloaded by:** Thiago Siqueira
- **Source institution:** Federal Reserve Bank of Philadelphia
- **Stored as:**

```text
datos_y_modelos/db/brazil_macroeconomic_data/real_fed_3m/spf-release-dates.txt
```

### Why this file is required

The monthly thesis panel must use only information that was **publicly available as of each month-end**.

The SPF is normally released once per quarter, but the actual publication date is not always the same calendar pattern. Therefore, a generic rule such as:

```text
Q1 -> February
Q2 -> May
Q3 -> August
Q4 -> November
```

is not sufficiently rigorous for a point-in-time panel.

The official `spf-release-dates.txt` file provides the actual historical **news release date** for each survey and is therefore the authoritative timing source for the monthly mapping.

---

# Point-in-time timing rule

For every monthly panel observation at month-end `t`:

1. identify all SPF surveys whose **official news release date** is on or before that month-end;
2. select the most recently released survey;
3. use that survey's `CPI3` value;
4. carry that value forward only until a newer SPF survey has actually been released.

In pseudocode:

```text
spf_cpi_next_quarter(month_end_t)
    = CPI3 from latest SPF survey
      with release_date <= month_end_t
```

This rule prevents look-ahead bias.

---

## Important timing exception

The official Philadelphia Fed release-date file documents that **2019 Q1 was delayed by the federal government shutdown**:

```text
2019 Q1
True deadline date: 12-Mar-2019
News release date:  22-Mar-2019
```

Therefore:

```text
2019-02 month-end -> still uses 2018 Q4 CPI3
2019-03 month-end -> uses 2019 Q1 CPI3
```

A simple "Q1 becomes available in February" rule would be wrong for this observation.

The official file also documents other shutdown-related delays, including 2013 Q4, 1996 Q1, and 2026 Q1. These are outside or mostly outside the current regression window, but reinforce why actual release dates must be used rather than assumed quarter-month conventions.

---

# Intended real-rate construction

## Nominal leg

```text
USSOC Curncy
```

Economic interpretation used in the thesis workflow:

```text
3-month USD Overnight Indexed Swap (OIS) fixed rate
```

Units:

```text
annualized percentage points
```

Monthly convention already used in the thesis:

```text
calendar month-end, latest available quote / PREV fill
```

---

## Expected-inflation leg

```text
Philadelphia Fed SPF CPI3
```

Economic interpretation:

```text
mean forecast of next-quarter headline CPI inflation
```

Units:

```text
annualized percentage points
```

Monthly timing:

```text
latest officially released SPF survey as of each month-end
```

---

## Primary candidate formula

The intended robustness variable is:

```text
real_fed_3m_spf = nominal_3m_ois - spf_cpi_next_quarter
```

or mathematically:

```text
r_t ≈ i_t - E_t(pi_{t+1q})
```

where:

- `i_t` = nominal 3-month USD OIS rate;
- `E_t(pi_{t+1q})` = SPF next-quarter CPI inflation expectation available at month-end `t`.

Both terms are in annualized percentage-point units.

---

## Optional exact Fisher transformation

If desired as an additional sensitivity:

```text
real_fed_3m_spf_exact =
    ((1 + nominal_3m_ois/100) /
     (1 + spf_cpi_next_quarter/100)
     - 1) * 100
```

The subtraction form remains the primary candidate because it follows the standard short-rate approximation and is directly comparable with recognized real-rate constructions.

---

# Why the Philadelphia Fed SPF was selected

A market-based Bloomberg CPI-fixing approach using:

```text
USSWIF1 BFIL Curncy
...
USSWIF12 BFIL Curncy
```

was investigated first.

That route was not selected as the immediate implementation because:

1. usable fixing history appears to start only in January 2017;
2. ticker rollover and reference-month conventions require additional validation;
3. point-in-time handling of CPI fixing quotes is more complex;
4. the Philadelphia Fed SPF is official, transparent, reproducible, and widely recognized;
5. SPF data allow coverage of the thesis's core 2016m1–2025m6 estimation window.

The Bloomberg fixing approach remains a possible additional market-based robustness exercise, but it is not required for the current director-requested check.

---

# Outcome / decision as of 11 October 2026

**Decision:** use Philadelphia Fed SPF `CPI3` as the preferred expected-inflation input for constructing the real U.S. 3-month rate robustness variable.

The intended robustness measure is therefore:

```text
USSOC 3M OIS
minus
latest-released SPF next-quarter CPI expectation
```

The monthly SPF mapping will be based on **actual official news release dates**, not an assumed February/May/August/November rule.

This preserves the existing nominal U.S. 3-month market instrument while replacing the rejected backward-looking CPI YoY adjustment with a forward-looking expected-inflation measure.

---

# Current status

As of 11 October 2026:

```text
[DONE] Raw SPF CPI workbook archived
[DONE] Official SPF release-date file archived
[DONE] Source provenance documented
[DONE] Expected-inflation variable selected: CPI3
[DONE] Point-in-time rule selected: latest official release as of month-end
[TODO] Build deterministic quarterly-to-monthly transformation
[TODO] Validate 2016m1–2025m6 coverage and timing
[TODO] Construct real_fed_3m_spf
[TODO] Run FE-DK robustness regression(s)
[TODO] Decide final thesis/table presentation
```

---

# Reproducibility workflow

Use:

```text
Mean_CPI_Level.xlsx
        +
spf-release-dates.txt
        |
        v
parse SPF quarter + official release date
        |
        v
select CPI3
        |
        v
map latest released forecast to each panel month-end
        |
        v
spf_cpi_next_quarter
        |
        + USSOC 3M OIS
        |
        v
real_fed_3m_spf
        |
        v
robustness regression
```

No manual editing of the raw official files should be performed.

---

# Data-freeze rule

The frozen WP-06 panel:

```text
datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt.xlsx
```

must **not** be overwritten.

The real-Fed variable should be produced as a separate reproducible robustness input and merged in memory, or through a separate robustness-stage dataset/script.

---

# Related thesis files

Frozen econometric panel:

```text
datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt.xlsx
```

Current WP-08 no-issue-size sensitivity script:

```text
src/econometrics/wp08_no_issue_size_sensitivity.do
```

Final five-model FE-DK table:

```text
datos_y_modelos/db/econometrics_db/Tabla_nuevas_estimaciones_FE_DK_final.docx
```

Raw real-Fed input folder:

```text
datos_y_modelos/db/brazil_macroeconomic_data/real_fed_3m/
```

---

# Methodological caveat

The SPF expectation is quarterly, whereas the nominal OIS is observed monthly and covers approximately three months from each observation date.

Therefore, this is best described as an:

```text
SPF-based expected real U.S. 3-month rate
```

rather than a directly observed market real policy rate.

The quarterly survey horizon is not a perfect day-for-day match to every monthly 3-month OIS interval. The robustness remains economically defensible because both components are short-horizon, forward-looking annualized rates, and the use of actual SPF release dates ensures point-in-time integrity.

---

# Raw-file preservation

These files are canonical raw inputs and should remain unchanged:

```text
Mean_CPI_Level.xlsx
spf-release-dates.txt
```

Any cleaned, parsed, monthly, or derived series should be written to a **new file** and generated by a deterministic script.
