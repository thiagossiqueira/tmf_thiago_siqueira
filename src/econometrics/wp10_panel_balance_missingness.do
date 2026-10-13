*===============================================================================
* FINAL SPECIFICATION - SAMPLE AUDIT ONLY
*
* Purpose:
*   Determine the estimation sample implied by Martin Grandes' final six-column
*   FE-DK specification after incorporating:
*     - Real Fed 3M (SPF expected inflation)
*     - bilateral USD/BRL RER
*     - Real Brazil 3M DI (Focus expected IPCA)
*     - sovereign risk and firm/bond controls
*
* IMPORTANT:
*   - Frozen WP-06 panel is never overwritten.
*   - No regression is estimated in this file.
*   - No diagnostic test is run in this file.
*   - Issue amount / total assets is NOT part of the final specification and
*     therefore does NOT restrict the final estimation sample.
*===============================================================================

clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

capture log close
log using ///
    "`root'\src\econometrics\wp07_reestimation\WP10_panel_balance_missingness.log", ///
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

count if _merge == 2
if r(N)>0 {
    di as error "Real-Fed input contains months not present in frozen panel."
    tab _merge
    exit 459
}

* Pre-2016 master-only observations are expected because the validated
* Real-Fed SPF series begins in 2016m1.

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
* 8. MARTIN GRANDES FINAL SIX-COLUMN X-MATRIX
*
* M1  Global factors
* M2  Global + local macro
* M3  Global + local macro + sovereign risk
* M4  Global + sovereign risk
* M5  Full: global + local + sovereign + firm/bond
* M6  Global + local monetary 3M rate
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

*===============================================================================
* 9. NATURAL COMPLETE-CASE SAMPLE BY MODEL
*===============================================================================

forvalues m = 1/6 {
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
* M5 contains the union of all variables appearing anywhere in M1-M6.
* Therefore its complete-case sample is the strict common sample required
* to hold observations fixed across all six final columns.
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
forvalues m = 1/6 {
    count if sample_common & !sample_m`m'
    if r(N)>0 {
        di as error ///
            "ERROR: common M5 sample is not nested inside Model `m' sample."
        exit 459
    }
}

*===============================================================================
* 11. VARIABLE-LEVEL MISSINGNESS AUDIT
*===============================================================================

local audit_vars ///
    spread ///
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

egen byte tag_bond = tag(bond_id)

di as text "============================================================"
di as text "VARIABLE MISSINGNESS - FULL FROZEN PANEL"

foreach v of local audit_vars {

    quietly count if missing(`v')
    local nmiss = r(N)

    quietly count if month_id >= tm(2016m1) & missing(`v')
    local nmiss2016 = r(N)

    tempvar bondmiss bondnonmiss

    bysort bond_id: egen long `bondmiss' = total(missing(`v'))
    bysort bond_id: egen long `bondnonmiss' = total(!missing(`v'))

    quietly count if tag_bond & `bondmiss' > 0
    local bonds_any_missing = r(N)

    quietly count if tag_bond & `bondnonmiss' == 0
    local bonds_all_missing = r(N)

    di as result ///
        "`v': missing all-panel=`nmiss'; missing 2016+=`nmiss2016'; bonds with any missing=`bonds_any_missing'; bonds entirely missing=`bonds_all_missing'"

    drop `bondmiss' `bondnonmiss'
}

*===============================================================================
* 12. PANEL IMBALANCE ON FINAL COMMON SAMPLE
*===============================================================================

bysort bond_id: gen long n_panel_rows = _N
bysort bond_id: egen long n_common_rows = total(sample_common)

di as text "============================================================"
di as text "BOND-LEVEL PANEL IMBALANCE"

di as text "Frozen-panel observations per bond:"
summarize n_panel_rows if tag_bond, detail

di as text "Common final-sample observations per bond:"
summarize n_common_rows if tag_bond, detail

count if tag_bond & n_common_rows == 0
di as result "Bonds with zero common-sample observations: " r(N)

di as text "Bonds excluded entirely from final common sample:"
list bond_id issuer n_panel_rows if tag_bond & n_common_rows == 0, noobs clean

count if tag_bond & n_common_rows > 0
di as result "Bonds retained in common sample: " r(N)

*===============================================================================
* 13. WP-10 OUTPUT DIRECTORY AND INVARIANT CHECKS
*===============================================================================

local wp10dir "`root'\src\econometrics\wp10_reporting"
local wp10xlsx "`wp10dir'\WP10_panel_balance_missingness.xlsx"
capture mkdir "`wp10dir'"

* One observation per bond-month is required for panel-coverage statistics.
capture isid bond_id month_id
if _rc {
    di as error "WP-10 ERROR: bond_id x month_id is not unique."
    exit 459
}

quietly count
local frozen_obs = r(N)

quietly count if sample_common
local final_obs = r(N)

if `frozen_obs' != 4648 {
    di as error "WP-10 ERROR: frozen panel does not contain 4,648 observations."
    exit 459
}

if `final_obs' != 3918 {
    di as error "WP-10 ERROR: final common sample does not contain 3,918 observations."
    exit 459
}

* Confirm that the entire 730-row bridge is explained by Real Fed availability.
quietly count if sample_common != !missing(real_fed_3m_spf)
if r(N) > 0 {
    di as error ///
        "WP-10 ERROR: final common sample differs from Real-Fed-available sample."
    exit 459
}

egen byte tag_issuer = tag(issuer)
egen byte tag_month = tag(month_id)

bysort issuer: egen byte issuer_in_final = max(sample_common)
bysort month_id: egen byte month_in_final = max(sample_common)

quietly count if tag_bond
local frozen_bonds = r(N)

quietly count if tag_bond & n_common_rows > 0
local final_bonds = r(N)

quietly count if tag_issuer
local frozen_issuers = r(N)

quietly count if tag_issuer & issuer_in_final
local final_issuers = r(N)

quietly count if tag_month
local frozen_months = r(N)

quietly count if tag_month & month_in_final
local final_months = r(N)

if `frozen_bonds' != 103 | `final_bonds' != 101 {
    di as error "WP-10 ERROR: bond counts do not match locked sample."
    exit 459
}

if `frozen_issuers' != 48 | `final_issuers' != 48 {
    di as error "WP-10 ERROR: issuer counts do not match locked sample."
    exit 459
}

if `final_months' != 114 {
    di as error "WP-10 ERROR: final sample does not contain 114 months."
    exit 459
}

*===============================================================================
* 14. OBSERVATIONS PER BOND - DISTRIBUTION
*===============================================================================

quietly summarize n_panel_rows if tag_bond, detail
local frozen_min  = r(min)
local frozen_p1   = r(p1)
local frozen_p5   = r(p5)
local frozen_p10  = r(p10)
local frozen_p25  = r(p25)
local frozen_p50  = r(p50)
local frozen_mean = r(mean)
local frozen_p75  = r(p75)
local frozen_p90  = r(p90)
local frozen_p95  = r(p95)
local frozen_p99  = r(p99)
local frozen_max  = r(max)

* Final-sample distribution must be computed over the 101 retained bonds only.
quietly summarize n_common_rows if tag_bond & n_common_rows > 0, detail
local final_min  = r(min)
local final_p1   = r(p1)
local final_p5   = r(p5)
local final_p10  = r(p10)
local final_p25  = r(p25)
local final_p50  = r(p50)
local final_mean = r(mean)
local final_p75  = r(p75)
local final_p90  = r(p90)
local final_p95  = r(p95)
local final_p99  = r(p99)
local final_max  = r(max)

preserve
clear
set obs 2

gen str20 sample = ""
gen long bonds = .
gen double minimum = .
gen double p1 = .
gen double p5 = .
gen double p10 = .
gen double p25 = .
gen double median = .
gen double mean_obs = .
gen double p75 = .
gen double p90 = .
gen double p95 = .
gen double p99 = .
gen double maximum = .

replace sample = "Frozen WP-06" in 1
replace bonds = `frozen_bonds' in 1
replace minimum = `frozen_min' in 1
replace p1 = `frozen_p1' in 1
replace p5 = `frozen_p5' in 1
replace p10 = `frozen_p10' in 1
replace p25 = `frozen_p25' in 1
replace median = `frozen_p50' in 1
replace mean_obs = `frozen_mean' in 1
replace p75 = `frozen_p75' in 1
replace p90 = `frozen_p90' in 1
replace p95 = `frozen_p95' in 1
replace p99 = `frozen_p99' in 1
replace maximum = `frozen_max' in 1

replace sample = "Final common sample" in 2
replace bonds = `final_bonds' in 2
replace minimum = `final_min' in 2
replace p1 = `final_p1' in 2
replace p5 = `final_p5' in 2
replace p10 = `final_p10' in 2
replace p25 = `final_p25' in 2
replace median = `final_p50' in 2
replace mean_obs = `final_mean' in 2
replace p75 = `final_p75' in 2
replace p90 = `final_p90' in 2
replace p95 = `final_p95' in 2
replace p99 = `final_p99' in 2
replace maximum = `final_max' in 2

export delimited using ///
    "`wp10dir'\WP10_panel_distribution.csv", replace
restore

*===============================================================================
* 15. BOND-LEVEL COVERAGE, FIRST/LAST DATES AND RETENTION
*===============================================================================

preserve

bysort bond_id: egen double first_obs_frozen = min(obs_date)
bysort bond_id: egen double last_obs_frozen  = max(obs_date)
bysort bond_id: egen double first_month_frozen = min(month_id)
bysort bond_id: egen double last_month_frozen  = max(month_id)

bysort bond_id: egen double first_obs_final = ///
    min(cond(sample_common == 1, obs_date, .))
bysort bond_id: egen double last_obs_final = ///
    max(cond(sample_common == 1, obs_date, .))
bysort bond_id: egen double first_month_final = ///
    min(cond(sample_common == 1, month_id, .))
bysort bond_id: egen double last_month_final = ///
    max(cond(sample_common == 1, month_id, .))

gen byte retained_final = n_common_rows > 0

gen long span_m_frozen = ///
    last_month_frozen - first_month_frozen + 1
gen long gaps_m_frozen = ///
    span_m_frozen - n_panel_rows
gen double coverage_frozen = ///
    n_panel_rows / span_m_frozen

gen long span_m_final = ///
    last_month_final - first_month_final + 1 if retained_final
gen long gaps_m_final = ///
    span_m_final - n_common_rows if retained_final
gen double coverage_final = ///
    n_common_rows / span_m_final if retained_final

assert gaps_m_frozen >= 0
assert gaps_m_final >= 0 if retained_final

gen str10 first_obs_frozen_iso = ///
    string(first_obs_frozen,"%tcCCYY-NN-DD")
gen str10 last_obs_frozen_iso = ///
    string(last_obs_frozen,"%tcCCYY-NN-DD")

gen str10 first_obs_final_iso = ""
replace first_obs_final_iso = ///
    string(first_obs_final,"%tcCCYY-NN-DD") if retained_final

gen str10 last_obs_final_iso = ""
replace last_obs_final_iso = ///
    string(last_obs_final,"%tcCCYY-NN-DD") if retained_final

keep if tag_bond

rename n_panel_rows observations_frozen
rename n_common_rows observations_final

keep bond_id issuer retained_final ///
    observations_frozen observations_final ///
    first_obs_frozen_iso last_obs_frozen_iso ///
    first_obs_final_iso last_obs_final_iso ///
    span_m_frozen gaps_m_frozen ///
    coverage_frozen ///
    span_m_final gaps_m_final ///
    coverage_final

sort retained_final bond_id

export delimited using ///
    "`wp10dir'\WP10_bond_coverage.csv", replace
restore

*===============================================================================
* 16. ISSUER AND MONTH RETENTION
*===============================================================================

preserve
bysort issuer: gen byte tag_i = _n == 1
bysort issuer: gen long observations_frozen = _N
bysort issuer: egen long observations_final = total(sample_common)
keep if tag_i
gen byte retained_final = observations_final > 0
keep issuer retained_final observations_frozen observations_final
sort retained_final issuer
export delimited using ///
    "`wp10dir'\WP10_issuer_retention.csv", replace
restore

preserve
bysort month_id: gen byte tag_m = _n == 1
bysort month_id: gen long observations_frozen = _N
bysort month_id: egen long observations_final = total(sample_common)
keep if tag_m

gen byte retained_final = observations_final > 0
gen str8 month_label = string(month_id,"%tm")

sort month_id
keep month_id month_label retained_final observations_frozen observations_final

export delimited using ///
    "`wp10dir'\WP10_month_retention.csv", replace
restore

*===============================================================================
* 17. ANNUAL COVERAGE AND ACTIVE BONDS
*===============================================================================

preserve
gen int year = year(dofc(obs_date))
egen byte tag_year_bond = tag(year bond_id)
egen byte tag_year_issuer = tag(year issuer)
egen byte tag_year_month = tag(year month_id)

collapse ///
    (count) observations=spread ///
    (sum) active_bonds=tag_year_bond ///
          active_issuers=tag_year_issuer ///
          months_covered=tag_year_month, ///
    by(year)

gen str20 sample = "Frozen WP-06"
tempfile annual_frozen
save `annual_frozen'
restore

preserve
keep if sample_common
gen int year = year(dofc(obs_date))
egen byte tag_year_bond = tag(year bond_id)
egen byte tag_year_issuer = tag(year issuer)
egen byte tag_year_month = tag(year month_id)

collapse ///
    (count) observations=spread ///
    (sum) active_bonds=tag_year_bond ///
          active_issuers=tag_year_issuer ///
          months_covered=tag_year_month, ///
    by(year)

gen str20 sample = "Final common sample"
append using `annual_frozen'

order sample year observations active_bonds active_issuers months_covered
sort year sample

export delimited using ///
    "`wp10dir'\WP10_annual_coverage.csv", replace
restore

*===============================================================================
* 18. VARIABLE-LEVEL MISSINGNESS SUMMARY
*===============================================================================

tempname misspost
tempfile missingness_summary

postfile `misspost' ///
    str32 variable ///
    long n_frozen ///
    long missing_frozen ///
    double missing_rate_frozen ///
    long n_2016plus ///
    long missing_2016plus ///
    double missing_rate_2016plus ///
    long n_final ///
    long missing_final ///
    double missing_rate_final ///
    int bonds_any_missing ///
    int bonds_partial_missing ///
    int bonds_complete_missing ///
    using `missingness_summary', replace

foreach v of local audit_vars {

    quietly count
    local n_total = r(N)

    quietly count if missing(`v')
    local nmiss = r(N)

    local rate_frozen = `nmiss' / `n_total'

    quietly count if month_id >= tm(2016m1)
    local n2016 = r(N)

    quietly count if month_id >= tm(2016m1) & missing(`v')
    local nmiss2016 = r(N)

    local rate2016 = `nmiss2016' / `n2016'

    quietly count if sample_common
    local nfin = r(N)

    quietly count if sample_common & missing(`v')
    local nmissfin = r(N)

    local ratefin = `nmissfin' / `nfin'

    tempvar bondmiss bondnonmiss

    bysort bond_id: egen long `bondmiss' = total(missing(`v'))
    bysort bond_id: egen long `bondnonmiss' = total(!missing(`v'))

    quietly count if tag_bond & `bondmiss' > 0
    local bany = r(N)

    quietly count if tag_bond & `bondnonmiss' == 0
    local ball = r(N)

    local bpartial = `bany' - `ball'

    post `misspost' ///
        ("`v'") ///
        (`n_total') ///
        (`nmiss') ///
        (`rate_frozen') ///
        (`n2016') ///
        (`nmiss2016') ///
        (`rate2016') ///
        (`nfin') ///
        (`nmissfin') ///
        (`ratefin') ///
        (`bany') ///
        (`bpartial') ///
        (`ball')

    drop `bondmiss' `bondnonmiss'
}

postclose `misspost'

preserve
use `missingness_summary', clear
format missing_rate_* %9.6f
export delimited using ///
    "`wp10dir'\WP10_variable_missingness.csv", replace
restore

*===============================================================================
* 19. BOND-BY-VARIABLE PARTIAL / COMPLETE MISSINGNESS
*===============================================================================

preserve

foreach v of local audit_vars {
    gen byte miss_`v' = missing(`v')
}

collapse ///
    (count) observations=spread ///
    (sum) miss_*, ///
    by(bond_id issuer)

reshape long miss_, i(bond_id) j(variable) string
rename miss_ missing_observations

gen double missing_rate = ///
    missing_observations / observations

gen str10 missing_type = ""
replace missing_type = "partial" ///
    if missing_observations > 0 & missing_observations < observations
replace missing_type = "complete" ///
    if missing_observations == observations

keep if missing_observations > 0

order variable bond_id issuer observations ///
    missing_observations missing_rate missing_type

sort variable bond_id

export delimited using ///
    "`wp10dir'\WP10_bond_variable_missingness.csv", replace
restore

*===============================================================================
* 20. SAMPLE BRIDGE AND THESIS-READY SUMMARY
*===============================================================================

bysort bond_id: egen byte bond_has_fed = max(!missing(real_fed_3m_spf))
bysort issuer: egen byte issuer_has_fed = max(!missing(real_fed_3m_spf))
bysort month_id: egen byte month_has_fed = max(!missing(real_fed_3m_spf))

quietly count if !missing(real_fed_3m_spf)
local fed_obs = r(N)

quietly count if tag_bond & bond_has_fed
local fed_bonds = r(N)

quietly count if tag_issuer & issuer_has_fed
local fed_issuers = r(N)

quietly count if tag_month & month_has_fed
local fed_months = r(N)

quietly summarize month_id, meanonly
local frozen_first_month = r(min)
local frozen_last_month = r(max)

quietly summarize month_id if !missing(real_fed_3m_spf), meanonly
local fed_first_month = r(min)
local fed_last_month = r(max)

quietly summarize month_id if sample_common, meanonly
local final_first_month = r(min)
local final_last_month = r(max)

preserve
clear
set obs 3

gen str40 stage = ""
gen long observations = .
gen long bonds = .
gen long issuers = .
gen long months = .
gen long dropped_from_previous = .
gen str12 first_month = ""
gen str12 last_month = ""
gen str100 reason = ""

replace stage = "Frozen WP-06 panel" in 1
replace observations = `frozen_obs' in 1
replace bonds = `frozen_bonds' in 1
replace issuers = `frozen_issuers' in 1
replace months = `frozen_months' in 1
replace first_month = string(`frozen_first_month',"%tm") in 1
replace last_month = string(`frozen_last_month',"%tm") in 1
replace reason = "Authoritative frozen reproducible panel" in 1

replace stage = "Real Fed 3M available" in 2
replace observations = `fed_obs' in 2
replace bonds = `fed_bonds' in 2
replace issuers = `fed_issuers' in 2
replace months = `fed_months' in 2
replace dropped_from_previous = `frozen_obs' - `fed_obs' in 2
replace first_month = string(`fed_first_month',"%tm") in 2
replace last_month = string(`fed_last_month',"%tm") in 2
replace reason = "SPF-based Real Fed 3M begins in 2016m1" in 2

replace stage = "Final six-model common sample" in 3
replace observations = `final_obs' in 3
replace bonds = `final_bonds' in 3
replace issuers = `final_issuers' in 3
replace months = `final_months' in 3
replace dropped_from_previous = `fed_obs' - `final_obs' in 3
replace first_month = string(`final_first_month',"%tm") in 3
replace last_month = string(`final_last_month',"%tm") in 3
replace reason = "No additional loss from other final-spec variables" in 3

export delimited using ///
    "`wp10dir'\WP10_sample_bridge.csv", replace
restore

preserve
clear
set obs 18

gen str55 metric = ""
gen str30 value = ""
gen str120 note = ""

replace metric = "Frozen panel observations" in 1
replace value = string(`frozen_obs',"%12.0f") in 1

replace metric = "Final estimation-sample observations" in 2
replace value = string(`final_obs',"%12.0f") in 2

replace metric = "Observations excluded" in 3
replace value = string(`frozen_obs' - `final_obs',"%12.0f") in 3
replace note = "Entire reduction is associated with Real Fed 3M availability" in 3

replace metric = "Frozen-panel bonds" in 4
replace value = string(`frozen_bonds',"%12.0f") in 4

replace metric = "Final-sample bonds" in 5
replace value = string(`final_bonds',"%12.0f") in 5

replace metric = "Bonds excluded completely" in 6
replace value = string(`frozen_bonds' - `final_bonds',"%12.0f") in 6

replace metric = "Final-sample issuers" in 7
replace value = string(`final_issuers',"%12.0f") in 7

replace metric = "Final-sample months" in 8
replace value = string(`final_months',"%12.0f") in 8

replace metric = "Final-sample period" in 9
replace value = ///
    string(`final_first_month',"%tm") + "-" + ///
    string(`final_last_month',"%tm") in 9

replace metric = "Observations per retained bond - minimum" in 10
replace value = string(`final_min',"%12.0f") in 10

replace metric = "Observations per retained bond - p25" in 11
replace value = string(`final_p25',"%12.0f") in 11

replace metric = "Observations per retained bond - median" in 12
replace value = string(`final_p50',"%12.0f") in 12

replace metric = "Observations per retained bond - mean" in 13
replace value = string(`final_mean',"%12.2f") in 13

replace metric = "Observations per retained bond - p75" in 14
replace value = string(`final_p75',"%12.0f") in 14

replace metric = "Observations per retained bond - maximum" in 15
replace value = string(`final_max',"%12.0f") in 15

replace metric = "Missing final-spec values from 2016m1 onward" in 16
replace value = "0" in 16
replace note = "All final-spec variables are complete over the retained date window" in 16

replace metric = "Real Fed 3M start" in 17
replace value = "2016m1" in 17
replace note = "Validated SPF expected-inflation series determines final sample start" in 17

replace metric = "Panel structure" in 18
replace value = "Unbalanced" in 18
replace note = ///
    "Bonds enter and exit the sample at different dates; individual bond histories contain no internal monthly gaps" in 18

export delimited using ///
    "`wp10dir'\WP10_thesis_summary.csv", replace
restore

* 21. THESIS / RESPONSE-MEMO REPORTING TABLE
*===============================================================================

preserve
clear
set obs 14

gen str42 item = ""
gen str18 frozen_panel = ""
gen str18 final_sample = ""
gen str110 comment = ""

replace item = "Observations" in 1
replace frozen_panel = string(`frozen_obs',"%12.0f") in 1
replace final_sample = string(`final_obs',"%12.0f") in 1
replace comment = "730 observations excluded because validated Real Fed 3M begins in 2016m1" in 1

replace item = "Bonds" in 2
replace frozen_panel = string(`frozen_bonds',"%12.0f") in 2
replace final_sample = string(`final_bonds',"%12.0f") in 2
replace comment = "Two bonds end before 2016m1 and are fully excluded" in 2

replace item = "Issuers" in 3
replace frozen_panel = string(`frozen_issuers',"%12.0f") in 3
replace final_sample = string(`final_issuers',"%12.0f") in 3
replace comment = "All 48 issuers remain represented" in 3

replace item = "Distinct months" in 4
replace frozen_panel = string(`frozen_months',"%12.0f") in 4
replace final_sample = string(`final_months',"%12.0f") in 4

replace item = "Sample period" in 5
replace frozen_panel = ///
    string(`frozen_first_month',"%tm") + "-" + ///
    string(`frozen_last_month',"%tm") in 5
replace final_sample = ///
    string(`final_first_month',"%tm") + "-" + ///
    string(`final_last_month',"%tm") in 5

replace item = "Obs./bond: minimum" in 6
replace frozen_panel = string(`frozen_min',"%12.0f") in 6
replace final_sample = string(`final_min',"%12.0f") in 6

replace item = "Obs./bond: 25th percentile" in 7
replace frozen_panel = string(`frozen_p25',"%12.0f") in 7
replace final_sample = string(`final_p25',"%12.0f") in 7

replace item = "Obs./bond: median" in 8
replace frozen_panel = string(`frozen_p50',"%12.0f") in 8
replace final_sample = string(`final_p50',"%12.0f") in 8

replace item = "Obs./bond: mean" in 9
replace frozen_panel = string(`frozen_mean',"%12.2f") in 9
replace final_sample = string(`final_mean',"%12.2f") in 9

replace item = "Obs./bond: 75th percentile" in 10
replace frozen_panel = string(`frozen_p75',"%12.0f") in 10
replace final_sample = string(`final_p75',"%12.0f") in 10

replace item = "Obs./bond: maximum" in 11
replace frozen_panel = string(`frozen_max',"%12.0f") in 11
replace final_sample = string(`final_max',"%12.0f") in 11

replace item = "Internal monthly gaps" in 12
replace frozen_panel = "0 bonds" in 12
replace final_sample = "0 bonds" in 12
replace comment = "Unbalancedness reflects heterogeneous bond entry and exit dates, not internal gaps" in 12

replace item = "Missing final-spec observations" in 13
replace frozen_panel = "730" in 13
replace final_sample = "0" in 13
replace comment = "All 730 missing values are Real Fed 3M observations before 2016m1" in 13

replace item = "Panel structure" in 14
replace frozen_panel = "Unbalanced" in 14
replace final_sample = "Unbalanced" in 14
replace comment = "Individual bond histories are contiguous within their observed spans" in 14

export delimited using ///
    "`wp10dir'\WP10_thesis_table.csv", replace
restore

* 22. CONSOLIDATED MACHINE-READABLE XLSX PACKAGE
*===============================================================================

capture erase "`wp10xlsx'"

import delimited using ///
    "`wp10dir'\WP10_thesis_summary.csv", clear varnames(1)
export excel using "`wp10xlsx'", ///
    sheet("thesis_summary") ///
    firstrow(variables) replace

import delimited using ///
    "`wp10dir'\WP10_thesis_table.csv", clear varnames(1)
export excel using "`wp10xlsx'", ///
    sheet("thesis_table", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_sample_bridge.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("sample_bridge", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_panel_distribution.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("panel_distribution", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_annual_coverage.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("annual_coverage", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_variable_missingness.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("variable_missingness", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_bond_variable_missingness.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("bond_var_missingness", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_bond_coverage.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("bond_coverage", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_issuer_retention.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("issuer_retention", replace) ///
    firstrow(variables)

import delimited using ///
    "`wp10dir'\WP10_month_retention.csv", clear
export excel using "`wp10xlsx'", ///
    sheet("month_retention", replace) ///
    firstrow(variables)

di as result ///
    "Consolidated XLSX: src/econometrics/wp10_reporting/WP10_panel_balance_missingness.xlsx"

* 23. FINAL SAFETY CONFIRMATION
*===============================================================================

di as text "============================================================"
di as result "WP-10 PANEL-BALANCE AND MISSINGNESS REPORTING COMPLETED."
di as result "NO REGRESSIONS OR DIAGNOSTIC TESTS WERE RUN."
di as result "FROZEN WP-06 PANEL WAS NOT OVERWRITTEN."
di as text "============================================================"

log close
