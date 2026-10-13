*===============================================================================
* FINAL SPECIFICATION - ECONOMETRIC DIAGNOSTICS
*
* Purpose:
*   Re-run model-selection and error-structure diagnostics on the LOCKED final
*   common estimation sample implied by Martin Grandes' final specification.
*
* Final common sample expected:
*   4,648 observations
*   103 bonds
*   48 issuers
*   2010m12 - 2025m6
*
* Diagnostics:
*   1. Pooled vs FE: Stata built-in F test after xtreg, fe
*   2. FE vs RE: classical Hausman test
*   3. Groupwise heteroskedasticity: Modified Wald (xttest3)
*   4. Cross-sectional dependence: Pesaran CD (xtcd2; unbalanced-panel compatible)
*   5. Serial correlation: Wooldridge test (xtserial)
*
* Panel unit-root tests (LLC / IPS / CIPS) are intentionally NOT run.
* The thesis documents that the strongly unbalanced and discontinuous panel
* does not support their consistent application to the full bond panel.
*
* IMPORTANT:
*   - Frozen WP-06 panel is never overwritten.
*   - Issue amount / total assets is excluded from the final specification.
*   - Diagnostics are run on the exact final common sample only.
*===============================================================================
clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture log close
log using ///
    "`root'\src\econometrics\wp07_reestimation\Final_spec_diagnostics.log", ///
    replace text

*===============================================================================
* 1. LOAD FROZEN WP-06 PANEL
*===============================================================================

import excel using ///
    "`root'\datos_y_modelos\db\econometrics_db\panel_main_and_robustness_rebuilt.xlsx", ///
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
* 8. FINAL SEVEN-COLUMN FE-DK X-MATRIX
*
* M1  Global factors
* M2  Global + local macro
* M3  Global + local macro + sovereign risk
* M4  Global + sovereign risk
* M5  Full: global + local + sovereign + firm/bond
* M6  Global + local monetary 3M rate
* M7  Brazil 3M robustness with Real Fed 3M omitted
*
* Source-accurate implementation:
*   Real Fed      -> real_fed_3m_spf
*   USD/BRL RER   -> real_exchange_rate
*   Brazil 3M     -> real_brazil_3m_focus
*
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
    sovereign_spread_brl

local model5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

local model6_x ///
    vix ///
    real_fed_3m_spf ///
    real_brazil_3m_focus

local model7_x ///
    vix ///
    real_brazil_3m_focus

*===============================================================================
* 9. NATURAL COMPLETE-CASE SAMPLE BY MODEL
*===============================================================================

forvalues m = 1/7 {
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

*===============================================================================
* 10. COMMON FINAL TABLE SAMPLE
*
* M5 contains the union of all variables appearing anywhere in M1-M7.
* Therefore its complete-case sample is the strict common sample required
* to hold observations fixed across all seven final columns.
*===============================================================================

gen byte sample_common = sample_m5

di as text "============================================================"
di as text "STRICT COMMON FINAL-TABLE SAMPLE"

count if sample_common
local ncommon = r(N)
di as result "COMMON SAMPLE OBSERVATIONS: `ncommon'"

quietly summarize month_id if sample_common, meanonly
di as result "Common sample first month: " %tm r(min)
di as result "Common sample last month:  " %tm r(max)

levelsof bond_id if sample_common, local(common_bonds)
local ncommon_bonds : word count `common_bonds'
di as result "Common sample bonds: `ncommon_bonds'"

levelsof issuer if sample_common, local(common_issuers)
local ncommon_issuers : word count `common_issuers'
di as result "Common sample issuers: `ncommon_issuers'"

* Verify common sample is admissible in every model.
forvalues m = 1/7 {
    count if sample_common & !sample_m`m'
    if r(N)>0 {
        di as error ///
            "ERROR: common M5 sample is not nested inside Model `m' sample."
        exit 459
    }
}

*===============================================================================
* 11. LOCK AND VERIFY FINAL DIAGNOSTIC SAMPLE
*===============================================================================

di as text "============================================================"
di as text "FINAL DIAGNOSTIC SAMPLE VALIDATION"

count if sample_common
di as result "Observations: " r(N)
if r(N) != 4648 {
    di as error "Expected 4,648 final-sample observations."
    exit 459
}

levelsof bond_id if sample_common, local(diag_bonds)
local nbonds : word count `diag_bonds'
di as result "Bonds: `nbonds'"
if `nbonds' != 103 {
    di as error "Expected 103 final-sample bonds."
    exit 459
}

levelsof issuer if sample_common, local(diag_issuers)
local nissuers : word count `diag_issuers'
di as result "Issuers: `nissuers'"
if `nissuers' != 48 {
    di as error "Expected 48 final-sample issuers."
    exit 459
}

quietly summarize month_id if sample_common, meanonly
di as result "First month: " %tm r(min)
di as result "Last month:  " %tm r(max)

if r(min) != tm(2010m12) | r(max) != tm(2025m6) {
    di as error "Unexpected final-sample time window."
    exit 459
}

* Numeric bond identifier for panel estimators.
encode bond_id, gen(bond_id_num)

* Diagnostics use the actual monthly calendar variable.
xtset bond_id_num month_id

* Required user-written diagnostic commands must already be installed.
capture which xttest3
if _rc {
    di as error "xttest3 is not installed."
    exit 499
}

capture which xtcd2
if _rc {
    di as error "xtcd2 is not installed."
    exit 499
}

capture which xtserial
if _rc {
    di as error "xtserial is not installed."
    exit 499
}

*===============================================================================
* 12. POOLED VS FIXED EFFECTS
*
* xtreg, fe reports:
*     F test that all u_i=0
* This is the pooled-vs-FE individual-effects test used in the thesis.
*===============================================================================

di as text "============================================================"
di as text "1. POOLED VS FE - BUILT-IN F TEST"

xtreg spread `model5_x' if sample_common, fe
estimates store FE_diag

di as text ///
    "Use Stata's reported 'F test that all u_i=0' as pooled-vs-FE diagnostic."

*===============================================================================
* 13. FIXED EFFECTS VS RANDOM EFFECTS - CLASSICAL HAUSMAN
*===============================================================================

di as text "============================================================"
di as text "2. HAUSMAN - FE VS RE"

xtreg spread `model5_x' if sample_common, fe
estimates store FE_plain_final

xtreg spread `model5_x' if sample_common, re
estimates store RE_plain_final

capture noisily hausman FE_plain_final RE_plain_final, sigmamore
local hausman_rc = _rc
di as result "Hausman return code: `hausman_rc'"

*===============================================================================
* 14. GROUPWISE HETEROSKEDASTICITY - MODIFIED WALD
*===============================================================================

di as text "============================================================"
di as text "3. MODIFIED WALD TEST FOR GROUPWISE HETEROSKEDASTICITY"

xtreg spread `model5_x' if sample_common, fe

capture noisily xttest3
local xttest3_rc = _rc
di as result "xttest3 return code: `xttest3_rc'"

*===============================================================================
* 15. CROSS-SECTIONAL DEPENDENCE - PESARAN CD
*===============================================================================

di as text "============================================================"
di as text "4. PESARAN CROSS-SECTIONAL DEPENDENCE TEST"

xtreg spread `model5_x' if sample_common, fe

capture noisily xtcd2, pesaran
local xtcd2_rc = _rc
di as result "xtcd2 return code: `xtcd2_rc'"

*===============================================================================
* 16. SERIAL CORRELATION - WOOLDRIDGE TEST
*===============================================================================

di as text "============================================================"
di as text "5. WOOLDRIDGE TEST FOR SERIAL CORRELATION"

capture noisily xtserial spread `model5_x' if sample_common
local xtserial_rc = _rc
di as result "xtserial return code: `xtserial_rc'"

*===============================================================================
* 17. COMPLETION
*===============================================================================

di as text "============================================================"
di as result "FINAL DIAGNOSTICS COMPLETED"
di as result "Sample: 4,648 observations / 103 bonds / 48 issuers"
di as result "Window: 2010m12-2025m6"
di as text "============================================================"

log close
exit

