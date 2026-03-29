# README 

## Modelo de Spread para Bonos Corporativos

Proyecto modular para el cálculo y visualización de los spreads entre bonos corporativos brasileños y la curva DI interpolada, utilizando datos históricos punto por punto. Incluye integración con **Flask** para visualizar los resultados en el navegador.

**Visualiza la app en producción aquí**: [tsiqueira4.pythonanywhere.com](https://tsiqueira4.pythonanywhere.com/)

### Estructura del Proyecto
```
spread-model/
├── Makefile                     # Atajos para ejecutar, testear e instalar el proyecto
├── WSGI.py                      # Archivo de configuración WSGI para despliegue en PythonAnywhere
├── main.py                      # Genera los datos y visualizaciones
├── synthetic_cds_brl.py         # Genera la superficie CDS-BRL (riesgo país en reales)
├── add_synthetic_cds_to_panel.py # Agrega la columna Synthetic_CDS_BRL al panel corporativo
├── app.py                       # Aplicación Flask para visualización web
├── pyproject.toml               # Configuración del proyecto Python
├── requirements.txt             # Dependencias
├── .gitignore                   # Archivos ignorados por Git
├── post-pull.sh                 # Script de actualización post-pull (instalación + generación de gráficos)
├── README.md
│
├── src/                         # Código fuente modular (instalado vía setup)
│   ├── calendars/               # Cálculo de fechas hábiles
│   │   ├── holidays
│   │   │   ├── brazil
│   │   │   ├── libor
│   │   │   ├── us
│   │   │   ├── utils
│   │   │   └── factory.py
│   │   ├── custom_date_types.py
│   │   └── daycounts.py
│   ├── finmath/                 # Funciones financieras
│   │   ├── brazilian_bonds
│   │   │   └── corporate_bonds.py
│   │   ├── SwapCurve
│   │   │   ├── Holidays
│   │   │   └── SwapCurve.py
│   │   └── termstructure
│   │       └── curve_models.py
│   ├── utils/                   # I/O, interpolación, gráficos
│   │   ├── file_io.py
│   │   ├── filters.py
│   │   ├── interpolation.py
│   │   └── plotting.py
│   ├── config.py                # Parámetros globales y rutas
│   └── core/                    # Cálculo de ventanas y spreads
│       ├── spread_calculator.py
│       └── windowing.py
│
│
├── datos_y_modelos/            # Archivos de datos (no incluidos si son privados)
│   ├── db/                     # Base de datos histórica de curvas DI y precios de bonos
│   │   ├── brazil_domestic_corp_bonds
│   │   ├── brazil_macroeconomic_data
│   │   ├── id_x_ipca_spread_futures
│   │   ├── one-day_interbank_deposit_futures_contract_di
│   │   ├── output_calculated_spreads
│   │   └── output_vecm_data
│   ├── scripts/
│   │   └── painel_spreads_model.do
│   └── Domestic/
│       ├── domestic_sovereign_curve_brazil.xlsx
│       └── universo_brazil_deb_des.xlsx     # Metadata de bonos corporativos brasileños
│
├── static/            # Visualizaciones exportadas en HTML
│   ├── css/                   
│   │   ├── main.css
│   │   ├── style.css
│   │   ├── summary.css  
│   │   └── tables.css 
│   ├── js/                     
│   │   ├── datatableFilter.js
│   │   ├── filter_controls.js
│   │   ├── spread_table.js
│   │   └── exportTable.js
│   ├── spread_surface.html
│   └── summary_table.html
├── templates/                   # Plantillas HTML para la app Flask
│   ├── shared
│   │   ├── base.html
│   │   └── nav_bar.html         # where I manage links from the landing page 
│   ├── filters.html
│   ├── index.html
│   ├── ipca_summary_full.html
│   ├── ipca_summary_iframe.html
│   ├── spread_embed.html
│   ├── spread_iframe.html
│   ├── summary_ful.html
│   └── summary_iframe.html
│
├── .github                      # Configuración de integración continua (CI)
│   └── workflows/
│       └── pytest.yml           # Workflow de GitHub Actions para ejecutar pytest automáticamente
│
├── tests/                       # Pruebas unitarias y de integración (pytest)
│   ├── conftest.py              # é extremamente útil em testes de integração pq testes de integração geralmente precisam de dados compartilhados, acesso a módulos fora do diretório padrão, configurações globais, etc.
│   ├── manual_validation.py     # Validaciones manuales, pruebas exploratorias           
│   ├── test_interpolation.py    # Pruebas unitarias para interpolación de la curva DI
│   ├── test_di_surface_integrity.py  # Verifica que los datos cargados coincidan con lo esperado
│   ├── test_spread_calculator.py
│   ├── test_interpolation.py
│   ├── test_spread_calculator.py     # Testea cálculo de spreads vs curva DI interpolada
│   ├── test_integration_pipeline.py  # Prueba de extremo a extremo: carga, interpolación, verificación
└── data/
    ├── skipped_yields.csv       # Observaciones descartadas durante los cálculos
    └── visualizaciones/         # Salidas adicionales opcionales (tablas, figuras, etc.)

```

### Instalación
Requisitos:
- Python >= 3.8

Instalar el proyecto en modo desarrollo:
```bash
pip install -e .
```

Instalar también Flask:
```bash
pip install flask
```

---

### Ejecución
#### Production: Para generar los datos y los gráficos HTML:
```bash
run https://www.pythonanywhere.com/user/tsiqueira4/consoles/41338075/
17:20 ~ $ ls
README.txt  light_spread_repo_for_py_anywhere
17:20 ~ $ cd light_spread_repo_for_py_anywhere/
17:20 ~ $ ls
README.txt  light_spread_repo_for_py_anywhere
17:20 ~ $ cd light_spread_repo_for_py_anywhere/
17:21 ~/light_spread_repo_for_py_anywhere (master)$ ls
Makefile   __pycache__  data             main.py       pyproject.toml    routes           src     templates  wsgi.py
README.md  app.py       datos_y_modelos  post-pull.sh  requirements.txt  sparse-checkout  static  tests
17:21 ~/light_spread_repo_for_py_anywhere (master) $ chmod +x post-pull.sh 
17:21 ~/light_spread_repo_for_py_anywhere (master)$ ./post-pull.sh 
```

Esto generará los archivos:
- `static/spread_surface.html`
- `static/summary_table.html`

#### Para generar los datos y los gráficos HTML:
```bash
python main.py
```

Esto generará los archivos:
- `static/spread_surface.html`
- `static/summary_table.html`

#### Para visualizar en el navegador vía Flask:
```bash
python app.py
```
Abrir el navegador en `http://127.0.0.1:5000`

---

### Pruebas
Ejecutar pruebas con `pytest`:
```bash
pytest
```


### Script de Pós-pull (actualización automática)
Después de hacer `git pull`, ejecuta:
```bash
./post-pull.sh
```
Este script:
- Activa el entorno virtual si existe
- Reinstala el proyecto (`pip install -e .`)
- Ejecuta `main.py` para actualizar las visualizaciones

Puedes hacerlo ejecutable con:
```bash
chmod +x post-pull.sh
```


---

### Visualizaciones
- Gráfico 3D de spreads observados (Plotly Surface)
- Tabla comparativa de yields (bono vs curva DI interpolada)

---

### Referencias externas útiles

Para análisis y consulta adicional sobre curvas de interés y títulos del gobierno en Brasil:

- **Tasas de títulos públicos (ANBIMA)**  
  Cálculo diario de tasas de interés de títulos públicos brasileños.  
  [https://www.anbima.com.br/pt_br/informar/taxas-de-titulos-publicos.htm](https://www.anbima.com.br/pt_br/informar/taxas-de-titulos-publicos.htm)

- **Curva de tasas de interés – Gráficos actualizados**  
  Visualizaciones recientes de la curva de tasas de interés en Brasil, útiles para análisis macroeconómico.  
  [https://clubedospoupadores.com/curva-de-juros](https://clubedospoupadores.com/curva-de-juros)

- **Spreads de títulos públicos brasileños**  
  Comparación entre distintas curvas de rendimiento y spreads sobre la curva base.  
  [https://clubedospoupadores.com/curva-de-juros/spread](https://clubedospoupadores.com/curva-de-juros/spread)

- **Curva de tasas – Inflación implícita**  
  Estimación de la inflación implícita derivada de la diferencia entre curvas nominales y reales.  
  [https://clubedospoupadores.com/curva-de-juros/inflacao](https://clubedospoupadores.com/curva-de-juros/inflacao)
---


### Build y Metadatos
Ver `pyproject.toml` para detalles de empaquetado y configuración del proyecto.

---

### Archivos Ignorados
El proyecto incluye `.gitignore` para evitar versionar:
- Datos de salida (`data/`)
- Entornos virtuales y cachés
- Artefactos de build e IDEs

---

### Autor
Thiago Siqueira – [t_siqueira@hotmail.com](mailto:tsiqueira@hotmail.com)

Para dudas o contribuciones, no dudes en abrir un issue o ponerte en contacto.