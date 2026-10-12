*===============================================================================
* WP-08 - Brazil 3M DI referee/director robustness
*
* Purpose:
*   Add the validated Brazil 3M DI market-implied rate (Bloomberg YCSW0089
*   Index, 3M point) to the frozen WP-06 econometric panel in memory.
*
* Important:
*   - This is a referee/director robustness exercise, not a baseline replacement.
*   - Do not describe brazil_3m_di as a literal SELIC 3M forward-starting rate.
*   - Frozen panel is never overwritten.
*   - No regressions in this section.
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

count
if r(N)!=4648 {
    di as error "Frozen panel does not contain the expected 4,648 observations."
    exit 459
}

tempfile frozen_panel
save `frozen_panel'

*-------------------------------------------------------------------------------
* 2. Load validated Brazil 3M DI monthly series
*-------------------------------------------------------------------------------

import excel using ///
    "`root'\datos_y_modelos\db\brazil_macroeconomic_data\brazil_3m_di_forward\brazil_3m_di_ycsw0089_monthly.xlsx", ///
    sheet("brazil_3m_di_ycsw0089_monthly (") firstrow clear

gen double month_id = mofd(obs_date)
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "Brazil 3M DI month_id could not be constructed for all rows."
    exit 198
}

count if missing(curve_rate)
if r(N)>0 {
    di as error "Brazil 3M DI contains missing curve_rate observations."
    exit 459
}

count if status != "OK"
if r(N)>0 {
    di as error "Brazil 3M DI contains observations not marked OK."
    exit 459
}

count if obs_date != bloomberg_date
if r(N)>0 {
    di as error "Brazil 3M DI requested dates differ from Bloomberg returned dates."
    exit 459
}

count if curve != "YCSW0089 Index"
if r(N)>0 {
    di as error "Unexpected Bloomberg curve found in Brazil 3M DI input."
    exit 459
}

count if tenor != "3M"
if r(N)>0 {
    di as error "Unexpected tenor found in Brazil 3M DI input."
    exit 459
}

isid month_id

rename curve_rate brazil_3m_di

keep month_id brazil_3m_di

tempfile brazil_di
save `brazil_di'

*-------------------------------------------------------------------------------
* 3. Merge Brazil 3M DI into frozen panel in memory only
*-------------------------------------------------------------------------------

use `frozen_panel', clear

merge m:1 month_id using `brazil_di'

count if _merge == 1
if r(N)>0 {
    di as error "Frozen-panel observations without Brazil 3M DI match."
    tab _merge
    exit 459
}

count if _merge == 2
di as text "Brazil 3M DI months outside frozen panel: " r(N)

drop if _merge == 2
drop _merge

count if missing(brazil_3m_di)
if r(N)>0 {
    di as error "Missing brazil_3m_di after merge."
    exit 459
}

count
if r(N)!=4648 {
    di as error "Observation count changed after Brazil 3M DI merge."
    exit 459
}

summarize brazil_3m_di

di as text "=================================================="
di as text "BRAZIL 3M DI MERGE VALIDATION PASSED"
di as result "Frozen-panel observations: " _N
di as text "Variable: brazil_3m_di"
di as text "Definition: Brazil 3M DI market-implied rate"
di as text "Source: Bloomberg YCSW0089 Index, 3M point"
di as text "Units: annualized percentage points"
di as text "No permanent panel file was modified."
di as text "No regressions have been run."
di as text "=================================================="






*===============================================================================
* 4. Brazil 3M DI robustness specifications - SAMPLE AUDIT ONLY
*    These correspond to the former Models 5-6 in the pre-WP-08 tracker.
*===============================================================================

* DI robustness A - Brazil 3M DI with nominal Fed 3M retained.
* Required exclusions: FX, sovereign spread, relative issue size.
local model_di_fed ///
    vix ///
    fed_3m_forward ///
    brazil_3m_di ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

* DI robustness B - Brazil 3M DI with nominal Fed 3M omitted.
* Otherwise identical to DI robustness A.
local model_di_nofed ///
    vix ///
    brazil_3m_di ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

gen byte sample_di_fed = 1
markout sample_di_fed spread `model_di_fed'

gen byte sample_di_nofed = 1
markout sample_di_nofed spread `model_di_nofed'

count if sample_di_fed
di as result "DI + FED MODEL OBSERVATIONS: " r(N)
if r(N)!=4648 {
    di as error "Unexpected complete-case sample for DI + Fed model."
    exit 459
}

count if sample_di_nofed
di as result "DI WITHOUT FED MODEL OBSERVATIONS: " r(N)
if r(N)!=4648 {
    di as error "Unexpected complete-case sample for DI without Fed model."
    exit 459
}

count if sample_di_fed != sample_di_nofed
di as result "OBSERVATIONS WITH DIFFERENT SAMPLE STATUS: " r(N)
if r(N)!=0 {
    di as error "The two Brazil 3M DI specifications do not use identical samples."
    exit 459
}

di as text "=================================================="
di as text "BRAZIL 3M DI SPECIFICATION / SAMPLE AUDIT PASSED"
di as text "DI robustness A: Brazil 3M DI + nominal Fed 3M"
di as text "DI robustness B: Brazil 3M DI; nominal Fed 3M omitted"
di as text "FX omitted in both."
di as text "Sovereign spread omitted in both."
di as text "Relative issue size omitted in both."
di as text "Common estimation sample: 4,648 observations."
di as text "No regressions have been run."
di as text "=================================================="



*===============================================================================
* 5. Brazil 3M DI robustness - DI + nominal Fed 3M
*===============================================================================

encode bond_id, gen(bond_id_num)

egen t_dk = group(month_id)
xtset bond_id_num t_dk

* Bond FE with Driscoll-Kraay standard errors, maximum lag 4.
xtscc spread `model_di_fed' if sample_di_fed, fe lag(4)
estimates store DI_FED

local di_fed_N   = e(N)
local di_fed_Ng  = e(N_g)
local di_fed_r2w = e(r2_w)

* Companion conventional FE regression only to recover rho.
xtreg spread `model_di_fed' if sample_di_fed, fe
local di_fed_rho = e(rho)

di as text "=================================================="
di as text "BRAZIL 3M DI + FED 3M FE-DK RESULT"
di as result "Observations: " `di_fed_N'
di as result "Bonds: " `di_fed_Ng'
di as result "Within R-squared: " %9.6f `di_fed_r2w'
di as result "rho: " %9.6f `di_fed_rho'
di as text "DK maximum lag: 4"
di as text "=================================================="



*===============================================================================
* 6. Brazil 3M DI robustness - nominal Fed 3M omitted
*===============================================================================

xtscc spread `model_di_nofed' if sample_di_nofed, fe lag(4)
estimates store DI_NOFED

local di_nofed_N   = e(N)
local di_nofed_Ng  = e(N_g)
local di_nofed_r2w = e(r2_w)

* Companion conventional FE regression only to recover rho.
xtreg spread `model_di_nofed' if sample_di_nofed, fe
local di_nofed_rho = e(rho)

di as text "=================================================="
di as text "BRAZIL 3M DI WITHOUT FED 3M FE-DK RESULT"
di as result "Observations: " `di_nofed_N'
di as result "Bonds: " `di_nofed_Ng'
di as result "Within R-squared: " %9.6f `di_nofed_r2w'
di as result "rho: " %9.6f `di_nofed_rho'
di as text "DK maximum lag: 4"
di as text "=================================================="

*-------------------------------------------------------------------------------
* STOP HERE.
* Both Brazil 3M DI robustness specifications estimated.
* No table/export yet.
*-------------------------------------------------------------------------------




*===============================================================================
* 7. Within-transformed multicollinearity diagnostics
*===============================================================================

* VIF is calculated after removing bond-specific means, so the diagnostic
* reflects the within variation used by the fixed-effects estimator.

gen double w_spread = .
bysort bond_id_num: egen double mean_spread = mean(spread)
replace w_spread = spread - mean_spread

local within_all ///
    vix ///
    fed_3m_forward ///
    brazil_3m_di ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

foreach v of local within_all {
    bysort bond_id_num: egen double mean_`v' = mean(`v')
    gen double w_`v' = `v' - mean_`v'
}

di as text "=================================================="
di as text "WITHIN VIF - DI ROBUSTNESS A: BRAZIL 3M DI + FED 3M"
di as text "=================================================="

regress w_spread ///
    w_vix ///
    w_fed_3m_forward ///
    w_brazil_3m_di ///
    w_gdp_yoy ///
    w_debt_gdp ///
    w_cf_cash_oper_to_tot_asset ///
    w_tot_debt_to_ebitda ///
    w_days_to_maturity ///
    if sample_di_fed

estat vif

di as text "=================================================="
di as text "WITHIN VIF - DI ROBUSTNESS B: BRAZIL 3M DI WITHOUT FED 3M"
di as text "=================================================="

regress w_spread ///
    w_vix ///
    w_brazil_3m_di ///
    w_gdp_yoy ///
    w_debt_gdp ///
    w_cf_cash_oper_to_tot_asset ///
    w_tot_debt_to_ebitda ///
    w_days_to_maturity ///
    if sample_di_nofed

estat vif

di as text "=================================================="
di as text "WITHIN VIF DIAGNOSTICS COMPLETE"
di as text "=================================================="


*===============================================================================
* 8. Export Brazil 3M DI robustness table
*===============================================================================

* Attach rho from companion conventional FE regressions.
estadd scalar rho = `di_fed_rho'   : DI_FED
estadd scalar rho = `di_nofed_rho' : DI_NOFED

local di_table_keep ///
    vix ///
    fed_3m_forward ///
    brazil_3m_di ///
    gdp_yoy ///
    debt_gdp ///
    cf_cash_oper_to_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

esttab DI_FED DI_NOFED using ///
    "`root'\src\econometrics\wp07_reestimation\Table_WP08_Brazil_3M_DI_Robustness_DK.txt", ///
    replace ///
    keep(`di_table_keep') ///
    order(`di_table_keep') ///
    varlabels(vix "VIX" ///
              fed_3m_forward "Fed 3M forward" ///
              brazil_3m_di "Brazil 3M DI" ///
              gdp_yoy "GDP growth (YoY)" ///
              debt_gdp "Gross government debt (% GDP)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              tot_debt_to_ebitda "Total debt / EBITDA" ///
              days_to_maturity "Residual maturity (years, BUS/252)") ///
    mtitles("DI + Fed 3M" "DI; Fed omitted") ///
    b(4) se(4) ///
    stats(N r2_w N_g rho, ///
          fmt(0 4 0 4) ///
          labels("Observations" "Within R-squared" "Number of bonds" "rho")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Bond fixed effects in both specifications." ///
             "Driscoll-Kraay standard errors with maximum lag 4." ///
             "Both columns use the same 4,648-observation / 103-bond sample." ///
             "Brazil 3M DI is the 3M point of Bloomberg YCSW0089 Index, in annualized percentage points." ///
             "FX, sovereign spread and relative issue size are excluded from both specifications." ///
             "Column 2 differs from Column 1 only by omitting nominal Fed 3M." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

esttab DI_FED DI_NOFED using ///
    "`root'\src\econometrics\wp07_reestimation\Table_WP08_Brazil_3M_DI_Robustness_DK.rtf", ///
    replace rtf ///
    keep(`di_table_keep') ///
    order(`di_table_keep') ///
    varlabels(vix "VIX" ///
              fed_3m_forward "Fed 3M forward" ///
              brazil_3m_di "Brazil 3M DI" ///
              gdp_yoy "GDP growth (YoY)" ///
              debt_gdp "Gross government debt (% GDP)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              tot_debt_to_ebitda "Total debt / EBITDA" ///
              days_to_maturity "Residual maturity (years, BUS/252)") ///
    mtitles("DI + Fed 3M" "DI; Fed omitted") ///
    b(4) se(4) ///
    stats(N r2_w N_g rho, ///
          fmt(0 4 0 4) ///
          labels("Observations" "Within R-squared" "Number of bonds" "rho")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Bond fixed effects in both specifications." ///
             "Driscoll-Kraay standard errors with maximum lag 4." ///
             "Both columns use the same 4,648-observation / 103-bond sample." ///
             "Brazil 3M DI is the 3M point of Bloomberg YCSW0089 Index, in annualized percentage points." ///
             "FX, sovereign spread and relative issue size are excluded from both specifications." ///
             "Column 2 differs from Column 1 only by omitting nominal Fed 3M." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

di as text "BRAZIL 3M DI ROBUSTNESS TABLES EXPORTED."
