clear all
capture log close
set more off
version 15
set varabbrev off

global project "C:\Users\tsiqueira4\OneDrive - Bloomberg LP\Desktop\Tesis\tmf_thiago_siqueira"
global db      "$project\datos_y_modelos\db\econometrics_db\paper_db_robusteness_check"
global out     "$project\src\econometrics\paper_econometrics\outputs_martin_robustness"

capture mkdir "$out"
cd "$out"
use "$db\paper_panel_main_and_robustness.dta", clear

capture rename _cf_cash_oper_to_tot_asset cf_cash_oper_to_tot_asset
capture rename cf_cash_oper_to_tot_asset_ cf_cash_oper_to_tot_asset
capture rename exchange_id exchange_id_unused
capture rename Date date
capture rename OBS_DATE obs_date
capture rename Obs_date obs_date
capture rename Month month
capture rename MONTH month

capture confirm variable spread
if _rc {
    local newvars bond_id issuer maturity bond_type exchange_id_unused sector obs_date month spread vix fed_3m_forward cpi_us_index cpi_br_index usd_brl gdp_yoy debt_gdp cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset tot_debt_to_ebitda days_to_maturity synthetic_cds_brl
    capture confirm variable A
    if !_rc {
        local oldvars A B C D E F G H I J K L M N O P Q R S T U
        forvalues i = 1/21 {
            local old : word `i' of `oldvars'
            local new : word `i' of `newvars'
            capture rename `old' `new'
        }
    }
    else {
        capture confirm variable v1
        if !_rc {
            forvalues i = 1/21 {
                local new : word `i' of `newvars'
                capture rename v`i' `new'
            }
        }
    }
}

capture confirm string variable spread
if !_rc drop if lower(strtrim(spread)) == "spread"
capture confirm string variable bond_id
if !_rc drop if lower(strtrim(bond_id)) == "bond_id"

capture confirm variable spread
if _rc {
    di as error "Variable spread not found. Re-import Excel with firstrow or check column order."
    describe
    exit 111
}

capture confirm string variable bond_id
if !_rc {
    encode bond_id, gen(bond_id_num)
    drop bond_id
    rename bond_id_num bond_id
}

capture confirm string variable issuer
if !_rc {
    encode issuer, gen(issuer_num)
    drop issuer
    rename issuer_num issuer
}

capture confirm string variable bond_type
if !_rc encode bond_type, gen(bond_type_cat)
else capture rename bond_type bond_type_cat

capture confirm string variable sector
if !_rc encode sector, gen(sector_cat)
else capture rename sector sector_cat

local numvars spread vix fed_3m_forward usd_brl gdp_yoy debt_gdp cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset tot_debt_to_ebitda days_to_maturity synthetic_cds_brl cpi_us_index cpi_br_index
foreach v of local numvars {
    capture confirm variable `v'
    if !_rc capture destring `v', replace ignore(",") force
}

capture confirm numeric variable month_id
if !_rc {
    quietly summarize month_id if !missing(month_id), meanonly
    if r(N)==0 | r(min)<400 | r(max)>1200 drop month_id
}
capture confirm string variable month_id
if !_rc rename month_id month_id_string

capture confirm variable month_id
if _rc {
    gen double month_id = .
    foreach d in month obs_date date month_id_string {
        capture confirm variable `d'
        if !_rc {
            capture confirm numeric variable `d'
            if !_rc {
                quietly summarize `d' if !missing(`d'), meanonly
                if r(N)>0 {
                    if r(max)>30000 replace month_id = mofd(`d' - 21916) if missing(month_id) & !missing(`d')
                    else if r(max)>1000 replace month_id = mofd(`d') if missing(month_id) & !missing(`d')
                    else replace month_id = `d' if missing(month_id) & !missing(`d')
                }
            }
            else {
                tempvar s n dd mm
                gen str60 `s' = strtrim(`d')
                replace `s' = subinstr(`s', char(160), "", .)
                replace `s' = subinstr(`s', char(34), "", .)
                replace `s' = subinstr(`s', "T00:00:00", "", .)
                replace `s' = subinstr(`s', " 00:00:00", "", .)
                destring `s', gen(`n') ignore(", ") force
                replace month_id = mofd(`n' - 21916) if missing(month_id) & !missing(`n') & `n'>30000
                replace month_id = mofd(`n') if missing(month_id) & !missing(`n') & `n'>1000 & `n'<=30000
                replace month_id = `n' if missing(month_id) & !missing(`n') & `n'>400 & `n'<=1200
                gen double `dd' = daily(substr(`s',1,10), "YMD")
                replace `dd' = daily(substr(`s',1,10), "MDY") if missing(`dd')
                replace `dd' = daily(substr(`s',1,10), "DMY") if missing(`dd')
                replace month_id = mofd(`dd') if missing(month_id) & !missing(`dd')
                gen double `mm' = monthly(`s', "YM")
                replace `mm' = monthly(`s', "MY") if missing(`mm')
                replace month_id = `mm' if missing(month_id) & !missing(`mm')
            }
        }
    }
}

format month_id %tm
count if missing(month_id)
if r(N)>0 {
    di as error "month_id could not be constructed. Check month/date variables."
    exit 198
}

sort bond_id month_id
xtset bond_id month_id

preserve
    keep month_id cpi_us_index cpi_br_index
    bysort month_id: keep if _n==1
    sort month_id
    tsset month_id, monthly
    gen double us_cpi_yoy = 100 * (cpi_us_index / L12.cpi_us_index - 1)
    keep month_id us_cpi_yoy
    tempfile cpi_yoy
    save `cpi_yoy', replace
restore

merge m:1 month_id using `cpi_yoy', nogen
label variable us_cpi_yoy "US CPI YoY computed from CPURNSA Index"

gen double fed_3m_real = fed_3m_forward - us_cpi_yoy
label variable fed_3m_real "Fed 3M forward minus US CPI YoY"

gen double rer_usd_brl = usd_brl * cpi_us_index / cpi_br_index
label variable rer_usd_brl "Real USD/BRL = USD/BRL * US CPI / Brazil IPCA"

quietly summarize rer_usd_brl if month_id == tm(2010m12), meanonly
local base_rer = r(mean)
if missing(`base_rer') {
    quietly summarize month_id if !missing(rer_usd_brl), meanonly
    local base_month = r(min)
    quietly summarize rer_usd_brl if month_id == `base_month', meanonly
    local base_rer = r(mean)
}

gen double real_exchange_rate = 100 * rer_usd_brl / `base_rer'
label variable real_exchange_rate "Real USD/BRL index; increase = BRL real depreciation"
save "$db\paper_panel_main_and_robustness_with_realvars.dta", replace

log using "00_constructed_real_variables.log", text replace
describe month_id cpi_us_index cpi_br_index us_cpi_yoy fed_3m_real rer_usd_brl real_exchange_rate
summarize cpi_us_index cpi_br_index us_cpi_yoy fed_3m_forward fed_3m_real usd_brl rer_usd_brl real_exchange_rate
count if missing(us_cpi_yoy)
count if missing(fed_3m_real)
count if missing(real_exchange_rate)
correlate usd_brl real_exchange_rate if !missing(usd_brl, real_exchange_rate)
log close

preserve
    keep month_id fed_3m_forward usd_brl debt_gdp synthetic_cds_brl
    bysort month_id: keep if _n==1
    sort month_id
    tsset month_id, monthly
    gen D_fed_3m_forward    = D.fed_3m_forward
    gen D_usd_brl           = D.usd_brl
    gen D_debt_gdp          = D.debt_gdp
    gen D_synthetic_cds_brl = D.synthetic_cds_brl
    keep month_id D_fed_3m_forward D_usd_brl D_debt_gdp D_synthetic_cds_brl
    tempfile macro_diffs
    save `macro_diffs', replace
restore
merge m:1 month_id using `macro_diffs', nogen
sort bond_id month_id
xtset bond_id month_id

local firm_controls cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset tot_debt_to_ebitda days_to_maturity
local base_x vix fed_3m_forward usd_brl gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl
local keep_base vix fed_3m_forward usd_brl gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl
local keep_diff vix D_fed_3m_forward D_usd_brl gdp_yoy D_debt_gdp `firm_controls' synthetic_cds_brl
local keep_lag L_spread `keep_base'
local keep_rer vix fed_3m_forward real_exchange_rate gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl
local keep_fedr vix fed_3m_real usd_brl gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl
local keep_both vix fed_3m_real real_exchange_rate gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl

capture log close
log using "01_main_estimation_and_martin_robustness.log", text replace

xtreg spread `base_x' i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE
xtreg spread `base_x' i.bond_type_cat i.sector_cat, re cluster(issuer)
estimates store RE
xtreg spread `base_x' i.bond_type_cat i.sector_cat, fe
estimates store FE_plain
xtreg spread `base_x' i.bond_type_cat i.sector_cat, re
estimates store RE_plain
hausman FE_plain RE_plain, sigmamore

xtreg spread `base_x' i.bond_type_cat i.sector_cat, fe
capture noisily ssc install xttest3, replace
capture noisily xttest3
capture noisily ssc install xtcsd, replace
capture noisily xtcsd, pesaran abs
capture which xtserial
if !_rc capture noisily xtserial spread `base_x'

xtreg spread vix D_fed_3m_forward D_usd_brl gdp_yoy D_debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_UR
capture drop L_spread
gen L_spread = L.spread
xtreg spread L_spread `base_x' i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_LAG
xtpcse spread `base_x' i.bond_type_cat i.sector_cat, pairwise
estimates store PCSE
capture noisily ssc install xtscc, replace
capture drop t_dk
egen t_dk = group(month_id)
xtset bond_id t_dk
xtscc spread `base_x', fe
estimates store DK
xtset bond_id month_id

xtreg spread vix fed_3m_forward real_exchange_rate gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_RER
xtreg spread vix fed_3m_real usd_brl gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_FEDREAL
xtreg spread vix fed_3m_real real_exchange_rate gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_REALS

xtreg spread vix fed_3m_forward usd_brl gdp_yoy `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_NODEBT
xtreg spread vix fed_3m_forward usd_brl debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_NOGDP
xtreg spread vix fed_3m_forward gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_NOFX
xtreg spread vix fed_3m_forward `firm_controls' synthetic_cds_brl i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_NOSOVMACRO

capture noisily ssc install outreg2, replace
outreg2 [FE] using "results_FE.docx", replace dec(4) label ctitle("Fixed Effects, clustered by issuer") addtext("N bonds", e(N_g), "Observations", e(N)) addstat("R-sq within", e(r2_w)) nocons
outreg2 [RE] using "results_RE.docx", replace dec(4) label ctitle("Random Effects, appendix") nocons
outreg2 [FE_plain RE_plain] using "FE_RE_comparison.docx", replace dec(4) label ctitle("FE", "RE") nocons

outreg2 [FE] using "Table3_chapter5_robustness.docx", replace dec(4) label ctitle("FE baseline") keep(`keep_base') nocons
outreg2 [PCSE] using "Table3_chapter5_robustness.docx", append dec(4) label ctitle("PCSE") keep(`keep_base') nocons
outreg2 [DK] using "Table3_chapter5_robustness.docx", append dec(4) label ctitle("Driscoll-Kraay") keep(`keep_base') nocons

outreg2 [FE] using "Table4_real_variable_robustness.docx", replace dec(4) label ctitle("Baseline nominal") keep(`keep_base') nocons
outreg2 [FE_RER] using "Table4_real_variable_robustness.docx", append dec(4) label ctitle("Real FX") keep(`keep_rer') nocons
outreg2 [FE_FEDREAL] using "Table4_real_variable_robustness.docx", append dec(4) label ctitle("Real Fed 3M") keep(`keep_fedr') nocons
outreg2 [FE_REALS] using "Table4_real_variable_robustness.docx", append dec(4) label ctitle("Real FX + Real Fed") keep(`keep_both') nocons

outreg2 [FE] using "Table5_sovereign_exclusion_robustness.docx", replace dec(4) label ctitle("Baseline") keep(`keep_base') nocons
outreg2 [FE_NODEBT] using "Table5_sovereign_exclusion_robustness.docx", append dec(4) label ctitle("No debt/GDP") keep(vix fed_3m_forward usd_brl gdp_yoy `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOGDP] using "Table5_sovereign_exclusion_robustness.docx", append dec(4) label ctitle("No GDP growth") keep(vix fed_3m_forward usd_brl debt_gdp `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOFX] using "Table5_sovereign_exclusion_robustness.docx", append dec(4) label ctitle("No FX") keep(vix fed_3m_forward gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOSOVMACRO] using "Table5_sovereign_exclusion_robustness.docx", append dec(4) label ctitle("No debt/GDP, GDP, FX") keep(vix fed_3m_forward `firm_controls' synthetic_cds_brl) nocons

outreg2 [FE] using "TableA_full_robustness.docx", replace dec(4) label ctitle("FE") keep(`keep_base') nocons
outreg2 [FE_UR] using "TableA_full_robustness.docx", append dec(4) label ctitle("FE macro diffs") keep(`keep_diff') nocons
outreg2 [FE_LAG] using "TableA_full_robustness.docx", append dec(4) label ctitle("FE dynamic") keep(`keep_lag') nocons
outreg2 [PCSE] using "TableA_full_robustness.docx", append dec(4) label ctitle("PCSE") keep(`keep_base') nocons
outreg2 [DK] using "TableA_full_robustness.docx", append dec(4) label ctitle("Driscoll-Kraay") keep(`keep_base') nocons
outreg2 [FE_NODEBT] using "TableA_full_robustness.docx", append dec(4) label ctitle("No debt/GDP") keep(vix fed_3m_forward usd_brl gdp_yoy `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOGDP] using "TableA_full_robustness.docx", append dec(4) label ctitle("No GDP") keep(vix fed_3m_forward usd_brl debt_gdp `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOFX] using "TableA_full_robustness.docx", append dec(4) label ctitle("No FX") keep(vix fed_3m_forward gdp_yoy debt_gdp `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_NOSOVMACRO] using "TableA_full_robustness.docx", append dec(4) label ctitle("No debt/GDP, GDP, FX") keep(vix fed_3m_forward `firm_controls' synthetic_cds_brl) nocons
outreg2 [FE_RER] using "TableA_full_robustness.docx", append dec(4) label ctitle("Real FX") keep(`keep_rer') nocons
outreg2 [FE_FEDREAL] using "TableA_full_robustness.docx", append dec(4) label ctitle("Real Fed") keep(`keep_fedr') nocons
outreg2 [FE_REALS] using "TableA_full_robustness.docx", append dec(4) label ctitle("Real FX + Real Fed") keep(`keep_both') nocons

capture noisily ssc install coefplot, replace
coefplot FE, keep(`keep_base') xline(0) title("Baseline FE coefficients") ysize(4) xsize(6)
graph export "coefplot_FE.png", replace

log close
display "Completed main estimation and Martin-requested robustness checks."
display "Outputs are saved in: $out"
display "Enhanced dataset saved as: $db\paper_panel_main_and_robustness_with_realvars.dta"
