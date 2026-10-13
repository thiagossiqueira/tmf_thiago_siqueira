*===============================================================================
* LEGACY / HISTORICAL - NOT FOR FINAL RESULTS
* Real Fed 3M SPF robustness
*
* This file preserves the original WP-08 robustness exercise committed in
* 9c1fd41. It uses the historical WP-08 specification and sample lock and
* must not be used to reproduce the final seven-model FE-DK results.
*
* Director request: test whether the U.S. 3M nominal-rate control can be
* expressed in real terms by netting expected inflation.
*
* Comparison:
*   Nominal: fed_3m_forward
*   Real:    real_fed_3m_spf = USSOC 3M OIS - SPF next-quarter CPI expectation
*
* Exact WP-08 Model 5 sample and controls are preserved.
* Frozen WP-06 panel is never overwritten.
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
* 2. Load validated real-Fed monthly robustness input
*-------------------------------------------------------------------------------
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

*-------------------------------------------------------------------------------
* 3. Merge real-Fed input into frozen panel in memory only
*
* Real-Fed series begins in 2016m1, matching the effective sovereign-risk
* regression window. Pre-2016 frozen-panel observations may therefore remain
* master-only and are not an error.
*-------------------------------------------------------------------------------
use `frozen_panel', clear

merge m:1 month_id using `real_fed_inputs'

count if _merge == 2
if r(N)>0 {
    di as error "Real-Fed input contains months not present in frozen panel."
    tab _merge
    exit 459
}

* Validate nominal leg against the frozen-panel Fed variable wherever matched.
gen double fed_nominal_diff = ///
    abs(fed_3m_forward - ussoc_px_last) if _merge == 3

quietly summarize fed_nominal_diff, meanonly
di as result "MAX |panel Fed - USSOC input|: " %12.10f r(max)

count if fed_nominal_diff > 1e-6 & !missing(fed_nominal_diff)
if r(N)>0 {
    di as error "USSOC nominal leg does not reproduce frozen-panel fed_3m_forward."
    exit 459
}

drop _merge fed_nominal_diff

label variable real_fed_3m_spf ///
    "Real US 3M OIS: USSOC minus SPF expected next-quarter CPI"

*===============================================================================
* 4. LOCKED MODEL-1 / MODEL-5 SPECIFICATIONS
*===============================================================================

* WP-08 Model 5: exact Model 1 excluding issue size.
local model_nominal ///
    vix ///
    fed_3m_forward ///
    usd_brl ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* Real-Fed robustness: only the Fed variable changes.
local model_real ///
    vix ///
    real_fed_3m_spf ///
    usd_brl ///
    gdp_yoy ///
    debt_gdp ///
    sovereign_spread_brl ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

*-------------------------------------------------------------------------------
* 5. Reproduce exact WP-08 Model-5 common sample
*
* Issue size is NOT a regressor here. It enters only the sample lock, exactly
* as in validated WP-08, so the comparison remains on N=3,918 observations.
*-------------------------------------------------------------------------------
gen byte sample_common = 1
markout sample_common spread `model_nominal'
markout sample_common amount_issued_to_bs_tot_asset

count if sample_common
di as result "COMMON SAMPLE OBSERVATIONS: " r(N)

if r(N) != 3918 {
    di as error "Expected validated WP-08 sample N=3918."
    exit 459
}

count if sample_common & missing(real_fed_3m_spf)
di as result "MISSING REAL FED WITHIN COMMON SAMPLE: " r(N)

if r(N)>0 {
    di as error "Real Fed series is incomplete within locked sample."
    exit 459
}

*-------------------------------------------------------------------------------
* 6. Panel setup
*-------------------------------------------------------------------------------
encode bond_id, gen(bond_id_num)

egen t_dk = group(month_id)
xtset bond_id_num t_dk

*===============================================================================
* 7. NOMINAL MODEL - validated WP-08 Model 5
*===============================================================================
xtscc spread `model_nominal' if sample_common, fe lag(4)
estimates store M5_NOMINAL

local nominal_N   = e(N)
local nominal_Ng  = e(N_g)
local nominal_r2w = e(r2_w)

xtreg spread `model_nominal' if sample_common, fe
local nominal_rho = e(rho)

*===============================================================================
* 8. REAL-FED MODEL - identical except Fed rate
*===============================================================================
xtscc spread `model_real' if sample_common, fe lag(4)
estimates store M6_REAL_SPF

local real_N   = e(N)
local real_Ng  = e(N_g)
local real_r2w = e(r2_w)

xtreg spread `model_real' if sample_common, fe
local real_rho = e(rho)

*===============================================================================
* 9. Validation / side-by-side results
*===============================================================================
di as text "============================================================"
di as text "REAL FED 3M SPF ROBUSTNESS"
di as text "Same sample; bond FE; Driscoll-Kraay lag(4)"
di as text "============================================================"

estimates table M5_NOMINAL M6_REAL_SPF, ///
    b(%9.4f) se(%9.4f) p(%9.4f) stats(N r2_w)

di as text "------------------------------------------------------------"
di as result "Nominal N:      " `nominal_N'
di as result "Real N:         " `real_N'
di as result "Nominal bonds:  " `nominal_Ng'
di as result "Real bonds:     " `real_Ng'
di as result "Nominal R2w:    " %9.6f `nominal_r2w'
di as result "Real R2w:       " %9.6f `real_r2w'
di as result "Nominal rho:    " %9.6f `nominal_rho'
di as result "Real rho:       " %9.6f `real_rho'
di as text "============================================================"

* No permanent dataset save.

