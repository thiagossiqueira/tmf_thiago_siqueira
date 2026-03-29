import pandas as pd
from src.config import CONFIG

def filter_corporate_universe(df: pd.DataFrame, inflation_linked: str = "N", log=None) -> pd.DataFrame:
    """
    Aplica os filtros padrão para selecionar o universo de bonds corporativos.
    Permite registrar os passos em um log opcional.
    """

    print_fn = (
        (lambda *args, **kwargs: print(*args, **kwargs))
        if log is None else
        (lambda *args, **kwargs: print(*args, **kwargs, file=log))
    )

    df = df.copy()
    print_fn(f"🔍 Inicial: {len(df)} linhas")

    # Filtros básicos
    df = df[~df['CLASSIFICATION_LEVEL_4_NAME'].str.startswith("Government", na=False)]
    print_fn(f"➡ Após remover 'Government': {len(df)}")

    df = df[~df['industry_sector'].isin(['Financial'])]
    print_fn(f"➡ Após remover 'Financial': {len(df)}")

    df = df[df['CPN_TYP'].isin(['FIXED'])]
    print_fn(f"➡ Após filtrar CPN_TYP='FIXED': {len(df)}")

    df = df[df['CRNCY'].isin(['BRL'])]
    print_fn(f"➡ Após filtrar CRNCY='BRL': {len(df)}")

    # Filtro por indexação à inflação
    df["INFLATION_LINKED_INDICATOR"] = (
        df["INFLATION_LINKED_INDICATOR"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    unique_vals = df["INFLATION_LINKED_INDICATOR"].unique()
    print_fn(f"🧪 Valores únicos normalizados em INFLATION_LINKED_INDICATOR: {unique_vals}")

    df = df[df["INFLATION_LINKED_INDICATOR"] == inflation_linked.strip().upper()]
    print_fn(f"➡ Após filtrar INFLATION_LINKED_INDICATOR={inflation_linked}: {len(df)}")

    # TOT_DEBT_TO_EBITDA válido
    df['TOT_DEBT_TO_EBITDA'] = pd.to_numeric(df['TOT_DEBT_TO_EBITDA'], errors='coerce')
    print_fn(f"➡ Após conversão de TOT_DEBT_TO_EBITDA (com NaN): {df['TOT_DEBT_TO_EBITDA'].isna().sum()} NaNs")

    df = df[df['TOT_DEBT_TO_EBITDA'].notna()]
    print_fn(f"➡ Após remover TOT_DEBT_TO_EBITDA nulos: {len(df)}")

    df["MATURITY"] = pd.to_datetime(df["MATURITY"], errors='coerce')

    return df


def filter_government_universe(df: pd.DataFrame, inflation_linked: str = "N", bond_type: str = None, log=None) -> pd.DataFrame:
    print_fn = (lambda *args, **kwargs: print(*args, **kwargs)) if log is None else (lambda *args, **kwargs: print(*args, **kwargs, file=log))

    df = df.copy()
    print_fn(f"🔍 Inicial: {len(df)} linhas")

    # Mantém apenas títulos BRL e FIXED
    df = df[df["CRNCY"] == "BRL"]
    df = df[df["CPN_TYP"] == "FIXED"]
    print_fn(f"➡ Após filtrar CPN_TYP='FIXED' e CRNCY='BRL': {len(df)}")

    # Normaliza indicador de inflação
    df["INFLATION_LINKED_INDICATOR"] = df["INFLATION_LINKED_INDICATOR"].astype(str).str.strip().str.upper()
    df = df[df["INFLATION_LINKED_INDICATOR"] == inflation_linked.strip().upper()]
    print_fn(f"➡ Após filtrar INFLATION_LINKED_INDICATOR={inflation_linked}: {len(df)}")

    # Se bond_type for especificado (LTN, NTNF, NTNB)
    if bond_type:
        df = df[df["SECURITY_TYP"].str.upper() == bond_type.upper()]
        print_fn(f"➡ Após filtrar SECURITY_TYP={bond_type}: {len(df)}")

    df["MATURITY"] = pd.to_datetime(df["MATURITY"], errors="coerce")
    return df
def anomaly_filtering_results(df: pd.DataFrame, is_ltn: bool = False) -> pd.DataFrame:
    """
    Aplica filtros para eliminar observações com yields zerados ou spreads anômalos.
    Inclui prints de diagnóstico mostrando o impacto de cada regra.
    Usa range em p.p. (±10) para LTNs e em bps (±1000) para os demais.
    """

    if df is None or df.empty:
        print("⚠️ [ANOMALY FILTER] DataFrame vazio — nada a filtrar.")
        return df

    df = df.copy()
    total_inicial = len(df)
    print(f"\n📊 [ANOMALY FILTER] Início: {total_inicial} observações")

    # Remover yields zerados
    df_yield_zero = df[df["YAS_BOND_YLD"] == 0]
    if not df_yield_zero.empty:
        print(f"➡️ Removendo {len(df_yield_zero)} registros com YAS_BOND_YLD = 0")
    df = df[df["YAS_BOND_YLD"] != 0]

    # Range dinâmico
    if is_ltn:
        low, high, unidade = -10, 10, "p.p."
    else:
        low, high, unidade = -1000, 1000, "bps"

    # Filtro de spreads anômalos
    total_pre_spread = len(df)
    mask_valid = (df["SPREAD"] >= low) & (df["SPREAD"] <= high)
    removidos_spread = total_pre_spread - mask_valid.sum()

    print(f"➡️ Removendo {removidos_spread} registros com SPREAD fora de [{low}, {high}] {unidade}")
    df = df[mask_valid]

    total_final = len(df)
    print(f"✅ [ANOMALY FILTER] Final: {total_final} observações válidas (de {total_inicial} iniciais)\n")

    return df

def apply_custom_filters(df: pd.DataFrame, inflation: str, exclude_gov: bool, exclude_fin: bool,
                         cpns: list) -> pd.DataFrame:
    df = df.copy()

    if exclude_gov:
        df = df[~df["CLASSIFICATION_LEVEL_4_NAME"].str.startswith("Government", na=False)]

    if exclude_fin:
        df = df[~df["industry_sector"].isin(["Financial"])]

    if cpns:
        df = df[df["CPN_TYP"].isin(cpns)]

    df["INFLATION_LINKED_INDICATOR"] = df["INFLATION_LINKED_INDICATOR"].astype(str).str.strip().str.upper()
    df = df[df["INFLATION_LINKED_INDICATOR"] == inflation.strip().upper()]

    return df


def load_raw_corp_data() -> pd.DataFrame:
    """
    Carrega a base de dados de bonds corporativos sem aplicar filtros.
    """
    df = pd.read_excel(CONFIG["CORP_PATH"], sheet_name="db_values_only")
    df["id"] = df["id"].astype(str).str.strip()
    return df

def filter_government_universe(
    df: pd.DataFrame,
    inflation_linked: str = "N",
    bond_type: str = None,
    log=None
) -> pd.DataFrame:
    """
    Filtro de universo para títulos soberanos (govt).

    - LTNs: zero-coupon, sem restrição por CRNCY nem FIXED.
    - NTNF/NTNB: mantém cupom fixo e BRL.
    """
    print_fn = (
        (lambda *args, **kwargs: print(*args, **kwargs))
        if log is None else
        (lambda *args, **kwargs: print(*args, **kwargs, file=log))
    )

    df = df.copy()
    print_fn(f"🔍 Inicial: {len(df)} linhas")

    bond_type = (bond_type or "").upper()

    # =======================================================
    # 🎯 Filtro específico por tipo de bond
    # =======================================================
    if bond_type == "LTN":
        # Zero-coupon: CPN_TYP deve indicar ausência de cupom
        zero_like = ["ZERO", "ZERO COUPON" ,"DISCOUNT", "ZC", "NONE", "N/A", "NAN", ""]
        df["CPN_TYP"] = df["CPN_TYP"].astype(str).str.upper().str.strip()
        df = df[df["CPN_TYP"].isin(zero_like)]

        # Opcional: confirmar se SECURITY_TYP está coerente
        if "SECURITY_TYP" in df.columns:
            df = df[df["SECURITY_TYP"].astype(str).str.upper().eq("LTN")]

        print_fn(f"➡ Após filtrar ZERO-COUPON (LTN): {len(df)}")

    else:
        # NTN-F e NTN-B → fixos, BRL
        df = df[df["CPN_TYP"].astype(str).str.upper().eq("FIXED")]
        df = df[df["CRNCY"].astype(str).str.upper().eq("BRL")]
        print_fn(f"➡ Após CPN_TYP='FIXED' & CRNCY='BRL': {len(df)}")

    # =======================================================
    # 💨 Filtro por indexação à inflação
    # =======================================================
    if "INFLATION_LINKED_INDICATOR" in df.columns:
        df["INFLATION_LINKED_INDICATOR"] = (
            df["INFLATION_LINKED_INDICATOR"].astype(str).str.strip().str.upper()
        )
        df = df[df["INFLATION_LINKED_INDICATOR"] == inflation_linked.strip().upper()]
        print_fn(f"➡ Após INFLATION_LINKED_INDICATOR={inflation_linked}: {len(df)}")

    # =======================================================
    # 📈 Filtro por SECURITY_TYP (se existir)
    # =======================================================
    if "SECURITY_TYP" in df.columns and bond_type:
        df["SECURITY_TYP"] = df["SECURITY_TYP"].astype(str).str.upper().str.strip()
        df = df[df["SECURITY_TYP"] == bond_type]
        print_fn(f"➡ Após SECURITY_TYP={bond_type}: {len(df)}")

    # =======================================================
    # 🗓️ Ajuste de datas
    # =======================================================
    if "MATURITY" in df.columns:
        df["MATURITY"] = pd.to_datetime(df["MATURITY"], errors="coerce")

    return df
