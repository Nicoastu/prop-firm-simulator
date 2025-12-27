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

# --- BASE DE DATOS ---
db_url = os.getenv("DATABASE_URL")
engine = None

if db_url:
    try:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url)
    except Exception as e:
        st.error(f"Error crítico conectando a BD: {e}")

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

# --- AUTH FUNCTIONS ---
def register_user(username, password, auth_type='manual'):
    if not engine: return "No hay conexión a BD"
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": username}).fetchone()
            if res: return "El usuario ya existe"
            conn.execute(text("INSERT INTO users (username, password, auth_type) VALUES (:u, :p, :a)"), 
                         {"u": username, "p": password, "a": auth_type})
            conn.commit()
            return "OK"
    except Exception as e: return f"Error de Sistema: {str(e)}"

def login_user_manual(username, password):
    if not engine: return False
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT password FROM users WHERE username = :u AND auth_type='manual'"), {"u": username}).fetchone()
            if res and res[0] == password: return True
        return False
    except: return False

def save_plan_db(username, firm, wr, rr, prob, inv):
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO plans (username, firm_name, win_rate, risk_reward, pass_prob, investment_needed)
                    VALUES (:u, :f, :w, :r, :p, :i)
                """), {"u": username, "f": firm, "w": wr, "r": rr, "p": prob, "i": inv})
                conn.commit()
        except: pass

def get_user_plans(username):
    if not engine: return []
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT firm_name, pass_prob, investment_needed, created_at FROM plans WHERE username = :u ORDER BY created_at DESC LIMIT 10"), {"u": username})
            return result.fetchall()
    except: return []

if engine: init_db()

# --- DATOS EMPRESAS ---
PROP_FIRMS = {
    "FTMO - 100k Swing": {"cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 10.0},
    "FundedNext - 100k Stellar": {"cost": 519, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0},
    "Apex - 50k Futures": {"cost": 167, "size": 50000, "daily_dd": 0.0, "total_dd": 4.0, "profit": 6.0},
    "Alpha Capital - 50k": {"cost": 297, "size": 50000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0}
}

# --- SIMULACIÓN DINÁMICA (NUEVO CORE) ---
def run_dynamic_simulation(balance, risk_pct, win_rate, rr, profit_target, max_total_dd, 
                          trades_per_day, comm_per_lot, sl_min, sl_max):
    
    n_sims = 1000
    passed_count = 0
    total_trades_log = []
    max_losing_streak_log = []
    equity_curves = [] 
    
    # Lista para calcular el lotaje promedio real usado
    avg_lots_used_log = []
    
    risk_money = balance * (risk_pct / 100)
    pip_value_std = 10 # EURUSD Standard
    
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
            
            # --- DINÁMICA DE MERCADO ---
            # Cada trade tiene un SL distinto dentro del rango del usuario
            current_trade_sl = random.uniform(sl_min, sl_max)
            
            # Calculamos lotaje para ESE trade específico
            # Si el SL es muy pequeño, el lotaje se dispara (y la comisión también)
            current_lot_size = risk_money / (current_trade_sl * pip_value_std)
            
            # Guardamos dato para estadísticas
            if i < 5: avg_lots_used_log.append(current_lot_size)
            
            trade_commission = current_lot_size * comm_per_lot
            
            # Resultado neto del trade
            if random.random() < (win_rate/100):
                # GANA: (Riesgo * RR) - Comisión
                gross_profit = risk_money * rr
                net_profit = gross_profit - trade_commission
                curr += net_profit
                current_streak = 0
            else:
                # PIERDE: Riesgo + Comisión
                # Nota: En stop loss pierdes lo arriesgado Y ADEMÁS pagas comisión
                total_loss = risk_money + trade_commission
                curr -= total_loss
                current_streak += 1
                if current_streak > max_streak: max_streak = current_streak
            
            if i < 20: curve.append(curr)
                
        if curr >= target_equity:
            passed_count += 1
            total_trades_log.append(trades)
        
        max_losing_streak_log.append(max_streak)
        if i < 20: equity_curves.append(curve)

    pass_rate = (passed_count / n_sims) * 100
    avg_trades = sum(total_trades_log) / len(total_trades_log) if total_trades_log else 0
    avg_days = avg_trades / trades_per_day if trades_per_day > 0 else 0
    avg_max_streak = sum(max_losing_streak_log) / len(max_losing_streak_log)
    avg_lot_metric = sum(avg_lots_used_log) / len(avg_lots_used_log) if avg_lots_used_log else 0
    
    return pass_rate, avg_days, avg_max_streak, equity_curves, avg_lot_metric

# --- FRONTEND ---
if not st.session_state['logged_in']:
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
            msg = register_user(nu, np)
            if msg == "OK": st.success("Creado. Ingresa en la pestaña Entrar.")
            else: st.error(msg)
else:
    # DASHBOARD
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("🛡️ Prop Firm Unit Economics")
    col_h2.write(f"👤 {st.session_state['username']}")
    if col_h2.button("Salir"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # SIDEBAR
    st.sidebar.header("1. La Empresa")
    firm_name = st.sidebar.selectbox("Selecciona Desafío", list(PROP_FIRMS.keys()))
    firm = PROP_FIRMS[firm_name]
    st.sidebar.info(f"💰 Costo: ${firm['cost']} | 📉 DD Total: {firm['total_dd']}%")

    st.sidebar.header("2. Gestión de Riesgo")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo Fijo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. Realidad de Mercado")
    trades_day = st.sidebar.number_input("Trades por día", 1, 20, 3)
    comm = st.sidebar.number_input("Comisión ($ por Lote)", 0.0, 10.0, 7.0)
    
    st.sidebar.markdown("##### Variabilidad del Stop Loss")
    st.sidebar.caption("El simulador variará el SL en cada trade, afectando el lotaje y las comisiones.")
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mínimo (Pips)", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Máximo (Pips)", 1, 200, 15)

    if st.button("🚀 Simular Realidad Variable", type="primary", use_container_width=True):
        
        with st.spinner("Simulando trades con lotaje dinámico..."):
            prob, days, streak, curves, avg_lot = run_dynamic_simulation(
                firm['size'], risk, wr, rr, firm['profit'], firm['total_dd'],
                trades_day, comm, sl_min, sl_max
            )
            
            attempts = 100/prob if prob > 0 else 100
            inv = attempts * firm['cost']
            save_plan_db(st.session_state['username'], firm_name, wr, rr, prob, inv)

        # RESULTADOS
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Probabilidad Éxito", f"{prob:.1f}%")
        kpi2.metric("Inversión Estimada", f"${inv:,.0f}")
        kpi3.metric("Peor Racha", f"{int(streak)} Pérdidas")
        kpi4.metric("Días Estimados", f"{int(days)}")

        st.markdown(f"""
        ### ⚖️ Análisis de Impacto
        Operando con un riesgo del **{risk}%** y SL variable entre **{sl_min} y {sl_max} pips**:
        - Tu lotaje promedio será de **{avg_lot:.2f} lotes**.
        - Pagarás un promedio de **${(avg_lot*comm):.2f} USD** en comisiones por trade.
        
        *Nota: Cuando el simulador elige un SL de {sl_min} pips, tu comisión se dispara, reduciendo drásticamente tu beneficio neto.*
        """)

        st.subheader("🔮 Curvas de Equity (Escenarios Posibles)")
        chart_data = pd.DataFrame()
        max_len = max(len(c) for c in curves)
        for idx, c in enumerate(curves):
            extended_c = c + [np.nan] * (max_len - len(c))
            chart_data[f"Sim {idx}"] = extended_c 
        st.line_chart(chart_data, height=300)

    st.divider()
    with st.expander("📜 Historial"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob %", "Inversión $", "Fecha"]), use_container_width=True)