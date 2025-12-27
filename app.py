import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Prop Firm Unit Economics", page_icon="🛡️", layout="wide")

# --- BASE DE DATOS (Mantenemos tu lógica existente) ---
db_url = os.getenv("DATABASE_URL")
engine = None

if db_url:
    try:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url)
    except Exception as e:
        st.error(f"Error conectando a BD: {e}")

def init_db():
    if engine:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT, 
                    auth_type TEXT DEFAULT 'manual'
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS plans (
                    id SERIAL PRIMARY KEY,
                    username TEXT,
                    firm_name TEXT,
                    win_rate FLOAT,
                    risk_reward FLOAT,
                    pass_prob FLOAT,
                    investment_needed FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()

def register_user(username, password, auth_type='manual'):
    if not engine: return False
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": username}).fetchone()
            if res: return False 
            conn.execute(text("INSERT INTO users (username, password, auth_type) VALUES (:u, :p, :a)"), 
                         {"u": username, "p": password, "a": auth_type})
            conn.commit()
            return True
    except: return False

def login_user_manual(username, password):
    if not engine: return False
    with engine.connect() as conn:
        res = conn.execute(text("SELECT password FROM users WHERE username = :u AND auth_type='manual'"), {"u": username}).fetchone()
        if res and res[0] == password: return True
    return False

def save_plan_db(username, firm, wr, rr, prob, inv):
    if engine:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO plans (username, firm_name, win_rate, risk_reward, pass_prob, investment_needed)
                VALUES (:u, :f, :w, :r, :p, :i)
            """), {"u": username, "f": firm, "w": wr, "r": rr, "p": prob, "i": inv})
            conn.commit()

def get_user_plans(username):
    if not engine: return []
    with engine.connect() as conn:
        result = conn.execute(text("SELECT firm_name, pass_prob, investment_needed, created_at FROM plans WHERE username = :u ORDER BY created_at DESC LIMIT 10"), {"u": username})
        return result.fetchall()

if engine: init_db()

# --- DATOS DE EMPRESAS ---
PROP_FIRMS = {
    "FTMO - 100k Swing": {"cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 10.0},
    "FundedNext - 100k Stellar": {"cost": 519, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0},
    "Apex - 50k Futures": {"cost": 167, "size": 50000, "daily_dd": 0.0, "total_dd": 4.0, "profit": 6.0},
    "Alpha Capital - 50k": {"cost": 297, "size": 50000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0}
}

# --- LÓGICA DE SIMULACIÓN AVANZADA ---
def run_advanced_simulation(balance, risk_pct, win_rate, rr, profit_target, max_total_dd, 
                          trades_per_day, comm_per_lot, avg_sl_pips):
    
    n_sims = 1000
    passed_count = 0
    total_trades_log = []
    max_losing_streak_log = []
    equity_curves = [] # Guardaremos algunas curvas para graficar
    
    # Cálculos de Gestión de Riesgo y Comisiones
    risk_amount = balance * (risk_pct / 100)
    
    # Estimación de Lote: Riesgo / (SL * ValorPip)
    # Asumimos EURUSD aprox $10 por pip por lote estándar
    pip_value_std = 10 
    lot_size = risk_amount / (avg_sl_pips * pip_value_std)
    commission_cost = lot_size * comm_per_lot
    
    # Ajuste de Win/Loss Real (Neto de comisiones)
    # Si gano: (Riesgo * RR) - Comisión
    # Si pierdo: Riesgo + Comisión
    real_win_amt = (risk_amount * rr) - commission_cost
    real_loss_amt = risk_amount + commission_cost
    
    # Limites
    limit_equity = balance - (balance * (max_total_dd/100))
    target_equity = balance + (balance * (profit_target/100))
    
    for i in range(n_sims):
        curr = balance
        trades = 0
        current_streak = 0
        max_streak = 0
        curve = [curr]
        
        while curr > limit_equity and curr < target_equity and trades < 1000:
            trades += 1
            if random.random() < (win_rate/100):
                curr += real_win_amt
                current_streak = 0
            else:
                curr -= real_loss_amt
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            
            # Guardamos puntos de la curva solo para las primeras 20 simulaciones (optimización memoria)
            if i < 20:
                curve.append(curr)
                
        if curr >= target_equity:
            passed_count += 1
            total_trades_log.append(trades)
        
        max_losing_streak_log.append(max_streak)
        if i < 20:
            equity_curves.append(curve)

    pass_rate = (passed_count / n_sims) * 100
    avg_trades = sum(total_trades_log) / len(total_trades_log) if total_trades_log else 0
    avg_days = avg_trades / trades_per_day if trades_per_day > 0 else 0
    avg_max_streak = sum(max_losing_streak_log) / len(max_losing_streak_log)
    
    return pass_rate, avg_days, avg_max_streak, equity_curves

# --- ESTADO DE SESIÓN ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''

# --- INTERFAZ ---

if not st.session_state['logged_in']:
    # LOGIN SIMPLE
    st.title("🛡️ Prop Firm Simulator")
    tab1, tab2 = st.tabs(["Entrar", "Crear Cuenta"])
    with tab1:
        u = st.text_input("Usuario", key="l_u")
        p = st.text_input("Pass", type="password", key="l_p")
        if st.button("Entrar", type="primary"):
            if login_user_manual(u, p):
                st.session_state['logged_in'] = True; st.session_state['username'] = u; st.rerun()
            else: st.error("Error credenciales")
    with tab2:
        nu = st.text_input("Nuevo Usuario", key="r_u")
        np = st.text_input("Nueva Pass", type="password", key="r_p")
        if st.button("Registrar"):
            if register_user(nu, np): st.success("Creado!"); st.rerun()
            else: st.error("Error registro")

else:
    # --- DASHBOARD DE NEGOCIO ---
    
    # Header minimalista
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("🛡️ Prop Firm Unit Economics")
    col_h2.write(f"👤 {st.session_state['username']}")
    if col_h2.button("Salir"):
        st.session_state['logged_in'] = False; st.rerun()

    st.markdown("---")

    # --- CONFIGURACIÓN (SIDEBAR) ---
    st.sidebar.header("1. La Empresa")
    firm_name = st.sidebar.selectbox("Selecciona Desafío", list(PROP_FIRMS.keys()))
    firm = PROP_FIRMS[firm_name]
    
    # Mostrar reglas básicas
    st.sidebar.info(f"💰 Costo: ${firm['cost']} \n\n 📉 Max DD: {firm['total_dd']}% \n\n 🎯 Objetivo: {firm['profit']}%")

    st.sidebar.header("2. Tu Estrategia")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45, help="Tu porcentaje real de aciertos")
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0, help="Cuánto ganas por cada 1 que arriesgas")
    risk = st.sidebar.slider("Riesgo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. La Realidad (Costos)")
    trades_day = st.sidebar.number_input("Trades por día (Promedio)", 1, 20, 3)
    comm = st.sidebar.number_input("Comisión ($ por Lote)", 0.0, 10.0, 7.0, help="Suele ser $7 en cuentas Raw")
    sl_pips = st.sidebar.number_input("Stop Loss Promedio (Pips)", 5, 100, 10, help="Necesario para calcular impacto de comisiones")

    # --- SIMULACIÓN ---
    if st.button("🚀 Correr Simulación de Negocio", type="primary", use_container_width=True):
        
        with st.spinner("Calculando escenarios, comisiones y proyecciones..."):
            prob, days, streak, curves = run_advanced_simulation(
                firm['size'], risk, wr, rr, firm['profit'], firm['total_dd'],
                trades_day, comm, sl_pips
            )
            
            # Unit Economics
            attempts = 100/prob if prob > 0 else 100
            inv = attempts * firm['cost']
            
            # Guardar en BD
            save_plan_db(st.session_state['username'], firm_name, wr, rr, prob, inv)

        # --- RESULTADOS VISUALES ---
        
        # 1. KPIs Principales
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        # Lógica de color para probabilidad
        prob_color = "normal"
        if prob > 50: prob_color = "normal" 
        
        kpi1.metric("Probabilidad de Éxito", f"{prob:.1f}%", delta=None)
        kpi2.metric("Inversión Estimada", f"${inv:,.0f}", help=f"Basado en {attempts:.1f} intentos promedio")
        kpi3.metric("Tiempo Estimado", f"{int(days)} Días", help="Días de trading necesarios para pasar")
        kpi4.metric("Peor Racha Esperada", f"{int(streak)} Pérdidas", help="Racha de pérdidas consecutivas promedio", delta_color="inverse")

        # 2. Análisis Gráfico (Equity Curves)
        st.subheader("🔮 Futuros Posibles (Equity Curves)")
        st.caption("Visualización de 20 simulaciones aleatorias. Observa cómo la varianza afecta tu resultado.")
        
        # Preparamos datos para gráfico de líneas
        # Necesitamos normalizar las longitudes de las curvas
        max_len = max(len(c) for c in curves)
        chart_data = pd.DataFrame()
        
        for idx, c in enumerate(curves):
            # Rellenamos con NaN para igualar longitudes si terminaron antes
            extended_c = c + [np.nan] * (max_len - len(c))
            chart_data[f"Sim {idx}"] = extended_c
            
        st.line_chart(chart_data, height=350)
        
        # 3. Insights de Negocio
        st.info(f"""
        💡 **Análisis de Rentabilidad:**
        Con tu estrategia actual, las comisiones te están costando un extra implícito. 
        Para obtener tu primera cuenta fondeada, deberías tener un presupuesto de **${inv:,.0f}**.
        Si tu primer retiro promedio es mayor a esa cantidad, **¡Tu negocio es viable!** ✅
        """)

    # --- HISTORIAL ---
    st.divider()
    with st.expander("📜 Ver Historial de Simulaciones"):
        planes = get_user_plans(st.session_state['username'])
        if planes:
            df = pd.DataFrame(planes, columns=["Empresa", "Prob %", "Inversión $", "Fecha"])
            st.dataframe(df, use_container_width=True)
        else:
            st.write("Aún no hay datos.")