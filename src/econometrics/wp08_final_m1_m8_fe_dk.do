*===============================================================================
* WP-08 FINAL SPECIFICATION - EIGHT-MODEL FE DRISCOLL-KRAAY TABLE
*
* Frozen source panel:
*   4,648 observations / 103 bonds / 48 issuers
*   2010m12 - 2025m6
*
* Strict final common sample:
*   1,177 observations / 80 bonds / 38 issuers
*   2023m9 - 2025m6
*
* Estimator:
*   Bond fixed effects
*   Driscoll-Kraay standard errors
*   Maximum lag = 4
*
* All eight final models use the same locked WP-08 common sample.
*===============================================================================
clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture log close
log using ///
    "`root'\src\econometrics\wp08_reestimation\WP08_Final_M1_M8_FE_DK.log", ///
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
    "`root'\output\Informes jurado\WP12_same_entity_book_debt_to_mktcap_4648_brl_only.csv", ///
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

keep bond_id month_id book_debt_to_market_cap

count if !missing(book_debt_to_market_cap)
if r(N) != 3303 {
    di as error "Expected 3,303 nonmissing book debt / market cap observations."
    exit 459
}

tempfile leverage_inputs
save `leverage_inputs'
*===============================================================================
* 5B. LOAD FROZEN B3CT BOND-LIQUIDITY CANDIDATE
*===============================================================================

import delimited using ///
    "`root'\datos_y_modelos\db\econometrics_db\wp06b_bond_liquidity_candidate_v1.csv", ///
    varnames(1) clear

gen double liquidity_date = date(obs_date, "YMD")
gen double month_id = mofd(liquidity_date)
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "Could not construct liquidity month_id."
    exit 459
}

isid bond_id month_id

count
if r(N) != 4648 {
    di as error "Expected 4,648 rows in frozen bond-liquidity candidate."
    exit 459
}

count if liquidity_b3ct_usable == 1
if r(N) != 1344 {
    di as error "Expected 1,344 B3CT-usable bond-months."
    exit 459
}

count if !missing(bond_trading_day_share)
if r(N) != 1344 {
    di as error "Expected 1,344 nonmissing bond trading-day shares."
    exit 459
}

count if liquidity_b3ct_usable != 1 & !missing(bond_trading_day_share)
if r(N)>0 {
    di as error "Bond-liquidity values found outside frozen usable window."
    exit 459
}

keep bond_id month_id liquidity_b3ct_usable bond_trading_day_share

tempfile liquidity_inputs
save `liquidity_inputs'



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
*===============================================================================
* 7A. MERGE FROZEN LEVERAGE AND BOND-LIQUIDITY CANDIDATES
*===============================================================================

merge 1:1 bond_id month_id using `leverage_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Frozen leverage candidate did not match all panel bond-month keys."
    tab _merge
    exit 459
}
drop _merge

count if !missing(book_debt_to_market_cap)
if r(N) != 3303 {
    di as error "Expected 3,303 nonmissing leverage observations after merge."
    exit 459
}

merge 1:1 bond_id month_id using `liquidity_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Frozen bond-liquidity candidate did not match all panel bond-month keys."
    tab _merge
    exit 459
}
drop _merge

count if !missing(bond_trading_day_share)
if r(N) != 1344 {
    di as error "Expected 1,344 nonmissing bond-liquidity observations after merge."
    exit 459
}

count if !missing(book_debt_to_market_cap) & !missing(bond_trading_day_share)
if r(N) != 1177 {
    di as error "Expected 1,177 leverage x bond-liquidity overlap observations."
    exit 459
}

label variable book_debt_to_market_cap ///
    "Book debt / equity market cap"

label variable bond_trading_day_share ///
    "Verified trading days / eligible trading days"

* 8. FINAL EIGHT-COLUMN FE-DK X-MATRIX
*
* M1  Global
* M2  Global + local macro
* M3  Global + local macro + sovereign risk
* M4  Full: M3 + new leverage + bond liquidity + maturity
* M5  Full 2: M4 without sovereign risk
* M6  Full 3: M5 without Real Brazil 3M
* M7  Parsimonious: VIX + Real Fed 3M + sovereign risk
* M8  M4 + OCF/assets accounting-liquidity comparison
*
* Frozen WP-08 decisions:
*   Corporate spread -> geometric spread
*   Bond FE + Driscoll-Kraay lag(4)
*   Real Fed         -> real_fed_3m_spf
*   USD/BRL RER      -> real_exchange_rate
*   Brazil 3M        -> real_brazil_3m_focus
*   Fiscal           -> EHBBBR stored in debt_gdp
*   Sovereign risk   -> sovereign_spread_brl
*   Leverage         -> book_debt_to_market_cap
*   Bond liquidity   -> bond_trading_day_share
*
* OCF/assets is excluded from M1-M7 and returns only in M8.
* tot_debt_to_ebitda is excluded from the final WP-08 micro block.
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
    book_debt_to_market_cap ///
    bond_trading_day_share ///
    days_to_maturity

local model5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    book_debt_to_market_cap ///
    bond_trading_day_share ///
    days_to_maturity

local model6_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    book_debt_to_market_cap ///
    bond_trading_day_share ///
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
    book_debt_to_market_cap ///
    bond_trading_day_share ///
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

    if inlist(`m',1,2,3,7) {
        if `nobs' != 4648 {
            di as error "Model `m' should retain the full 4,648-observation panel."
            exit 459
        }
    }

    if inlist(`m',4,5,6,8) {
        if `nobs' != 1177 {
            di as error "Model `m' should have 1,177 observations in its natural sample."
            exit 459
        }
    }
}

* M8 adds OCF/assets to M4. OCF/assets must not further restrict the
* already leverage-and-bond-liquidity-constrained M4 sample.
count if sample_m4 != sample_m8
if r(N)>0 {
    di as error "M8 OCF/assets unexpectedly changes the M4 complete-case sample."
    exit 459
}

*===============================================================================
* 10. WP-08 SAMPLE BRIDGE
*===============================================================================

count
local bridge_panel = r(N)
if `bridge_panel' != 4648 {
    di as error "Frozen panel no longer contains 4,648 observations."
    exit 459
}

count if !missing(book_debt_to_market_cap)
local bridge_leverage = r(N)
if `bridge_leverage' != 3303 {
    di as error "Leverage bridge should contain 3,303 observations."
    exit 459
}

count if !missing(bond_trading_day_share)
local bridge_liquidity = r(N)
if `bridge_liquidity' != 1344 {
    di as error "Bond-liquidity bridge should contain 1,344 observations."
    exit 459
}

count if !missing(book_debt_to_market_cap) & !missing(bond_trading_day_share)
local bridge_both = r(N)
if `bridge_both' != 1177 {
    di as error "Joint leverage/liquidity bridge should contain 1,177 observations."
    exit 459
}

di as text "============================================================"
di as text "WP-08 SAMPLE BRIDGE"
di as result "Frozen v4 panel:                         `bridge_panel'"
di as result "Nonmissing new leverage:                 `bridge_leverage'"
di as result "Nonmissing bond liquidity:               `bridge_liquidity'"
di as result "Joint leverage x bond-liquidity sample:  `bridge_both'"

*===============================================================================
* 11. STRICT COMMON FINAL-TABLE SAMPLE
*
* M8 contains the union of all regressors appearing anywhere in M1-M8.
* Therefore its complete-case sample is the strict common sample used
* for the eight-column final table.
*===============================================================================

gen byte sample_common = sample_m8

count if sample_common
local ncommon = r(N)

quietly summarize month_id if sample_common, meanonly
local common_first = r(min)
local common_last  = r(max)

levelsof bond_id if sample_common, local(common_bonds)
local ncommon_bonds : word count `common_bonds'

levelsof issuer if sample_common, local(common_issuers)
local ncommon_issuers : word count `common_issuers'

di as text "============================================================"
di as text "STRICT COMMON FINAL-TABLE SAMPLE"
di as result "Observations: `ncommon'"
di as result "First month:  " %tm `common_first'
di as result "Last month:   " %tm `common_last'
di as result "Bonds:        `ncommon_bonds'"
di as result "Issuers:      `ncommon_issuers'"

* Verify that the strict common sample is admissible in every model.
forvalues m = 1/8 {
    count if sample_common & !sample_m`m'
    if r(N)>0 {
        di as error "Strict common sample is not nested inside Model `m'."
        exit 459
    }
}

*===============================================================================
* 12. LOCK WP-08 FINAL SAMPLE
*===============================================================================

if `ncommon' != 1177 {
    di as error "Expected 1,177 observations in WP-08 common sample."
    exit 459
}

if `ncommon_bonds' != 80 {
    di as error "Expected 80 bonds in WP-08 common sample."
    exit 459
}

if `ncommon_issuers' != 38 {
    di as error "Expected 38 issuers in WP-08 common sample."
    exit 459
}

if `common_first' != tm(2023m9) {
    di as error "Expected WP-08 common sample to start in 2023m9."
    exit 459
}

if `common_last' != tm(2025m6) {
    di as error "Expected WP-08 common sample to end in 2025m6."
    exit 459
}

*===============================================================================
* 13. PANEL SETUP FOR DRISCOLL-KRAAY
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
* 14. ESTIMATE FINAL EIGHT MODELS
*===============================================================================

forvalues m = 1/8 {

    di as text "============================================================"
    di as text "FINAL FE-DK MODEL `m'"
    di as text "============================================================"

    xtscc spread `model`m'_x' if sample_common, fe lag(4)
    estimates store M`m'_DK

    local m`m'_N   = e(N)
    local m`m'_Ng  = e(N_g)
    local m`m'_r2w = e(r2_w)

    if `m`m'_N' != `ncommon' {
        di as error "Model `m' does not use the locked WP-08 common sample."
        exit 459
    }

    if `m`m'_Ng' != `ncommon_bonds' {
        di as error "Model `m' does not use all locked WP-08 common-sample bonds."
        exit 459
    }

    * Companion FE regression only to recover rho.
    xtreg spread `model`m'_x' if sample_common, fe
    local m`m'_rho = e(rho)

    estadd scalar rho = `m`m'_rho' : M`m'_DK
}

*===============================================================================
* 15. SIDE-BY-SIDE VALIDATION
*===============================================================================

estimates table M1_DK M2_DK M3_DK M4_DK M5_DK M6_DK M7_DK M8_DK, ///
    b(%9.4f) se(%9.4f) stats(N r2_w)

*===============================================================================
* 16. FINAL TABLE EXPORT
*===============================================================================

local table_keep ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    book_debt_to_market_cap ///
    bond_trading_day_share ///
    cf_cash_oper_to_tot_asset ///
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
              book_debt_to_market_cap "Book debt / equity market cap" ///
              bond_trading_day_share "Bond trading-day share" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              days_to_maturity "Residual maturity (years, BUS/252)") ///
    mtitles("M1: Global" ///
            "M2: Local macro" ///
            "M3: + Sovereign" ///
            "M4: Full" ///
            "M5: Full 2 - no Sov Risk" ///
            "M6: Full 3 - no Sov Risk / no Brazil 3M" ///
            "M7: Parsimonious" ///
            "M8: Full + OCF/assets") ///
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
             "All columns use the same 1,177-observation sample (80 bonds; 38 issuers)." ///
             "Common-sample window: September 2023 to June 2025." ///
             "Real Fed 3M uses SPF expected inflation." ///
             "Real Brazil 3M uses Focus expected IPCA." ///
             "RER is the bilateral USD/BRL CPI-based real exchange-rate index." ///
             "Fiscal balance is the EHBBBR quarterly seasonally adjusted series." ///
             "M4 adds book debt / equity market cap, bond trading-day share, and maturity." ///
             "M5 removes sovereign risk from M4." ///
             "M6 additionally removes the Real Brazil 3M rate." ///
             "M7 is the parsimonious VIX + Real Fed 3M + sovereign-risk specification." ///
             "M8 adds OCF/assets to M4 as the accounting-liquidity comparison." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

esttab M1_DK M2_DK M3_DK M4_DK M5_DK M6_DK M7_DK M8_DK using ///
    "`root'\src\econometrics\wp08_reestimation\Table5_Final_Eight_Models_FE_DK.txt", ///
    replace `table_options'

esttab M1_DK M2_DK M3_DK M4_DK M5_DK M6_DK M7_DK M8_DK using ///
    "`root'\src\econometrics\wp08_reestimation\Table5_Final_Eight_Models_FE_DK.rtf", ///
    replace rtf `table_options'

di as text "============================================================"
di as result "WP-08 FINAL EIGHT-MODEL FE-DK TABLE COMPLETED"
di as result "Common sample: 1,177 observations / 80 bonds / 38 issuers"
di as result "Window: 2023m9-2025m6"
di as result "DK maximum lag: 4"
di as text "============================================================"

log close
exit
