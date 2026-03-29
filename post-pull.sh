#!/bin/bash
echo "🔁 Iniciando post-pull automático..."

# Detecta ambiente
if [[ "$HOME" == "/home/tsiqueira4" ]]; then
    echo "🧠 Ambiente detectado: PythonAnywhere (produção)"
    ON_PYTHONANYWHERE=true
else
    echo "🧠 Ambiente detectado: Local (desenvolvimento)"
    ON_PYTHONANYWHERE=false
fi

# Garante que estamos no branch master e atualiza origin
echo "📂 Sincronizando repositório..."
git fetch origin master
git checkout master

# Reconfigura sparse-checkout para garantir que o filtro é atualizado
echo "📂 Configurando sparse-checkout..."
git config core.sparseCheckout true
mkdir -p .git/info
cat > .git/info/sparse-checkout <<EOF
/*
!datos_y_modelos/db/one-day_interbank_deposit_futures_contract_di/hist_di_curve_contracts_db.xlsx
!datos_y_modelos/db/brazil_domestic_equities/*
!datos_y_modelos/db/brazil_domestic_corp_bonds/brazil_debentures_universe/Resultado/resultado_parte*
EOF

echo "🧹 Aplicando filtro do sparse-checkout..."
git read-tree -mu HEAD

# Pull forçado para garantir atualização de arquivos rastreados
echo "📥 Executando git pull origin master..."
git pull --rebase --autostash origin master

# Ativa venv local se aplicável
if [ "$ON_PYTHONANYWHERE" = false ] && [ -d "venv" ]; then
    echo "📦 Ativando ambiente virtual local..."
    source venv/bin/activate
fi

# Instala dependências
echo "📦 Instalando dependências..."
pip install -e . --quiet
pip install -r requirements.txt --quiet

# Roda cálculos principais
echo "📊 Executando main.py..."
python main.py

# Gera superfície CDS-BRL sintética
echo "💡 Generando superficie CDS-BRL (riesgo Brasil sintético)..."
if [ -f "synthetic_cds_brl.py" ]; then
  python synthetic_cds_brl.py
  echo "✅ synthetic_cds_brl.py ejecutado con éxito."
else
  echo "⚠️ Archivo synthetic_cds_brl.py no encontrado, omitiendo generación del CDS-BRL."
fi

# Agrega columna Synthetic_CDS_BRL al panel corporativo
echo "📈 Agregando columna Synthetic_CDS_BRL al panel de bonos corporativos..."
if [ -f "add_synthetic_cds_to_panel.py" ]; then
  python add_synthetic_cds_to_panel.py
  echo "✅ add_synthetic_cds_to_panel.py ejecutado con éxito."
else
  echo "⚠️ Archivo add_synthetic_cds_to_panel.py no encontrado, omitiendo actualización del panel."
fi

# Reinicia app
if [ "$ON_PYTHONANYWHERE" = true ]; then
    echo "🌐 Recarregando aplicação com touch no wsgi.py"
    touch /var/www/tsiqueira4_pythonanywhere_com_wsgi.py
    echo "✅ Deploy finalizado: https://tsiqueira4.pythonanywhere.com"
else
    echo "✅ Projeto atualizado localmente com sucesso!"
fi
