import streamlit as st
import random
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Prop Firm Unit Economics", page_icon="🛡️", layout="wide")

# --- 1. BASE DE DATOS (Las reglas del juego) ---
PROP_FIRMS = {
    "FTMO - 100k Swing": {
        "cost": 540,
        "currency": "USD",
        "size": 100000,
        "daily_dd_percent": 5.0,
        "total_dd_percent": 10.0,
        "profit_target_p1": 10.0,
        "profit_target_p2": 5.0,
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
        "daily_dd_percent": 0.0, 
        "total_dd_percent": 4.0, 
        "profit_target_p1": 6.0, 
        "profit_target_p2": 0.0,
        "drawdown_type": "Trailing Drawdown"
    }
}

# --- 2. LOGICA DE MONTECARLO (El Cerebro) ---
def run_monte_carlo_simulation(balance, risk_percent, win_rate, risk_reward, profit_target, max_daily_dd, max_total_dd, n_simulations=1000):
    """
    Simula n intentos de pasar la prueba y devuelve estadísticas.
    """
    passed_count = 0
    ruin_count = 0
    avg_trades = []
    
    risk_amount = balance * (risk_percent / 100)
    win_amount = risk_amount * risk_reward
    daily_dd_limit = balance * (max_daily_dd / 100)
    total_dd_limit = balance * (max_total_dd / 100)
    target_amount = balance + (balance * (profit_target / 100))
    min_balance = balance - total_dd_limit

    for _ in range(n_simulations):
        current_balance = balance
        trades = 0
        # Simplificación: Asumimos que el DD diario se resetea, aquí verificamos racha de pérdidas en un "día" simulado
        # Para el MVP verificamos principalmente el Drawdown Total
        
        while current_balance > min_balance and current_balance < target_amount:
            trades += 1
            if random.random() < (win_rate / 100):
                current_balance += win_amount
            else:
                current_balance -= risk_amount
            
            # Límite de trades para evitar bucles infinitos en estrategias break-even
            if trades > 500: 
                break
        
        if current_balance >= target_amount:
            passed_count += 1
            avg_trades.append(trades)
        else:
            ruin_count += 1

    pass_rate = (passed_count / n_simulations) * 100
    avg_trades_needed = sum(avg_trades) / len(avg_trades) if avg_trades else 0
    
    return pass_rate, avg_trades_needed

# --- 3. INTERFAZ DE USUARIO (Frontend) ---
st.title("🛡️ Prop Firm Unit Economics")
st.markdown("### ¿Es tu estrategia rentable para este modelo de negocio?")

# --- SECCIÓN A: Elegir el Escenario ---
st.sidebar.header("1. Configura el Escenario")
selected_firm_name = st.sidebar.selectbox("Empresa / Desafío", list(PROP_FIRMS.keys()))
firm_data = PROP_FIRMS[selected_firm_name]

# --- SECCIÓN B: Tu Estrategia (Inputs) ---
st.sidebar.header("2. Tu Estrategia (La Verdad)")
win_rate = st.sidebar.slider("Win Rate (%)", 10, 90, 45)
risk_reward = st.sidebar.slider("Ratio Riesgo:Beneficio (1:X)", 0.5, 5.0, 2.0)
risk_per_trade = st.sidebar.slider("Riesgo por Operación (%)", 0.1, 3.0, 1.0)
n_sims = st.sidebar.select_slider("Precisión (Simulaciones)", options=[100, 1000, 5000], value=1000)

# --- VISUALIZACIÓN DE REGLAS (Esto arregla lo que veías feo) ---
st.divider()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Costo Prueba", f"${firm_data['cost']}")
col2.metric("Objetivo Profit", f"{firm_data['profit_target_p1']}%")
col3.metric("Max Drawdown", f"{firm_data['total_dd_percent']}%")
col4.metric("Cuenta", f"${firm_data['size']:,}")

# --- BOTÓN DE ACCIÓN ---
if st.button("🔄 Simular Resultados de Negocio", type="primary"):
    
    with st.spinner('Corriendo miles de escenarios matemáticos...'):
        # Ejecutar simulación
        pass_prob, trades_avg = run_monte_carlo_simulation(
            balance=firm_data['size'],
            risk_percent=risk_per_trade,
            win_rate=win_rate,
            risk_reward=risk_reward,
            profit_target=firm_data['profit_target_p1'],
            max_daily_dd=firm_data['daily_dd_percent'],
            max_total_dd=firm_data['total_dd_percent'],
            n_simulations=n_sims
        )

    # --- RESULTADOS ---
    st.divider()
    st.subheader("📊 Resultados del Análisis")
    
    # Semáforo de Probabilidad
    r_col1, r_col2 = st.columns(2)
    
    if pass_prob > 40:
        color = "green"
        msg = "¡Alta Probabilidad!"
    elif pass_prob > 20:
        color = "orange"
        msg = "Riesgo Moderado"
    else:
        color = "red"
        msg = "Zona de Peligro (Quemará Cuenta)"

    r_col1.markdown(f"### Probabilidad de Pasar: :{color}[{pass_prob:.1f}%]")
    r_col1.caption(f"{msg} Basado en {n_sims} simulaciones.")
    
    r_col2.metric("Trades Promedio Necesarios", f"{int(trades_avg)}")

    # Unit Economics (La parte de Negocio)
    st.markdown("### 💰 Unit Economics (Tu Realidad Financiera)")
    
    # Evitar división por cero
    intentos_necesarios = 100 / pass_prob if pass_prob > 0 else 100
    costo_estimado = intentos_necesarios * firm_data['cost']
    
    ue_col1, ue_col2, ue_col3 = st.columns(3)
    ue_col1.metric("Intentos Estimados", f"{intentos_necesarios:.1f}")
    ue_col2.metric("Inversión Requerida", f"${costo_estimado:,.0f} USD")
    ue_col3.info(f"Esto significa que estadísticamente podrías quemar **{int(intentos_necesarios)} cuentas** antes de pasar una. ¿Tienes capital para eso?")

else:
    st.info("👈 Ajusta tus parámetros en la izquierda y presiona Simular.")