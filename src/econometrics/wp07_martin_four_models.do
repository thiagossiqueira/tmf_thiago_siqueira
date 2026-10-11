*===============================================================================
* WP-07 - Martin four-model specification
* DATA PREPARATION + SPECIFICATION ONLY
* No regressions are run and the frozen WP-06 panel is never overwritten.
*===============================================================================

clear all
set more off

local root "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"

*-------------------------------------------------------------------------------
* 1. Load frozen WP-06 panel
*-------------------------------------------------------------------------------
import excel using ///
    "`root'\datos_y_modelos\db\econometrics_db\panel_main_and_robustness_rebuilt.xlsx", ///
    sheet("ts") firstrow clear

* Frozen workbook month imports as Excel/Stata datetime.
gen double month_id = mofd(dofc(month))
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "month_id could not be constructed for all frozen-panel rows."
    exit 198
}

tempfile frozen_panel
save `frozen_panel'

*-------------------------------------------------------------------------------
* 2. Load reproducible CPI level inputs for bilateral RER
*
* US:
*   BLS CUUR0000SA0
*   CPI-U, All Items, US city average, not seasonally adjusted
*   Bloomberg equivalent: CPURNSA Index
*
* Brazil:
*   BZCLVLUE Index
*   Brazil IPCA accumulated price-index level
*   aligned to IPCA reference month
*-------------------------------------------------------------------------------
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

*-------------------------------------------------------------------------------
* 3. Merge CPI inputs into frozen panel in memory only
*-------------------------------------------------------------------------------
use `frozen_panel', clear

merge m:1 month_id using `rer_inputs'

count if _merge != 3
if r(N)>0 {
    di as error "CPI merge did not match all frozen-panel observations."
    tab _merge
    exit 459
}
drop _merge

count if missing(cpi_us_index, cpi_br_index)
if r(N)>0 {
    di as error "Missing CPI inputs after merge."
    exit 459
}

*-------------------------------------------------------------------------------
* 4. Construct bilateral real USD/BRL exchange-rate index
*
* Price-level formulation:
*   RER_t = USD/BRL_t * CPI_US_t / CPI_BR_t
*
* CPI levels enter directly. Monthly inflation would instead require
* CPI_t / CPI_(t-1) - 1, which is not the variable used here.
*
* Increase in RER = BRL real depreciation.
*-------------------------------------------------------------------------------
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

* Validation only
count if missing(real_exchange_rate)
summarize real_exchange_rate

*===============================================================================
* FOUR LOCKED RHS SPECIFICATIONS
*===============================================================================

* Model 1 - NER baseline
local model1_x ///
    vix ///
    fed_3m_forward ///
    usd_brl ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    amount_issued_to_bs_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* Model 2 - RER replaces NER
local model2_x ///
    vix ///
    fed_3m_forward ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    amount_issued_to_bs_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* Model 3 - sovereign-risk-focused specification
local model3_x ///
    vix ///
    fed_3m_forward ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    amount_issued_to_bs_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* Model 4 - local macro/RER specification without sovereign risk
local model4_x ///
    vix ///
    fed_3m_forward ///
    real_exchange_rate ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    amount_issued_to_bs_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

*-------------------------------------------------------------------------------
* STOP HERE.
* No xtset, xtreg, xtscc, estimates store, export, or permanent save yet.
*-------------------------------------------------------------------------------

*===============================================================================
* SAMPLE AUDIT ONLY - no regressions
*===============================================================================

gen byte sample_m1 = 1
markout sample_m1 spread `model1_x'

gen byte sample_m2 = 1
markout sample_m2 spread `model2_x'

gen byte sample_m3 = 1
markout sample_m3 spread `model3_x'

gen byte sample_m4 = 1
markout sample_m4 spread `model4_x'

foreach m in 1 2 3 4 {
    di as text "--------------------------------------------------"
    di as text "MODEL `m' COMPLETE-CASE SAMPLE"
    count if sample_m`m'
    summarize month_id if sample_m`m', meanonly
    di as result "First month: " %tm r(min)
    di as result "Last month:  " %tm r(max)

    levelsof bond_id if sample_m`m', local(bonds)
    local nbonds : word count `bonds'
    di as result "Number of bonds: `nbonds'"

    levelsof issuer if sample_m`m', local(issuers)
    local nissuers : word count `issuers'
    di as result "Number of issuers: `nissuers'"
}

*-------------------------------------------------------------------------------
* STOP HERE.
* Still no estimation commands.
*-------------------------------------------------------------------------------


*===============================================================================
* COMMON ESTIMATION SAMPLE
*===============================================================================

* Models 1-3 have identical complete-case samples.
* Use that sample for all four models so coefficient differences across columns
* reflect specification changes rather than changes in observations/bonds.

gen byte sample_common = sample_m1

count if sample_common
di as result "COMMON SAMPLE OBSERVATIONS: " r(N)

count if sample_m4 & !sample_common
di as result "MODEL 4 EXTRA OBSERVATIONS EXCLUDED FOR COMPARABILITY: " r(N)

*-------------------------------------------------------------------------------
* STOP HERE.
* No regressions yet.
*-------------------------------------------------------------------------------

*===============================================================================
* ESTIMATION VALIDATION - MODEL 1 ONLY
*===============================================================================

* Numeric panel identifier required by xtset/xtscc.
encode bond_id, gen(bond_id_num)

* Preserve monthly ordering used in the validated WP-07 baseline.
egen t_dk = group(month_id)
xtset bond_id_num t_dk

* Driscoll-Kraay FE estimate.
* Lag explicitly fixed at 4 for reproducibility.
xtscc spread `model1_x' if sample_common, fe lag(4)
estimates store M1_DK

local m1_N    = e(N)
local m1_Ng   = e(N_g)
local m1_r2w  = e(r2_w)

* Companion FE regression only to recover rho.
* Coefficients are the same within-estimator coefficients;
* final inference will use the DK standard errors above.
xtreg spread `model1_x' if sample_common, fe

local m1_rho = e(rho)

di as text "=================================================="
di as text "MODEL 1 VALIDATION SUMMARY"
di as result "Observations: " `m1_N'
di as result "Bonds:        " `m1_Ng'
di as result "Within R2:    " %9.6f `m1_r2w'
di as result "rho:          " %9.6f `m1_rho'
di as text "=================================================="

*-------------------------------------------------------------------------------
* STOP HERE.
* Models 2-4 are not estimated yet.
*-------------------------------------------------------------------------------

*===============================================================================
* ESTIMATION VALIDATION - MODEL 2
*===============================================================================

xtscc spread `model2_x' if sample_common, fe lag(4)
estimates store M2_DK

local m2_N    = e(N)
local m2_Ng   = e(N_g)
local m2_r2w  = e(r2_w)

* Companion FE regression only to recover rho.
xtreg spread `model2_x' if sample_common, fe
local m2_rho = e(rho)

di as text "=================================================="
di as text "MODEL 2 VALIDATION SUMMARY"
di as result "Observations: " `m2_N'
di as result "Bonds:        " `m2_Ng'
di as result "Within R2:    " %9.6f `m2_r2w'
di as result "rho:          " %9.6f `m2_rho'
di as text "=================================================="

*-------------------------------------------------------------------------------
* STOP HERE.
* Models 3-4 are not estimated yet.
*-------------------------------------------------------------------------------

*===============================================================================
* ESTIMATION VALIDATION - MODEL 3
*===============================================================================

xtscc spread `model3_x' if sample_common, fe lag(4)
estimates store M3_DK

local m3_N    = e(N)
local m3_Ng   = e(N_g)
local m3_r2w  = e(r2_w)

* Companion FE regression only to recover rho.
xtreg spread `model3_x' if sample_common, fe
local m3_rho = e(rho)

di as text "=================================================="
di as text "MODEL 3 VALIDATION SUMMARY"
di as result "Observations: " `m3_N'
di as result "Bonds:        " `m3_Ng'
di as result "Within R2:    " %9.6f `m3_r2w'
di as result "rho:          " %9.6f `m3_rho'
di as text "=================================================="

*-------------------------------------------------------------------------------
* STOP HERE.
* Model 4 is not estimated yet.
*-------------------------------------------------------------------------------

*===============================================================================
* ESTIMATION VALIDATION - MODEL 4
*===============================================================================

xtscc spread `model4_x' if sample_common, fe lag(4)
estimates store M4_DK

local m4_N    = e(N)
local m4_Ng   = e(N_g)
local m4_r2w  = e(r2_w)

* Companion FE regression only to recover rho.
xtreg spread `model4_x' if sample_common, fe
local m4_rho = e(rho)

di as text "=================================================="
di as text "MODEL 4 VALIDATION SUMMARY"
di as result "Observations: " `m4_N'
di as result "Bonds:        " `m4_Ng'
di as result "Within R2:    " %9.6f `m4_r2w'
di as result "rho:          " %9.6f `m4_rho'
di as text "=================================================="

*-------------------------------------------------------------------------------
* STOP HERE.
* All four models estimated; no table export yet.
*-------------------------------------------------------------------------------

*===============================================================================
* SIDE-BY-SIDE VALIDATION TABLE - ALL FOUR DK MODELS
*===============================================================================

estimates table M1_DK M2_DK M3_DK M4_DK, ///
    b(%9.4f) se(%9.4f) stats(N r2_w)

di as text "--------------------------------------------------"
di as text "RHO FROM COMPANION FE REGRESSIONS"
di as result "Model 1 rho: " %9.6f `m1_rho'
di as result "Model 2 rho: " %9.6f `m2_rho'
di as result "Model 3 rho: " %9.6f `m3_rho'
di as result "Model 4 rho: " %9.6f `m4_rho'

*-------------------------------------------------------------------------------
* STOP HERE.
* No final Word/RTF export yet.
*-------------------------------------------------------------------------------
