import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time
import math

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Prop Firm Unit Economics", page_icon="🛡️", layout="wide")

# --- INICIALIZAR SESIÓN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

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

# --- FUNCIONES AUTH & DB ---
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

# --- ESTRUCTURA DE DATOS JERÁRQUICA (NUEVA) ---
# Estructura: Empresa -> Programa -> Tamaño -> Datos
FIRMS_DATA = {
    "The5ers": {
        "High Stakes (2 Step)": {
            "5K":   {"cost": 39,  "size": 5000,   "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 5},
            "10K":  {"cost": 78,  "size": 10000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 10},
            "20K":  {"cost": 165, "size": 20000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 15},
            "60K":  {"cost": 329, "size": 60000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 25},
            "100K": {"cost": 545, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 40}
        },
        "Hyper Growth (1 Step)": {
            "5K":   {"cost": 260, "size": 5000,   "daily_dd": 3.0, "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 15},
            "10K":  {"cost": 450, "size": 10000,  "daily_dd": 3.0, "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 25},
            "20K":  {"cost": 850, "size": 20000,  "daily_dd": 3.0, "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 50}
        }
    },
    "FTMO": {
        "Swing Challenge": {
            "100K": {"cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 10.0, "profit_p2": 5.0, "p1_bonus": 0}
        }
    },
    "FundedNext": {
        "Stellar 1-Step": {
            "100K": {"cost": 519, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 0.0, "p1_bonus": 0}
        }
    }
}

# --- SIMULADOR DE FASE INDIVIDUAL ---
def simulate_phase(balance, risk_money, win_rate, rr, profit_target_pct, max_total_dd_pct, comm_per_lot, pip_val, sl_min, sl_max):
    """Retorna True si pasa, False si quema, y la curva de equity"""
    curr = balance
    limit_equity = balance - (balance * (max_total_dd_pct/100))
    target_equity = balance + (balance * (profit_target_pct/100))
    curve = [curr]
    trades = 0
    
    # Límite de trades por seguridad para evitar loops infinitos
    while curr > limit_equity and curr < target_equity and trades < 1500:
        trades += 1
        
        # Dinámica de Mercado (SL Variable)
        current_trade_sl = random.uniform(sl_min, sl_max)
        current_lot_size = risk_money / (current_trade_sl * pip_val)
        trade_commission = current_lot_size * comm_per_lot
        
        if random.random() < (win_rate/100):
            net_profit = (risk_money * rr) - trade_commission
            curr += net_profit
        else:
            total_loss = risk_money + trade_commission
            curr -= total_loss
        
        curve.append(curr)

    success = curr >= target_equity
    return success, trades, curve, current_lot_size

# --- SIMULACIÓN GENERAL (1 o 2 Pasos) ---
def run_full_simulation(firm_data, risk_pct, win_rate, rr, trades_day, comm, sl_min, sl_max):
    n_sims = 1000
    passed_count = 0
    total_days_log = []
    equity_curves = [] 
    avg_lots_used_log = []
    
    balance = firm_data['size']
    risk_money = balance * (risk_pct / 100)
    pip_val = 10 
    
    # Detectamos si es 1 Step o 2 Step
    is_two_step = firm_data.get('profit_p2', 0) > 0
    
    for i in range(n_sims):
        # --- FASE 1 ---
        p1_success, p1_trades, p1_curve, last_lot = simulate_phase(
            balance, risk_money, win_rate, rr, 
            firm_data['profit_p1'], firm_data['total_dd'], 
            comm, pip_val, sl_min, sl_max
        )
        
        if i < 5: avg_lots_used_log.append(last_lot) # Guardamos muestra de lotaje
        
        final_curve = p1_curve
        total_trades = p1_trades
        
        if p1_success:
            if is_two_step:
                # --- FASE 2 ---
                # Reseteamos balance para fase 2
                p2_success, p2_trades, p2_curve, _ = simulate_phase(
                    balance, risk_money, win_rate, rr, 
                    firm_data['profit_p2'], firm_data['total_dd'], 
                    comm, pip_val, sl_min, sl_max
                )
                
                # Unimos curvas visualmente (shift para que se vea continuo)
                offset = p1_curve[-1] - p2_curve[0]
                shifted_p2 = [x + offset for x in p2_curve]
                final_curve = p1_curve + shifted_p2[1:] # Unir
                total_trades += p2_trades
                
                if p2_success:
                    passed_count += 1
            else:
                # Si es 1 Step y pasó la fase 1, es éxito
                passed_count += 1
        
        # Guardar datos para promedios
        if p1_success: # Solo contamos días si al menos pasó la fase 1 (o todo)
             total_days_log.append(total_trades / trades_day if trades_day > 0 else 0)
        
        if i < 20: equity_curves.append(final_curve)

    pass_rate = (passed_count / n_sims) * 100
    avg_days = sum(total_days_log) / len(total_days_log) if total_days_log else 0
    avg_lot = sum(avg_lots_used_log) / len(avg_lots_used_log) if avg_lots_used_log else 0
    
    return pass_rate, avg_days, equity_curves, avg_lot

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
    # --- DASHBOARD LOGUEADO ---
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("🛡️ Prop Firm Unit Economics")
    col_h2.write(f"👤 {st.session_state['username']}")
    if col_h2.button("Salir"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # --- SELECTORES JERÁRQUICOS ---
    st.sidebar.header("1. La Empresa")
    
    # Nivel 1: Empresa
    sel_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    
    # Nivel 2: Programa (Tipo de Cuenta)
    programs_available = list(FIRMS_DATA[sel_company].keys())
    sel_program = st.sidebar.selectbox("Programa / Desafío", programs_available)
    
    # Nivel 3: Tamaño
    sizes_available = list(FIRMS_DATA[sel_company][sel_program].keys())
    sel_size = st.sidebar.selectbox("Tamaño de Cuenta", sizes_available)
    
    # Obtener Datos Finales
    firm = FIRMS_DATA[sel_company][sel_program][sel_size]
    
    # Identificar nombre completo para DB
    full_name_db = f"{sel_company} - {sel_program} ({sel_size})"
    
    # Mostrar Reglas
    is_2step = firm.get('profit_p2', 0) > 0
    target_text = f"F1: {firm['profit_p1']}% | F2: {firm['profit_p2']}%" if is_2step else f"Objetivo: {firm['profit_p1']}%"
    
    st.sidebar.markdown(f"""
    **Reglas del Juego:**
    * 💰 Costo: **${firm['cost']}**
    * 📉 DD Max: **{firm['total_dd']}%** | Diario: **{firm.get('daily_dd', 0)}%**
    * 🎯 {target_text}
    * 🎁 Payout Fase 1: **${firm.get('p1_bonus', 0)}**
    """)

    st.sidebar.header("2. Gestión de Riesgo")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo Fijo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. Realidad de Mercado")
    trades_day = st.sidebar.number_input("Trades por día", 1, 20, 3)
    comm = st.sidebar.number_input("Comisión ($ por Lote)", 0.0, 10.0, 7.0)
    
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mín (Pips)", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Max (Pips)", 1, 200, 15)

    if st.button("🚀 Simular Negocio", type="primary", use_container_width=True):
        
        with st.spinner(f"Simulando {full_name_db}..."):
            prob, days, curves, avg_lot = run_full_simulation(
                firm, risk, wr, rr, trades_day, comm, sl_min, sl_max
            )
            
            # Cálculo de Presupuesto (Unit Economics)
            attempts_needed_math = 100/prob if prob > 0 else 100
            attempts_recommended = math.ceil(attempts_needed_math)
            if prob > 90: attempts_recommended = 1
            
            budget_suggested = attempts_recommended * firm['cost']
            
            save_plan_db(st.session_state['username'], full_name_db, wr, rr, prob, budget_suggested)

        # --- RESULTADOS ---
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        kpi1.metric("Probabilidad Total", f"{prob:.1f}%", help="Probabilidad de pasar TODAS las fases requeridas.")
        kpi2.metric("Costo Cuenta", f"${firm['cost']}")
        
        # Lógica de colores para alerta de presupuesto
        c_delta = "normal"
        if attempts_recommended > 1: c_delta = "inverse"
        
        kpi3.metric(f"Sugerencia: {attempts_recommended} Intentos", f"${budget_suggested}", 
                   delta_color=c_delta, help="Presupuesto sugerido para garantizar estadísticamente el fondeo.")
                   
        kpi4.metric("Días Estimados", f"{int(days)}")

        # Información Extra
        st.info(f"""
        **💡 Análisis {sel_program}:**
        * Al pasar la Fase 1, recibirás una repartición de **${firm.get('p1_bonus', 0)}** (The5ers Hub Credits/Cash).
        * Si pasas todo, recuperas el fee de **${firm['cost']}** en el primer payout.
        * Estás operando con **{avg_lot:.2f} lotes** promedio.
        """)

        st.subheader("🔮 Curvas de Equity (Fase 1 + Fase 2)")
        chart_data = pd.DataFrame()
        max_len = max(len(c) for c in curves)
        for idx, c in enumerate(curves):
            extended_c = c + [np.nan] * (max_len - len(c))
            chart_data[f"Sim {idx}"] = extended_c 
        st.line_chart(chart_data, height=300)

    st.divider()
    with st.expander("📜 Historial"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob %", "Presupuesto $", "Fecha"]), use_container_width=True)