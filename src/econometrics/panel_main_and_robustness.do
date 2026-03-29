clear all
capture log close
set more off
version 15

global base "C:\Users\tsiqueira4\OneDrive - Bloomberg LP\Desktop\Tesis\TFM_Maestria_Economia_Siqueira_Thiago_Diciembre_2025\datos_y_modelos\db\econometrics_db"
cd "$base"
use "panel_main_and_robustness", clear

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
if !_rc {
    encode bond_type, gen(bond_type_cat)
}
else {
    capture rename bond_type bond_type_cat
}

capture confirm string variable sector
if !_rc {
    encode sector, gen(sector_cat)
}
else {
    capture rename sector sector_cat
}

destring spread vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl, ///
         replace ignore(",") force

capture confirm variable month_id
if _rc {
    capture confirm string variable month
    if !_rc {
        gen __daily = daily(substr(month,1,10),"YMD")
        gen month_id = mofd(__daily)
        drop __daily
    }
    else {
        capture confirm numeric variable month
        if !_rc {
            gen month_id = mofd(month)
        }
        else {
            di as error "No se encontro month_id ni una variable month utilizable."
            exit 198
        }
    }
}
format month_id %tm

sort bond_id month_id
xtset bond_id month_id

tempfile panel_main
save `panel_main', replace

preserve
keep month_id vix fed_3m_forward usd_brl gdp_yoy debt_gdp synthetic_cds_brl
bys month_id: keep if _n==1
sort month_id
tsset month_id, monthly

local L = 12

capture log close
log using "00_unitroot_macro_tests.log", text replace
display "=================================================="
display "ADF TESTS FOR COMMON MONTHLY MACRO SERIES"
display "=================================================="

dfuller vix, lags(`L')
dfuller fed_3m_forward, lags(`L')
dfuller usd_brl, lags(`L')
dfuller gdp_yoy, lags(`L')
dfuller debt_gdp, lags(`L')
dfuller synthetic_cds_brl, lags(`L')

display "=================================================="
display "PP TESTS (ROBUSTNESS)"
display "=================================================="

pperron vix, lags(`L')
pperron fed_3m_forward, lags(`L')
pperron usd_brl, lags(`L')
pperron gdp_yoy, lags(`L')
pperron debt_gdp, lags(`L')
pperron synthetic_cds_brl, lags(`L')

log close

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

capture log close
log using "01_main_estimation_and_diagnostics.log", text replace

*---------------------------------------------------
* 5.1) FE baseline (main model)
*---------------------------------------------------
xtreg spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE

*---------------------------------------------------
* 5.2) RE baseline
*---------------------------------------------------
xtreg spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, re cluster(issuer)
estimates store RE

******************************************************
* 6) HAUSMAN TEST (classical FE vs RE, unclustered)
******************************************************

xtreg spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, fe
estimates store FE_plain

xtreg spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, re
estimates store RE_plain

hausman FE_plain RE_plain, sigmamore

******************************************************
* 7) DIAGNOSTICS ON BASELINE FE
******************************************************

xtreg spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, fe

capture noisily ssc install xttest3, replace
capture noisily xttest3

capture noisily ssc install xtcsd, replace
capture noisily xtcsd, pesaran abs

capture which xtserial
if !_rc {
    capture noisily xtserial spread ///
        vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
        cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
        tot_debt_to_ebitda days_to_maturity synthetic_cds_brl
}
else {
    di as txt "Note: xtserial is not installed; Wooldridge serial-correlation test skipped."
}

******************************************************
* 8) UNIT-ROOT-AWARE FE ALTERNATIVE
******************************************************

xtreg spread ///
      vix D_fed_3m_forward D_usd_brl gdp_yoy D_debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_UR

******************************************************
* 9) ROBUSTNESS CHECKS
******************************************************

sort bond_id month_id
xtset bond_id month_id

capture drop L_spread
gen L_spread = L.spread

xtreg spread L_spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
      i.bond_type_cat i.sector_cat, fe cluster(issuer)
estimates store FE_LAG

xtpcse spread ///
       vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
       cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
       tot_debt_to_ebitda days_to_maturity synthetic_cds_brl ///
       i.bond_type_cat i.sector_cat, pairwise
estimates store PCSE

capture noisily ssc install xtscc, replace
capture drop t_dk
egen t_dk = group(month_id)

sort bond_id t_dk
xtset bond_id t_dk

xtscc spread ///
      vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
      cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
      tot_debt_to_ebitda days_to_maturity synthetic_cds_brl, fe
estimates store DK

sort bond_id month_id
xtset bond_id month_id

******************************************************
* 10) EXPORT TABLES
******************************************************

capture noisily ssc install outreg2, replace

*---------------------------------------------------
* 10.1) Main model tables
*---------------------------------------------------
outreg2 [FE] using "results_FE.docx", ///
    replace dec(4) label ///
    ctitle("Fixed Effects (Robust Clustered by Issuer)") ///
    addtext("N bonds", e(N_g), "Observations", e(N)) ///
    addstat("R-sq (within)", e(r2_w)) nocons

outreg2 [RE] using "results_RE.docx", ///
    replace dec(4) label ///
    ctitle("Random Effects (Appendix)") nocons

outreg2 [FE_plain RE_plain] using "FE_RE_comparison.docx", ///
    replace dec(4) label ctitle("FE","RE") nocons

*---------------------------------------------------
* 10.2) Compact robustness table (Chapter 5)
*      Safer approach: one model at a time with append
*---------------------------------------------------
outreg2 [FE] using "Table3_chapter5_robustness.docx", ///
    replace dec(4) label ///
    ctitle("FE baseline") ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [FE_UR] using "Table3_chapter5_robustness.docx", ///
    append dec(4) label ///
    ctitle("FE macro diffs") ///
    keep(vix D_fed_3m_forward D_usd_brl gdp_yoy D_debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [FE_LAG] using "Table3_chapter5_robustness.docx", ///
    append dec(4) label ///
    ctitle("FE dynamic") ///
    keep(L_spread vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

*---------------------------------------------------
* 10.3) Full robustness table (Annex)
*      Safer approach: one model at a time with append
*---------------------------------------------------
outreg2 [FE] using "TableA_full_robustness.docx", ///
    replace dec(4) label ///
    ctitle("FE") ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [FE_UR] using "TableA_full_robustness.docx", ///
    append dec(4) label ///
    ctitle("FE-UR") ///
    keep(vix D_fed_3m_forward D_usd_brl gdp_yoy D_debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [FE_LAG] using "TableA_full_robustness.docx", ///
    append dec(4) label ///
    ctitle("FE-LAG") ///
    keep(L_spread vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [PCSE] using "TableA_full_robustness.docx", ///
    append dec(4) label ///
    ctitle("PCSE") ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

outreg2 [DK] using "TableA_full_robustness.docx", ///
    append dec(4) label ///
    ctitle("DK") ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    nocons

******************************************************
* 11) COEFFICIENT PLOT (baseline FE)
******************************************************
capture noisily ssc install coefplot, replace

coefplot FE, ///
    keep(vix fed_3m_forward usd_brl gdp_yoy debt_gdp ///
         cf_cash_oper_to_tot_asset amount_issued_to_bs_tot_asset ///
         tot_debt_to_ebitda days_to_maturity synthetic_cds_brl) ///
    xline(0) ///
    title("Coeficientes del modelo FE por tipo de factor") ///
    ysize(4) xsize(6)

graph export "coefplot_FE.png", replace

capture log close

display "Main estimation, diagnostics, unit-root-aware FE, and robustness tables completed successfully."
