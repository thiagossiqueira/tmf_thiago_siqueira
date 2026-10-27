*===============================================================================
* WP-12C CONTROLLED LEVERAGE PROXY COMMON-SAMPLE BRIDGE
*
* Frozen source panel:
*   4,648 observations / 103 bonds / 48 issuers
*   2010m12 - 2025m6
*
* Strict final common sample:
*   3,303 observations / 93 bonds / 44 issuers
*   2011m3 - 2025m6
*
* Estimator:
*   Bond fixed effects
*   Driscoll-Kraay standard errors
*   Maximum lag = 4
*
* All eight final models use the same locked WP-12A common sample.
*===============================================================================
clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture mkdir "`root'\src\econometrics\wp12c_reestimation"
capture log close
log using ///
    "`root'\src\econometrics\wp12c_reestimation\WP12C_Leverage_Proxy_Common_Sample_Bridge.log", ///
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
* 5A. LOAD WP-12A BOOK DEBT / MARKET CAP
*===============================================================================

import delimited using ///
    "`root'\output\Informes jurado\WP12_same_entity_book_debt_to_mktcap_4648_brl_only.csv", ///
    varnames(1) clear

gen double leverage_date = date(obs_date, "YMD")
gen double month_id = mofd(leverage_date)
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "Could not construct Book Debt / Market Cap month_id."
    exit 459
}

isid bond_id month_id
keep bond_id month_id book_debt_to_market_cap

count if !missing(book_debt_to_market_cap)
if r(N) != 3303 {
    di as error "Expected 3,303 nonmissing Book Debt / Market Cap observations."
    exit 459
}

tempfile book_leverage_inputs
save `book_leverage_inputs'

*===============================================================================
* 5B. LOAD WP-12C TOTAL DEBT / TOTAL ASSETS
*===============================================================================

import delimited using ///
    "`root'\output\Informes jurado\WP12C_total_debt_to_total_assets_4648.csv", ///
    varnames(1) clear

gen double leverage_date = date(obs_date, "YMD")
gen double month_id = mofd(leverage_date)
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "Could not construct Total Debt / Total Assets month_id."
    exit 459
}

isid bond_id month_id
keep bond_id month_id total_debt_to_total_assets

count if !missing(total_debt_to_total_assets)
if r(N) != 4648 {
    di as error "Expected 4,648 nonmissing Total Debt / Total Assets observations."
    exit 459
}

tempfile tda_leverage_inputs
save `tda_leverage_inputs'

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
* 7A. MERGE BOTH LEVERAGE PROXIES
*===============================================================================

merge 1:1 bond_id month_id using `book_leverage_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Book Debt / Market Cap input did not match all panel keys."
    tab _merge
    exit 459
}
drop _merge

count if !missing(book_debt_to_market_cap)
if r(N) != 3303 {
    di as error "Expected 3,303 Book Debt / Market Cap observations after merge."
    exit 459
}

merge 1:1 bond_id month_id using `tda_leverage_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "Total Debt / Total Assets input did not match all panel keys."
    tab _merge
    exit 459
}
drop _merge

count if !missing(total_debt_to_total_assets)
if r(N) != 4648 {
    di as error "Expected 4,648 Total Debt / Total Assets observations after merge."
    exit 459
}

label variable book_debt_to_market_cap ///
    "Book debt / equity market cap"

label variable total_debt_to_total_assets ///
    "Total debt / total assets (%)"

*===============================================================================
* 8. CONTROLLED LEVERAGE-PROXY SPECIFICATIONS
*
* Objective:
* Hold the WP-12A sample fixed and change ONLY the leverage proxy.
*
* A = Book Total Debt / Equity Market Cap
* B = Total Debt / Total Assets
*
* FE bond + Driscoll-Kraay lag(4) in every regression.
*===============================================================================

local book4_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    book_debt_to_market_cap ///
    days_to_maturity

local tda4_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    total_debt_to_total_assets ///
    days_to_maturity

local book5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    book_debt_to_market_cap ///
    days_to_maturity

local tda5_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    total_debt_to_total_assets ///
    days_to_maturity

local book6_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    book_debt_to_market_cap ///
    days_to_maturity

local tda6_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    total_debt_to_total_assets ///
    days_to_maturity

local book8_x ///
    vix ///
    real_fed_3m_spf ///
    real_exchange_rate ///
    real_brazil_3m_focus ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    book_debt_to_market_cap ///
    cf_cash_oper_to_tot_asset ///
    days_to_maturity

local tda8_x ///
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
* 9. CONTROLLED SAMPLE
*===============================================================================

gen byte sample_wp12a = 1
markout sample_wp12a spread `book8_x'

gen byte sample_tda = 1
markout sample_tda spread `tda8_x'

count if sample_wp12a
local n_wp12a = r(N)

count if sample_tda
local n_tda = r(N)

gen byte sample_common = sample_wp12a & sample_tda

count if sample_common
local ncommon = r(N)

count if sample_common != sample_wp12a
if r(N)>0 {
    di as error "Controlled sample differs from the frozen WP-12A sample."
    exit 459
}

quietly summarize month_id if sample_common, meanonly
local common_first = r(min)
local common_last  = r(max)

levelsof bond_id if sample_common, local(common_bonds)
local ncommon_bonds : word count `common_bonds'

levelsof issuer if sample_common, local(common_issuers)
local ncommon_issuers : word count `common_issuers'

di as text "============================================================"
di as text "WP-12C CONTROLLED LEVERAGE-PROXY SAMPLE"
di as result "WP-12A Book Debt / Market Cap support: `n_wp12a'"
di as result "Total Debt / Total Assets support:     `n_tda'"
di as result "Controlled common sample:              `ncommon'"
di as result "First month: " %tm `common_first'
di as result "Last month:  " %tm `common_last'
di as result "Bonds:       `ncommon_bonds'"
di as result "Issuers:     `ncommon_issuers'"

if `n_wp12a' != 3303 {
    di as error "Expected WP-12A support of 3,303 observations."
    exit 459
}

if `n_tda' != 4648 {
    di as error "Expected Total Debt / Total Assets support of 4,648 observations."
    exit 459
}

if `ncommon' != 3303 {
    di as error "Expected controlled common sample of 3,303 observations."
    exit 459
}

if `ncommon_bonds' != 93 {
    di as error "Expected 93 bonds in controlled sample."
    exit 459
}

if `ncommon_issuers' != 44 {
    di as error "Expected 44 issuers in controlled sample."
    exit 459
}

if `common_first' != tm(2011m3) {
    di as error "Expected controlled sample to start in 2011m3."
    exit 459
}

if `common_last' != tm(2025m6) {
    di as error "Expected controlled sample to end in 2025m6."
    exit 459
}

di as result "CONTROLLED SAMPLE LOCK: PASS"

*===============================================================================
* 10. PROXY DESCRIPTIVES ON IDENTICAL SAMPLE
*===============================================================================

summarize ///
    book_debt_to_market_cap ///
    total_debt_to_total_assets ///
    if sample_common

pwcorr ///
    book_debt_to_market_cap ///
    total_debt_to_total_assets ///
    if sample_common, sig obs

*===============================================================================
* 11. PANEL SETUP
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
* 12. CONTROLLED FE-DK ESTIMATIONS
*===============================================================================

di as text "============================================================"
di as text "M4 - BOOK DEBT / MARKET CAP"
xtscc spread `book4_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store B4_DK

di as text "M4 - TOTAL DEBT / TOTAL ASSETS"
xtscc spread `tda4_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store T4_DK

di as text "============================================================"
di as text "M5 - BOOK DEBT / MARKET CAP"
xtscc spread `book5_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store B5_DK

di as text "M5 - TOTAL DEBT / TOTAL ASSETS"
xtscc spread `tda5_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store T5_DK

di as text "============================================================"
di as text "M6 - BOOK DEBT / MARKET CAP"
xtscc spread `book6_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store B6_DK

di as text "M6 - TOTAL DEBT / TOTAL ASSETS"
xtscc spread `tda6_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store T6_DK

di as text "============================================================"
di as text "M8 - BOOK DEBT / MARKET CAP"
xtscc spread `book8_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store B8_DK

di as text "M8 - TOTAL DEBT / TOTAL ASSETS"
xtscc spread `tda8_x' if sample_common, fe lag(4)
if e(N)!=3303 | e(N_g)!=93 {
    di as error "Controlled regression did not retain 3,303 observations / 93 bonds."
    exit 459
}
estimates store T8_DK

*===============================================================================
* 13. SIDE-BY-SIDE CONTROLLED RESULTS
*===============================================================================

di as text "============================================================"
di as text "M4 CONTROLLED: BOOK/MKTCAP VS DEBT/ASSETS"
estimates table B4_DK T4_DK, b(%10.4f) se(%10.4f) stats(N r2_w)

di as text "============================================================"
di as text "M5 CONTROLLED: BOOK/MKTCAP VS DEBT/ASSETS"
estimates table B5_DK T5_DK, b(%10.4f) se(%10.4f) stats(N r2_w)

di as text "============================================================"
di as text "M6 CONTROLLED: BOOK/MKTCAP VS DEBT/ASSETS"
estimates table B6_DK T6_DK, b(%10.4f) se(%10.4f) stats(N r2_w)

di as text "============================================================"
di as text "M8 CONTROLLED: BOOK/MKTCAP VS DEBT/ASSETS"
estimates table B8_DK T8_DK, b(%10.4f) se(%10.4f) stats(N r2_w)

*===============================================================================
* 14. EXPORT CONTROLLED BRIDGE
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
    total_debt_to_total_assets ///
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
              total_debt_to_total_assets "Total debt / total assets (%)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              days_to_maturity "Residual maturity (years, BUS/252)") ///
    mtitles("M4 Book/MCap" ///
            "M4 Debt/Assets" ///
            "M5 Book/MCap" ///
            "M5 Debt/Assets" ///
            "M6 Book/MCap" ///
            "M6 Debt/Assets" ///
            "M8 Book/MCap" ///
            "M8 Debt/Assets") ///
    b(4) se(4) ///
    stats(N r2_w N_g, ///
          fmt(0 4 0) ///
          labels("Observations" ///
                 "Within R-squared" ///
                 "Number of bonds")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Controlled comparison: identical 3,303-observation sample in every column." ///
             "93 bonds; 44 issuers; March 2011 to June 2025." ///
             "Only the leverage proxy changes within each model pair." ///
             "Bond fixed effects in all specifications." ///
             "Driscoll-Kraay standard errors with maximum lag 4." ///
             "Book/MCap is the WP-12A robustness proxy." ///
             "Debt/Assets is the director-specified WP-12C fallback." ///
             "Leverage coefficients are not directly magnitude-comparable because proxy definitions/scales differ." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

esttab ///
    B4_DK T4_DK ///
    B5_DK T5_DK ///
    B6_DK T6_DK ///
    B8_DK T8_DK ///
    using ///
    "`root'\src\econometrics\wp12c_reestimation\WP12C_Leverage_Proxy_Common_Sample_Bridge.txt", ///
    replace `table_options'

esttab ///
    B4_DK T4_DK ///
    B5_DK T5_DK ///
    B6_DK T6_DK ///
    B8_DK T8_DK ///
    using ///
    "`root'\src\econometrics\wp12c_reestimation\WP12C_Leverage_Proxy_Common_Sample_Bridge.rtf", ///
    replace rtf `table_options'

di as text "============================================================"
di as result "WP-12C CONTROLLED LEVERAGE PROXY BRIDGE COMPLETED"
di as result "Common sample: 3,303 observations / 93 bonds / 44 issuers"
di as result "Window: 2011m3-2025m6"
di as result "Only leverage proxy differs within each model pair."
di as result "DK maximum lag: 4"
di as text "============================================================"

log close
exit
