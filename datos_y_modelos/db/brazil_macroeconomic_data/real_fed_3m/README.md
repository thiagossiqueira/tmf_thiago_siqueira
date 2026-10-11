# Real Fed 3M Robustness Input — Philadelphia Fed SPF CPI Expectations

## Purpose

This folder contains the raw inflation-expectations input selected for the **real Fed 3M robustness check** in the thesis:

> *Determinantes de los diferenciales de bonos corporativos en moneda local en Brasil: panel 2010–2025*

The objective is to construct a real version of the existing U.S. 3-month nominal rate by netting out an **expected inflation rate**, rather than using trailing realized CPI inflation.

---

## Why this file was downloaded

The thesis baseline uses a nominal U.S. 3-month OIS rate (`USSOC Curncy`, Bloomberg; inherited panel variable name `fed_3m_forward`).

On 10–11 October 2026, thesis director **Martín Grandes** asked to check whether the Fed 3M rate could also be expressed in real terms by discounting/subtracting inflation.

The prior legacy construction:

```text
fed_3m_real = fed_3m_forward - us_cpi_yoy
```

was rejected for this robustness exercise because it combines:

- a forward-looking / short-horizon nominal 3-month rate; with
- backward-looking 12-month realized CPI inflation.

The revised approach uses **expected inflation over a short horizon**.

---

## Requested by

**Martín Grandes**  
Thesis director.

Director instruction, paraphrased from the October 2026 discussion:

> Check whether the Fed 3M / flat-forward rate can also be shown in real terms by netting out inflation.

Implementation detail — using a horizon-appropriate expected-inflation measure rather than trailing CPI YoY — is the thesis author's methodological choice, not a separate requirement imposed by the director.

---

## Source

**Federal Reserve Bank of Philadelphia — Survey of Professional Forecasters (SPF)**

Raw file:

```text
Mean_CPI_Level.xlsx
```

Direct download URL used:

```text
https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/data-files/files/Mean_CPI_Level.xlsx?sc_lang=en&hash=988348DA9D1AA5EE5B778F6B760F7A1C
```

SPF CPI page:

```text
https://www.philadelphiafed.org/surveys-and-data/cpi-spf
```

SPF documentation:

```text
https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/spf-documentation.pdf
```

---

## Download details

- **Downloaded:** 11 October 2026
- **Downloaded by:** Thiago Siqueira
- **Source institution:** Federal Reserve Bank of Philadelphia
- **Destination folder:**

```text
datos_y_modelos/db/brazil_macroeconomic_data/real_fed_3m/
```

- **Raw file preserved as:**

```text
datos_y_modelos/db/brazil_macroeconomic_data/real_fed_3m/Mean_CPI_Level.xlsx
```

The raw source file should remain unchanged. Any transformation should be produced separately and reproducibly.

---

## Variable selected

The intended SPF input is:

```text
CPI3
```

For a survey conducted in quarter `t`, `CPI3` represents the SPF mean forecast of **headline CPI inflation for the next quarter (`t+1`)**, expressed at an annualized quarterly rate.

This is the preferred SPF input because it is conceptually aligned with the Philadelphia Fed's short real-rate methodology using a 3-month nominal rate minus next-quarter expected CPI inflation.

---

## Intended real-rate construction

Nominal leg:

```text
USSOC Curncy
```

Bloomberg description used in the thesis workflow:

```text
3-month USD Overnight Indexed Swap (OIS) fixed rate
```

Inflation-expectations leg:

```text
Philadelphia Fed SPF CPI3
```

Approximate real-rate construction:

```text
real_fed_3m = nominal_3m_ois - expected_next_quarter_cpi
```

Both components are expressed in annualized percentage-point terms.

An exact Fisher transformation may also be retained as a sensitivity if needed:

```text
real_fed_3m_exact = ((1 + nominal_3m_ois/100) / (1 + expected_cpi/100) - 1) * 100
```

The approximation above is the primary candidate because it follows the standard short-rate convention and is directly comparable with the Philadelphia Fed's published real-rate methodology.

---

## Point-in-time / monthly timing rule

The monthly panel must use only information that was publicly available by each month-end.

The SPF is released quarterly, normally in:

- February
- May
- August
- November

The intended monthly carry-forward convention is therefore:

| Panel month | SPF observation used |
|---|---|
| January | previous year's Q4 `CPI3` |
| February–April | Q1 `CPI3` |
| May–July | Q2 `CPI3` |
| August–October | Q3 `CPI3` |
| November–December | Q4 `CPI3` |

Example:

```text
2016-01 -> 2015Q4 CPI3
2016-02 -> 2016Q1 CPI3
2016-03 -> 2016Q1 CPI3
2016-04 -> 2016Q1 CPI3
2016-05 -> 2016Q2 CPI3
```

This rule is designed to avoid look-ahead bias.

Before final implementation, release-date timing should be validated programmatically for the full estimation window.

---

## Why SPF was chosen

A market-based Bloomberg CPI-fixing approach (`USSWIF1`–`USSWIF12 BFIL Curncy`) was also investigated.

That route was not selected as the immediate implementation because:

1. usable Bloomberg fixing history appears to begin only in January 2017;
2. the fixing tickers require additional validation of rollover and reference-month conventions;
3. the Philadelphia Fed SPF provides a transparent, official, academically recognized expected-inflation measure;
4. SPF coverage supports the thesis estimation period beginning in 2016.

The Bloomberg fixing approach remains a possible additional market-based robustness check, but it is not required for the current implementation.

---

## Outcome / decision as of 11 October 2026

**Decision:** proceed with the Philadelphia Fed SPF `CPI3` series as the preferred expected-inflation input for constructing a real 3-month U.S. rate robustness variable.

The planned robustness variable is therefore:

```text
USSOC 3M OIS - SPF next-quarter CPI expectation
```

This preserves the thesis's existing nominal 3-month OIS instrument while replacing the rejected backward-looking CPI YoY adjustment with a forward-looking expected-inflation measure.

**Status:** source selected and raw workbook archived.  
**Not yet done:** deterministic monthly transformation, merge into a robustness dataset, and FE-DK re-estimation.

The frozen WP-06 panel must **not** be overwritten. Any real-Fed variable should be created as a reproducible robustness input or merged in memory during estimation.

---

## Reproducibility rule

Use the following workflow:

```text
raw official source
    -> deterministic quarterly-to-monthly timing transformation
    -> validation of coverage and release timing
    -> derived real Fed 3M robustness series
    -> in-memory merge / robustness estimation
```

Do not manually edit the raw SPF workbook.

---

## Related thesis files

Current econometric panel:

```text
datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt.xlsx
```

Current WP-08 sensitivity script:

```text
src/econometrics/wp08_no_issue_size_sensitivity.do
```

The real-Fed robustness should be implemented separately so that the frozen WP-06 panel remains unchanged.

---

## Notes

- The inherited panel variable name `fed_3m_forward` is economically imprecise: the underlying Bloomberg instrument is a spot 3-month USD OIS rate, not a forward-starting 3m×6m contract.
- The real-rate robustness should be described as an **SPF-based expected real 3-month U.S. rate**, not as an observed real policy rate.
- The SPF quarterly expectation is a reputable short-horizon proxy, but it is not a perfect calendar-day match to every 3-month OIS observation. This limitation should be disclosed if the variable enters the final thesis robustness section.
