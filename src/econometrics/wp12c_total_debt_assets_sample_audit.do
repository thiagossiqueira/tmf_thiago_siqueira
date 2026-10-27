*===============================================================================
* WP-12C SAMPLE AUDIT - DIRECTOR-SPECIFIED TOTAL DEBT / TOTAL ASSETS
*
* Frozen source panel:
*   4,648 observations / 103 bonds / 48 issuers
*   2010m12 - 2025m6
*
* Strict final common sample:
*   Frozen-panel target: 4,648 observations / 103 bonds / 48 issuers
*   Frozen-panel window: 2010m12 - 2025m6
*
* Estimator:
*   Bond fixed effects
*   Driscoll-Kraay standard errors
*   Maximum lag = 4
*
* This audit reports natural complete-case support before any common-sample lock.
*===============================================================================
clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture mkdir "`root'\src\econometrics\wp12c_reestimation"
capture log close
log using ///
    "`root'\src\econometrics\wp12c_reestimation\WP12C_Total_Debt_Assets_Sample_Audit.log", ///
    replace text

*===============================================================================
* 1. LOAD FROZEN WP-06 PANEL
*===============================================================================

import excel using ///
    "`root'\datos_y_modelos\db\econometrics_db\panel_main_and_robustness_rebuilt_v4.xlsx", ///
    sheet("ts") firstrow clear

gen double month_id = mofd(dofc(month))
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "month_id could not be constructed for all frozen-panel rows."
    exit 198
}

tempfile frozen_panel
save `frozen_panel'

*===============================================================================
* 2. LOAD CPI LEVEL INPUTS FOR BILATERAL RER
*===============================================================================

import delimited using ///
    "`root'\datos_y_modelos\db\real_exchange_rate_inputs\rer_cpi_monthly_inputs.csv", ///
    varnames(1) clear

gen double cpi_date = date(month, "YMD")
gen double month_id = mofd(cpi_date)
format month_id %tm

isid month_id

keep month_id cpi_us_index cpi_br_index us_series_id br_series_id

tempfile rer_inputs
save `rer_inputs'

*===============================================================================
* 3. LOAD VALIDATED REAL FED 3M INPUT
*===============================================================================

import delimited using ///
    "`root'\datos_y_modelos\db\brazil_macroeconomic_data\real_fed_3m\real_fed_3m_spf_monthly.csv", ///
    varnames(1) clear

gen double real_fed_date = date(month_end, "YMD")
gen double month_id = mofd(real_fed_date)
format month_id %tm

isid month_id

keep month_id ///
    ussoc_px_last ///
    spf_cpi_next_quarter ///
    real_fed_3m_spf ///
    real_fed_3m_spf_exact

tempfile real_fed_inputs
save `real_fed_inputs'

*===============================================================================
* 4. LOAD VALIDATED REAL BRAZIL 3M INPUT
*===============================================================================

import delimited using ///
    "`root'\datos_y_modelos\db\brazil_macroeconomic_data\real_brazil_3m\real_brazil_3m_focus_panel_dates.csv", ///
    varnames(1) clear

gen double real_brazil_date = date(obs_date, "YMD")
gen double month_id = mofd(real_brazil_date)
format month_id %tm

isid month_id

count if missing(real_brazil_3m_focus)
if r(N)>0 {
    di as error "Missing primary Real Brazil 3M values."
    exit 459
}

count if abs(nominal_di_canonical_diff_bp) > 1e-9 ///
    & !missing(nominal_di_canonical_diff_bp)
if r(N)>0 {
    di as error "Real Brazil input fails canonical DI reconciliation."
    exit 459
}

keep month_id ///
    nominal_brazil_3m_di_pct ///
    expected_ipca_ann_pct ///
    real_brazil_3m_focus ///
    real_brazil_3m_focus_exact ///
    nominal_di_canonical_diff_bp

tempfile real_brazil_inputs
save `real_brazil_inputs'
*===============================================================================
* 5A. LOAD FROZEN BOOK DEBT / MARKET CAP CANDIDATE
*===============================================================================

import delimited using ///
    "`root'\output\Informes jurado\WP12C_total_debt_to_total_assets_4648.csv", ///
    varnames(1) clear

gen double leverage_date = date(obs_date, "YMD")
gen double month_id = mofd(leverage_date)
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "Could not construct leverage month_id."
    exit 459
}

isid bond_id month_id

keep bond_id month_id total_debt_to_total_assets

count if !missing(total_debt_to_total_assets)
if r(N) != 4648 {
    di as error "Expected 4,648 nonmissing Total Debt / Total Assets observations."
    exit 459
}

tempfile leverage_inputs
save `leverage_inputs'
*===============================================================================
* 5. RESTORE FROZEN PANEL AND MERGE RER INPUTS
*===============================================================================

use `frozen_panel', clear

merge m:1 month_id using `rer_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "CPI/RER merge did not match all frozen-panel observations."
    tab _merge
    exit 459
}
drop _merge

count if missing(cpi_us_index, cpi_br_index)
if r(N)>0 {
    di as error "Missing CPI inputs after RER merge."
    exit 459
}

* Bilateral real USD/BRL:
* RER_t = USD/BRL_t * CPI_US_t / CPI_BR_t
* Increase = BRL real depreciation.

gen double rer_usd_brl = ///
    usd_brl * cpi_us_index / cpi_br_index

quietly summarize rer_usd_brl if month_id == tm(2010m12), meanonly
local base_rer = r(mean)

if missing(`base_rer') {
    di as error "December 2010 RER base value is missing."
    exit 459
}

gen double real_exchange_rate = ///
    100 * rer_usd_brl / `base_rer'

label variable real_exchange_rate ///
    "Real USD/BRL index; increase = BRL real depreciation"

*===============================================================================
* 6. MERGE REAL FED 3M
*===============================================================================

merge m:1 month_id using `real_fed_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Real-Fed input does not match all frozen-panel observations."
    tab _merge
    exit 459
}

* Validated Real-Fed SPF coverage now spans the full frozen-panel window,
* 2010m12-2025m6, with no missing month-end observations.

gen double fed_nominal_diff = ///
    abs(fed_3m_forward - ussoc_px_last) if _merge == 3

quietly summarize fed_nominal_diff, meanonly
di as result ///
    "MAX |frozen-panel Fed - Real-Fed nominal input|: " %12.10f r(max)

count if fed_nominal_diff > 1e-6 & !missing(fed_nominal_diff)
if r(N)>0 {
    di as error ///
        "Real-Fed nominal leg does not reproduce frozen-panel fed_3m_forward."
    exit 459
}

drop _merge fed_nominal_diff

label variable real_fed_3m_spf ///
    "Real US 3M OIS: USSOC minus SPF expected next-quarter CPI"

*===============================================================================
* 7. MERGE REAL BRAZIL 3M
*===============================================================================

merge m:1 month_id using `real_brazil_inputs'

count if _merge != 3
if r(N)>0 {
    di as error ///
        "Real Brazil 3M input did not match all frozen-panel months."
    tab _merge
    exit 459
}
drop _merge

quietly summarize nominal_di_canonical_diff_bp, meanonly
di as result ///
    "MAX |Brazil nominal DI - canonical DI| (bp): " %12.10f r(max)

label variable real_brazil_3m_focus ///
    "Real Brazil 3M DI: nominal DI minus Focus expected IPCA"

*===============================================================================
* 7A. MERGE FROZEN BOOK DEBT / MARKET CAP CANDIDATE
*===============================================================================

merge 1:1 bond_id month_id using `leverage_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Frozen leverage candidate did not match all panel bond-month keys."
    tab _merge
    exit 459
}
drop _merge

count if !missing(total_debt_to_total_assets)
if r(N) != 4648 {
    di as error "Expected 4,648 nonmissing leverage observations after merge."
    exit 459
}

label variable total_debt_to_total_assets ///
    "Total debt / total assets (%)"

* 8. FINAL EIGHT-COLUMN FE-DK X-MATRIX
*
* M1  Global
* M2  Global + local macro
* M3  Global + local macro + sovereign risk
* M4  Full: M3 + new leverage + maturity
* M5  Full 2: M4 without sovereign risk
* M6  Full 3: M5 without Real Brazil 3M
* M7  Parsimonious: VIX + Real Fed 3M + sovereign risk
* M8  M4 + OCF/assets
*
* Frozen specification decisions inherited from WP-08:
*   Corporate spread -> geometric spread
*   Bond FE + Driscoll-Kraay lag(4)
*   Real Fed         -> real_fed_3m_spf
*   USD/BRL RER      -> real_exchange_rate
*   Brazil 3M        -> real_brazil_3m_focus
*   Fiscal           -> EHBBBR stored in debt_gdp
*   Sovereign risk   -> sovereign_spread_brl
*   Leverage         -> total_debt_to_total_assets
*   Bond liquidity   -> excluded from preferred main table
*
* OCF/assets is excluded from M1-M7 and returns only in M8.
* tot_debt_to_ebitda is excluded from the final WP-12A micro block.
* No nominal USD/BRL.
* No nominal Fed 3M.
* No amount_issued_to_bs_tot_asset.
*===============================================================================

local model1_x ///
    vix ///
    real_fed_3m_spf

local model2_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp

local model3_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl

local model4_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    total_debt_to_total_assets ///
    days_to_maturity

local model5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    total_debt_to_total_assets ///
    days_to_maturity

local model6_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    total_debt_to_total_assets ///
    days_to_maturity

local model7_x ///
    vix ///
    real_fed_3m_spf ///
    sovereign_spread_brl

local model8_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    total_debt_to_total_assets ///
    cf_cash_oper_to_tot_asset ///
    days_to_maturity

*===============================================================================
* 9. NATURAL COMPLETE-CASE SAMPLE BY MODEL
*===============================================================================

forvalues m = 1/8 {
    gen byte sample_m`m' = 1
    markout sample_m`m' spread `model`m'_x'

    di as text "============================================================"
    di as text "MODEL `m' NATURAL COMPLETE-CASE SAMPLE"

    count if sample_m`m'
    local nobs = r(N)
    di as result "Observations: `nobs'"

    quietly summarize month_id if sample_m`m', meanonly
    di as result "First month: " %tm r(min)
    di as result "Last month:  " %tm r(max)

    levelsof bond_id if sample_m`m', local(bonds)
    local nbonds : word count `bonds'
    di as result "Number of bonds: `nbonds'"

    levelsof issuer if sample_m`m', local(issuers)
    local nissuers : word count `issuers'
    di as result "Number of issuers: `nissuers'"

}

* Compare M4 and M8 membership without imposing equality.
count if sample_m4 != sample_m8
local m4_m8_sample_diff = r(N)
di as result "M4 vs M8 sample-membership differences: `m4_m8_sample_diff'"

*===============================================================================
* 10. WP-12C TOTAL DEBT / TOTAL ASSETS SAMPLE BRIDGE
*===============================================================================

count
local bridge_panel = r(N)

count if !missing(total_debt_to_total_assets)
local bridge_leverage = r(N)

count if sample_m8
local bridge_full = r(N)

di as text "============================================================"
di as text "WP-12C SAMPLE BRIDGE"
di as result "Frozen v4 panel:                           `bridge_panel'"
di as result "Total Debt / Total Assets available:       `bridge_leverage'"
di as result "M8 natural complete-case support:          `bridge_full'"
di as result "WP-12A Book Debt / Market Cap comparator:  3303"
di as result "WP-08 B3CT comparator:                     1177"

if `bridge_panel' != 4648 {
    di as error "Frozen v4 panel no longer contains 4,648 observations."
    exit 459
}

if `bridge_leverage' != 4648 {
    di as error "Total Debt / Total Assets should cover all 4,648 observations."
    exit 459
}

di as text "============================================================"
di as result "WP-12C SAMPLE AUDIT COMPLETED"
di as text "No common-sample choice has been imposed."
di as text "No regression has been run."
di as text "============================================================"

log close
exit 0
