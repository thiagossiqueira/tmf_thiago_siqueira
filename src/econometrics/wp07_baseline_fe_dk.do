clear all
capture log close
set more off
version 15
set varabbrev off

global project "C:\Users\tsiqueira4\PycharmProjects\tmf_thiago_siqueira"
global db      "$project\datos_y_modelos\db\econometrics_db"
global out     "$project\src\econometrics\wp07_reestimation"

capture mkdir "$out"
cd "$out"

import excel "$db\panel_main_and_robustness_rebuilt.xlsx", sheet("ts") firstrow clear

* Normalize names created by Excel/Stata import.
capture rename exchangeid exchange_id

* Panel identifiers.
encode bond_id, gen(bond_id_num)
drop bond_id
rename bond_id_num bond_id

encode issuer, gen(issuer_num)
drop issuer
rename issuer_num issuer

* Categorical variables retained only for legacy FE parity.
encode bond_type, gen(bond_type_cat)
encode sector, gen(sector_cat)

* Monthly panel date.
gen double month_id = mofd(dofc(month))
format month_id %tm

count if missing(month_id)
if r(N)>0 {
    di as error "month_id could not be constructed for all observations."
    exit 198
}
sort bond_id month_id
xtset bond_id month_id

local firm_controls ///
    cf_cash_oper_to_tot_asset ///
    amount_issued_to_bs_tot_asset ///
    tot_debt_to_ebitda ///
    days_to_maturity

local base_x ///
    vix ///
    fed_3m_forward ///
    usd_brl ///
    gdp_yoy ///
    debt_gdp ///
    `firm_controls' ///
    sovereign_spread_brl

capture log close
log using "WP07_baseline_FE_DK.log", text replace

* Baseline FE: legacy specification, issuer-clustered SEs.
xtreg spread `base_x' i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE

* Driscoll-Kraay: legacy xtscc implementation.
capture noisily ssc install xtscc, replace
egen t_dk = group(month_id)
xtset bond_id t_dk
xtscc spread `base_x', fe lag(4)
estimates store DK

log close


*---------------------------------------------------
* WP-07 Table 5-style baseline: FE vs Driscoll-Kraay
*---------------------------------------------------
capture which esttab
if _rc {
    ssc install estout, replace
}

esttab FE DK using "Table5_WP07_FE_DK.txt", replace ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity sovereign_spread_brl) ///
    varlabels(vix "VIX" ///
              fed_3m_forward "Fed 3M forward" ///
              usd_brl "USD/BRL" ///
              gdp_yoy "GDP growth (YoY)" ///
              debt_gdp "Gross government debt (% GDP)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              amount_issued_to_bs_tot_asset "Issue amount / total assets" ///
              tot_debt_to_ebitda "Total debt / EBITDA" ///
              days_to_maturity "Residual maturity (years, BUS/252)" ///
              sovereign_spread_brl "Sovereign spread BRL") ///
    mtitles("FE" "Driscoll-Kraay") ///
    b(4) se(4) ///
    stats(N r2_w N_g, ///
          fmt(0 4 0) ///
          labels("Observations" "Within R-squared" "Number of bonds")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Bond fixed effects included in both specifications." ///
             "Column (1): standard errors clustered by issuer." ///
             "Column (2): Driscoll-Kraay standard errors, maximum lag 4." ///
             "* p<0.10, ** p<0.05, *** p<0.01")

esttab FE DK using "Table5_WP07_FE_DK.rtf", replace rtf ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity sovereign_spread_brl) ///
    varlabels(vix "VIX" ///
              fed_3m_forward "Fed 3M forward" ///
              usd_brl "USD/BRL" ///
              gdp_yoy "GDP growth (YoY)" ///
              debt_gdp "Gross government debt (% GDP)" ///
              cf_cash_oper_to_tot_asset "Operating cash flow / total assets" ///
              amount_issued_to_bs_tot_asset "Issue amount / total assets" ///
              tot_debt_to_ebitda "Total debt / EBITDA" ///
              days_to_maturity "Residual maturity (years, BUS/252)" ///
              sovereign_spread_brl "Sovereign spread BRL") ///
    mtitles("FE" "Driscoll-Kraay") ///
    b(4) se(4) ///
    stats(N r2_w N_g, ///
          fmt(0 4 0) ///
          labels("Observations" "Within R-squared" "Number of bonds")) ///
    star(* 0.10 ** 0.05 *** 0.01) ///
    nocons nonotes ///
    addnotes("Bond fixed effects included in both specifications." ///
             "Column (1): standard errors clustered by issuer." ///
             "Column (2): Driscoll-Kraay standard errors, maximum lag 4." ///
             "* p<0.10, ** p<0.05, *** p<0.01")
