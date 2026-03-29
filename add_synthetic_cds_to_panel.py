import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
from src.config import CONFIG

# Cargar panel y superficie CDS-BRL
panel = pd.read_excel(CONFIG["PANEL_DATA_PATH"])
cds_surface = pd.read_excel(CONFIG["SYNTHETIC_CDS_PATH"])

# Usar la última curva (fecha más reciente) de la superficie CDS-BRL
latest_row = cds_surface.iloc[-1].dropna()

# Extraer solo columnas que sean tenores válidos (excluye OBS_DATE)
tenor_labels = [x for x in latest_row.index if "year" in x or "month" in x]
tenor_values = np.array([
    float(x.replace("-year", "").replace("month", "").split("-")[0])
    for x in tenor_labels
])
spreads = latest_row[tenor_labels].values / 100  # convertir a porcentaje

# ---- Ajuste NSS directo (sin optimización de precios) ----
def nss_func(t, beta0, beta1, beta2, tau1, tau2):
    t = np.maximum(t, 1e-6)
    term1 = (1 - np.exp(-t / tau1)) / (t / tau1)
    term2 = term1 - np.exp(-t / tau1)
    term3 = ((1 - np.exp(-t / tau2)) / (t / tau2)) - np.exp(-t / tau2)
    return beta0 + beta1 * term1 + beta2 * term2 + 0.0 * term3  # forma simplificada

# Ajustar parámetros beta de NSS directamente sobre la curva de spreads
betas, _ = curve_fit(nss_func, tenor_values, spreads, maxfev=10000)

# Calcular spreads sintéticos (en bps) interpolados para cada bono del panel
panel["Synthetic_CDS_BRL"] = nss_func(panel["days_to_maturity"], *betas) * 100

# Guardar nuevo archivo con la columna agregada
panel.to_excel(CONFIG["PANEL_DATA_OUTPUT_PATH"], index=False)
print(f"✅ Archivo actualizado con curva NSS: {CONFIG['PANEL_DATA_OUTPUT_PATH']}")
