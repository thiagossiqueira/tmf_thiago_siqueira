*===============================================================================
* FINAL SPECIFICATION - SEVEN-MODEL FE DRISCOLL-KRAAY TABLE
*
* Final common sample:
*   4,648 observations
*   103 bonds
*   48 issuers
*   2010m12 - 2025m6
*
* Estimator:
*   Bond fixed effects
*   Driscoll-Kraay standard errors
*   Maximum lag = 4
*
* All seven models use the same locked common sample.
*===============================================================================
clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture log close
log using ///
    "`root'\src\econometrics\wp07_reestimation\wp07_dk_bandwidth_sensitivity.log", ///
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

* M4: Full model.
local model4_x ///
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

* M5: Full 2 - full model without sovereign risk.
local model5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* M6: Full 3 - no sovereign risk and no Real Brazil 3M rate.
local model6_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* M7: Parsimonious global + sovereign-risk model.
local model7_x ///
    vix ///
    real_fed_3m_spf ///
    sovereign_spread_brl

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
* M4 is the Full model and contains the union of all variables
* appearing anywhere in M1-M7. Therefore its complete-case sample is
* the strict common sample required to hold observations fixed across
* all seven final columns.
*===============================================================================

gen byte sample_common = sample_m4

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
            "ERROR: common M4 Full-model sample is not nested inside Model `m' sample."
        exit 459
    }
}

*===============================================================================
* 11. VERIFY LOCKED FINAL SAMPLE
*===============================================================================

count if sample_common
if r(N) != 4648 {
    di as error "Expected 4,648 final-sample observations."
    exit 459
}

levelsof bond_id if sample_common, local(final_bonds)
local n_final_bonds : word count `final_bonds'
if `n_final_bonds' != 103 {
    di as error "Expected 103 bonds in final sample."
    exit 459
}

*===============================================================================
* 12. PANEL SETUP FOR DRISCOLL-KRAAY
*===============================================================================

encode bond_id, gen(bond_id_num)
egen t_dk = group(month_id)
xtset bond_id_num t_dk

capture which xtscc
if _rc {
    di as error "xtscc is not installed."
    exit 499
}

capture which esttab
if _rc {
    di as error "esttab/estout is not installed."
    exit 499
}

*===============================================================================
* 13. ESTIMATE FINAL SEVEN MODELS: DK LAG(4) VS DK LAG(2)
*
* WP-07 rule:
*   Same dependent variable, regressors, sample and bond fixed effects.
*   The only econometric change is DK maximum lag: 4 -> 2.
*
* Baseline estimates retain canonical names M1_DK ... M7_DK.
* Sensitivity estimates are stored as M1_DK2 ... M7_DK2.
*===============================================================================

forvalues m = 1/7 {

    di as text "============================================================"
    di as text "WP-07 FE-DK MODEL `m': BASELINE LAG(4)"
    di as text "============================================================"

    * Baseline: frozen DK lag(4).
    xtscc spread `model`m'_x' if sample_common, fe lag(4)
    estimates store M`m'_DK

    local m`m'_N   = e(N)
    local m`m'_Ng  = e(N_g)
    local m`m'_r2w = e(r2_w)

    if `m`m'_N' != 4648 {
        di as error "Lag(4) Model `m' does not use 4,648 observations."
        exit 459
    }

    if `m`m'_Ng' != 103 {
        di as error "Lag(4) Model `m' does not use 103 bonds."
        exit 459
    }

    gen byte __wp07_es4_m`m' = e(sample)

    count if __wp07_es4_m`m' != sample_common
    if r(N) != 0 {
        di as error "Lag(4) e(sample) differs from locked sample_common in Model `m'."
        exit 459
    }

    di as text "------------------------------------------------------------"
    di as text "WP-07 FE-DK MODEL `m': SENSITIVITY LAG(2)"
    di as text "------------------------------------------------------------"

    * Sensitivity: ONLY the DK bandwidth changes from 4 to 2.
    xtscc spread `model`m'_x' if sample_common, fe lag(2)
    estimates store M`m'_DK2

    local m`m'_N2   = e(N)
    local m`m'_Ng2  = e(N_g)
    local m`m'_r2w2 = e(r2_w)

    if `m`m'_N2' != 4648 {
        di as error "Lag(2) Model `m' does not use 4,648 observations."
        exit 459
    }

    if `m`m'_Ng2' != 103 {
        di as error "Lag(2) Model `m' does not use 103 bonds."
        exit 459
    }

    gen byte __wp07_es2_m`m' = e(sample)

    count if __wp07_es2_m`m' != sample_common
    if r(N) != 0 {
        di as error "Lag(2) e(sample) differs from locked sample_common in Model `m'."
        exit 459
    }

    count if __wp07_es4_m`m' != __wp07_es2_m`m'
    local sample_diff_m`m' = r(N)

    di as result ///
        "MODEL `m' COMMON-SAMPLE CHECK: lag(4) vs lag(2) differing observations = " ///
        `sample_diff_m`m''

    if `sample_diff_m`m'' != 0 {
        di as error "Lag(4) and lag(2) estimation samples differ in Model `m'."
        exit 459
    }

    if `m`m'_N' != `m`m'_N2' {
        di as error "Lag(4) and lag(2) N differ in Model `m'."
        exit 459
    }

    if `m`m'_Ng' != `m`m'_Ng2' {
        di as error "Lag(4) and lag(2) bond counts differ in Model `m'."
        exit 459
    }

    * Companion FE regression only to recover rho.
    * rho does not depend on the DK bandwidth.
    xtreg spread `model`m'_x' if sample_common, fe
    local m`m'_rho = e(rho)

    estadd scalar rho = `m`m'_rho' : M`m'_DK
    estadd scalar rho = `m`m'_rho' : M`m'_DK2
}
*===============================================================================
* 14. WP-07 DK BANDWIDTH SENSITIVITY AUDIT
*===============================================================================
*
* For identical data, regressors, FE and estimation sample, changing the
* Driscoll-Kraay maximum lag should affect the variance estimator only.
* Coefficients should therefore be identical; SE, t, p and stars may change.
*===============================================================================

tempname wp07_post
tempfile wp07_audit_dta

postfile `wp07_post' ///
    int model str40 variable ///
    double b_lag4 se_lag4 t_lag4 p_lag4 ///
           b_lag2 se_lag2 t_lag2 p_lag2 ///
           coef_diff se_pct_change ///
    byte sig_lag4 sig_lag2 ///
    using "`wp07_audit_dta'", replace

forvalues m = 1/7 {

    estimates restore M`m'_DK
    local xlist : colnames e(b)

    foreach v of local xlist {

        if "`v'" != "_cons" {

            *---------------------------------------------------------------
            * Frozen baseline: DK lag(4)
            *---------------------------------------------------------------
            estimates restore M`m'_DK

            scalar __b4  = _b[`v']
            scalar __se4 = _se[`v']
            scalar __t4  = __b4 / __se4

            quietly test `v'
            scalar __p4 = r(p)

            *---------------------------------------------------------------
            * Sensitivity: DK lag(2)
            *---------------------------------------------------------------
            estimates restore M`m'_DK2

            scalar __b2  = _b[`v']
            scalar __se2 = _se[`v']
            scalar __t2  = __b2 / __se2

            quietly test `v'
            scalar __p2 = r(p)

            *---------------------------------------------------------------
            * Direct comparison
            *---------------------------------------------------------------
            scalar __bdiff = __b2 - __b4
            scalar __sepct = 100 * (__se2 / __se4 - 1)

            scalar __sig4 = cond(__p4 < .01, 3, ///
                            cond(__p4 < .05, 2, ///
                            cond(__p4 < .10, 1, 0)))

            scalar __sig2 = cond(__p2 < .01, 3, ///
                            cond(__p2 < .05, 2, ///
                            cond(__p2 < .10, 1, 0)))

            post `wp07_post' ///
                (`m') ("`v'") ///
                (__b4) (__se4) (__t4) (__p4) ///
                (__b2) (__se2) (__t2) (__p2) ///
                (__bdiff) (__sepct) ///
                (__sig4) (__sig2)

            di as result ///
                "WP07_AUDIT|M`m'|`v'" ///
                "|b4=" %10.6f __b4 ///
                "|se4=" %10.6f __se4 ///
                "|t4=" %9.4f __t4 ///
                "|p4=" %9.6f __p4 ///
                "|b2=" %10.6f __b2 ///
                "|se2=" %10.6f __se2 ///
                "|t2=" %9.4f __t2 ///
                "|p2=" %9.6f __p2 ///
                "|SEpct=" %9.3f __sepct ///
                "|sig4=" %1.0f __sig4 ///
                "|sig2=" %1.0f __sig2

            * Coefficients must not change when only DK bandwidth changes.
            if abs(__bdiff) > 1e-10 {
                di as error ///
                    "ERROR: coefficient changed between lag(4) and lag(2): M`m' `v'"
                exit 459
            }
        }
    }
}

postclose `wp07_post'

preserve

use "`wp07_audit_dta'", clear

gen double coef_abs_diff = abs(coef_diff)
gen byte sign_changed = (b_lag4 * b_lag2 < 0)
gen byte stars_changed = (sig_lag4 != sig_lag2)

gen str3 stars_lag4 = ///
    cond(sig_lag4 == 3, "***", ///
    cond(sig_lag4 == 2, "**", ///
    cond(sig_lag4 == 1, "*", "")))

gen str3 stars_lag2 = ///
    cond(sig_lag2 == 3, "***", ///
    cond(sig_lag2 == 2, "**", ///
    cond(sig_lag2 == 1, "*", "")))

order model variable ///
    b_lag4 se_lag4 t_lag4 p_lag4 stars_lag4 ///
    b_lag2 se_lag2 t_lag2 p_lag2 stars_lag2 ///
    se_pct_change coef_abs_diff sign_changed stars_changed

sort model variable

quietly summarize coef_abs_diff, meanonly
di as text "============================================================"
di as result ///
    "WP-07 MAX ABS COEFFICIENT DIFFERENCE LAG(4) VS LAG(2): " ///
    %12.10f r(max)

count if sign_changed
di as result "WP-07 SIGN CHANGES: " r(N)

count if stars_changed
di as result "WP-07 SIGNIFICANCE-STAR CHANGES: " r(N)

di as text "============================================================"
di as text "ROWS WITH SIGN OR SIGNIFICANCE-STAR CHANGES"
list model variable ///
    b_lag4 se_lag4 p_lag4 stars_lag4 ///
    b_lag2 se_lag2 p_lag2 stars_lag2 ///
    se_pct_change sign_changed stars_changed ///
    if sign_changed | stars_changed, noobs abbreviate(32)

export delimited using ///
    "`root'\src\econometrics\wp07_reestimation\WP07_DK_Bandwidth_Sensitivity_Audit.csv", ///
    replace

restore
*===============================================================================
* 15. FINAL TABLE EXPORT
*===============================================================================

local table_keep ///
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

local table_options ///
    keep(`table_keep') ///
    varlabels(vix "VIX" ///
              real_fed_3m_spf "Real Fed 3M forward" ///
              real_exchange_rate "Real USD/BRL index" ///
              real_brazil_3m_focus "Real Brazil 3M rate" ///
              gdp_yoy "GDP growth (YoY)" ///
              debt_gdp "Fiscal balance (% of GDP)" ///
              sovereign_spread_brl "Sovereign risk (BRL)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              tot_debt_to_ebitda "Total debt / EBITDA" ///
              days_to_maturity "Residual maturity (years, BUS/252)") ///
    mtitles("M1: Global" ///
            "M2: Local macro" ///
            "M3: + Sovereign" ///
            "M4: Full" ///
            "M5: Full 2 - no Sov Risk" ///
            "M6: Full 3 - no Sov Risk / no Brazil 3M" ///
            "M7: Parsimonious") ///
    b(4) se(4) ///
    stats(N r2_w N_g rho, ///
          fmt(0 4 0 4) ///
          labels("Observations" ///
                 "Within R-squared" ///
                 "Number of bonds" ///
                 "rho")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Bond fixed effects in all specifications." ///
             "Driscoll-Kraay standard errors with maximum lag 4." ///
             "All columns use the same 4,648-observation sample (103 bonds)." ///
             "Real Fed 3M uses SPF expected inflation." ///
             "Real Brazil 3M uses Focus expected IPCA." ///
             "RER is the bilateral USD/BRL CPI-based real exchange-rate index." ///
             "M5 removes sovereign risk from the Full specification." ///
             "M6 removes sovereign risk and the Real Brazil 3M rate from the Full specification." ///
             "M7 is the parsimonious VIX + Real Fed 3M + sovereign-risk specification." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

esttab M1_DK M2_DK M3_DK M4_DK M5_DK M6_DK M7_DK using ///
    "`root'\src\econometrics\wp07_reestimation\WP07_DK_Bandwidth_Sensitivity_Lag4_Baseline.txt", ///
    replace `table_options'

esttab M1_DK M2_DK M3_DK M4_DK M5_DK M6_DK M7_DK using ///
    "`root'\src\econometrics\wp07_reestimation\WP07_DK_Bandwidth_Sensitivity_Lag4_Baseline.rtf", ///
    replace rtf `table_options'

di as text "============================================================"
di as result "FINAL SEVEN-MODEL FE-DK TABLE COMPLETED"
di as result "Sample: 4,648 observations / 103 bonds / 48 issuers"
di as result "Window: 2010m12-2025m6"
di as result "DK maximum lag: 4"
di as text "============================================================"

log close
exit
