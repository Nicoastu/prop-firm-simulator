import streamlit as st

# Configuración de la página
st.set_page_config(page_title="Prop Firm Simulator", layout="centered")

# --- BASE DE DATOS (DICCIONARIO) ---
# Aquí precargamos las reglas como acordamos
PROP_FIRMS = {
    "FTMO - 100k Swing": {
        "cost": 540,
        "currency": "USD",
        "size": 100000,
        "daily_dd_percent": 5.0,  # 5%
        "total_dd_percent": 10.0, # 10%
        "profit_target_p1": 10.0, # 10%
        "profit_target_p2": 5.0,  # 5%
        "drawdown_type": "Balance Based"
    },
    "FundedNext - 100k Stellar": {
        "cost": 519,
        "currency": "USD",
        "size": 100000,
        "daily_dd_percent": 5.0,
        "total_dd_percent": 10.0,
        "profit_target_p1": 8.0,
        "profit_target_p2": 5.0,
        "drawdown_type": "Balance Based"
    },
    "Apex - 50k Futures": {
        "cost": 167,
        "currency": "USD",
        "size": 50000,
        "daily_dd_percent": 0.0, # No tiene diario estricto a veces, depende
        "total_dd_percent": 5.0, # Trailing
        "profit_target_p1": 6.0, # 3000 profit
        "profit_target_p2": 0.0,
        "drawdown_type": "Trailing Drawdown"
    }
}

# --- INTERFAZ VISUAL ---
st.title("🛡️ Prop Firm Unit Economics")
st.markdown("Calcula la rentabilidad real de tu negocio de fondeo.")

# Selector de Empresa (Prueba de concepto)
selected_firm = st.selectbox("Selecciona una Empresa / Desafío:", list(PROP_FIRMS.keys()))

# Mostrar datos crudos para verificar
st.write("Reglas cargadas:", PROP_FIRMS[selected_firm])