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

# --- DATOS JERÁRQUICOS ---
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

# --- MOTOR DE SIMULACIÓN ---
def simulate_phase(balance, risk_money, win_rate, rr, profit_target_pct, max_total_dd_pct, comm_per_lot, pip_val, sl_min, sl_max, is_funded=False):
    curr = balance
    # En cuenta fondeada, el "objetivo" es sobrevivir el mes con algo de profit (ej 1%)
    target_equity = balance + (balance * (profit_target_pct/100)) if not is_funded else balance + (balance * 0.01) 
    limit_equity = balance - (balance * (max_total_dd_pct/100))
    trades = 0
    
    # Limite de trades para simular "un mes" o "un periodo"
    max_trades = 1000 if not is_funded else 100 # Asumimos 100 trades promedio por mes de vida
    
    while curr > limit_equity and curr < target_equity and trades < max_trades:
        trades += 1
        current_trade_sl = random.uniform(sl_min, sl_max)
        current_lot_size = risk_money / (current_trade_sl * pip_val)
        trade_commission = current_lot_size * comm_per_lot
        
        if random.random() < (win_rate/100):
            net_profit = (risk_money * rr) - trade_commission
            curr += net_profit
        else:
            total_loss = risk_money + trade_commission
            curr -= total_loss

    success = curr >= target_equity
    return success, curr

def run_business_simulation(firm_data, risk_pct, win_rate, rr, comm, sl_min, sl_max):
    n_sims = 1000
    
    # Contadores de Supervivencia por Etapa
    pass_p1 = 0
    pass_p2 = 0
    pass_payout_1 = 0
    pass_payout_2 = 0
    pass_payout_3 = 0 # Longevidad
    
    total_net_returns = 0
    
    balance = firm_data['size']
    risk_money = balance * (risk_pct / 100)
    pip_val = 10 
    is_two_step = firm_data.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        # --- FASE 1 ---
        p1_ok, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p1'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
        if not p1_ok: continue
        pass_p1 += 1
            
        # --- FASE 2 (Si existe) ---
        if is_two_step:
            p2_ok, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p2'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
            if not p2_ok: continue
            pass_p2 += 1
        else:
            pass_p2 += 1 # Si es 1-step, pasar fase 1 cuenta como fase 2 completada para la lógica
        
        # --- MES 1: Primer Retiro ---
        m1_ok, m1_bal = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True)
        if m1_ok:
            pass_payout_1 += 1
            profit = m1_bal - balance
            payout = (profit * 0.8) + firm_data['cost'] + firm_data.get('p1_bonus', 0)
            total_net_returns += payout
            
            # --- MES 2: Segundo Retiro (Sobrevivir otro mes) ---
            # Reseteamos balance a inicial (simulando retiro)
            m2_ok, m2_bal = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True)
            if m2_ok:
                pass_payout_2 += 1
                profit2 = m2_bal - balance
                total_net_returns += (profit2 * 0.8)
                
                # --- MES 3: Tercer Retiro ---
                m3_ok, m3_bal = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True)
                if m3_ok:
                    pass_payout_3 += 1
                    profit3 = m3_bal - balance
                    total_net_returns += (profit3 * 0.8)

    # Cálculo de Probabilidades Acumuladas
    prob_p1 = (pass_p1 / n_sims) * 100
    prob_p2 = (pass_p2 / n_sims) * 100
    prob_pay1 = (pass_payout_1 / n_sims) * 100
    prob_pay2 = (pass_payout_2 / n_sims) * 100
    prob_pay3 = (pass_payout_3 / n_sims) * 100
    
    avg_return_total = total_net_returns / n_sims # Retorno promedio por cada cuenta comprada (EV)
    roi_net = avg_return_total - firm_data['cost']

    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, 
        "prob_pay1": prob_pay1, "prob_pay2": prob_pay2, "prob_pay3": prob_pay3,
        "ev_net": roi_net
    }

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
    # --- DASHBOARD DE NEGOCIO ---
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("🛡️ Prop Firm Unit Economics")
    col_h2.write(f"👤 {st.session_state['username']}")
    if col_h2.button("Salir"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # --- SIDEBAR (CONFIG) ---
    st.sidebar.header("1. Configuración")
    sel_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    sel_program = st.sidebar.selectbox("Programa", list(FIRMS_DATA[sel_company].keys()))
    sel_size = st.sidebar.selectbox("Capital", list(FIRMS_DATA[sel_company][sel_program].keys()))
    
    firm = FIRMS_DATA[sel_company][sel_program][sel_size]
    full_name_db = f"{sel_company} - {sel_program} ({sel_size})"
    
    st.sidebar.header("2. Estrategia")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo Trade (%)", 0.1, 3.0, 1.0)
    comm = st.sidebar.number_input("Comisión ($/Lote)", 0.0, 10.0, 7.0)
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mín", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Max", 1, 200, 15)

    # --- TARJETA DE REGLAS (ALWAYS ON) ---
    # Esto responde a tu petición de tener las reglas siempre visibles
    st.markdown("### 📋 Reglas y Condiciones de la Cuenta")
    
    # Preparamos textos
    is_2step = firm.get('profit_p2', 0) > 0
    target_txt = f"{firm['profit_p1']}% (F1) / {firm['profit_p2']}% (F2)" if is_2step else f"{firm['profit_p1']}%"
    
    rule_c1, rule_c2, rule_c3, rule_c4 = st.columns(4)
    rule_c1.metric("Costo (Fee)", f"${firm['cost']}", border=True)
    rule_c2.metric("Objetivo Profit", target_txt, border=True)
    rule_c3.metric("Drawdown Max", f"{firm['total_dd']}%", f"Diario: {firm.get('daily_dd',0)}%", border=True)
    rule_c4.metric("Tamaño Cuenta", f"${firm['size']:,}", border=True)

    if st.button("📊 Simular Viabilidad del Negocio", type="primary", use_container_width=True):
        
        with st.spinner("Simulando Fases, Retiros y Longevidad..."):
            stats = run_business_simulation(firm, risk, wr, rr, comm, sl_min, sl_max)
            
            # Cálculo de "Costo Real" para DB
            attempts_needed = 100 / stats['prob_pay1'] if stats['prob_pay1'] > 0 else 100
            real_cost = math.ceil(attempts_needed) * firm['cost']
            save_plan_db(st.session_state['username'], full_name_db, wr, rr, stats['prob_pay1'], real_cost)

        # --- RESULTADOS ORGANIZADOS EN PESTAÑAS ---
        st.divider()
        tab_flow, tab_business = st.tabs(["🛤️ El Viaje (Paso a Paso)", "💼 Detalle del Negocio"])

        # PESTAÑA 1: EL FLUJO CRONOLÓGICO
        with tab_flow:
            st.subheader("Probabilidades Paso a Paso")
            st.caption("¿Qué tan lejos llegará tu cuenta según tu estadística actual?")
            
            # Diagrama de Flujo Horizontal con Métricas
            col_step1, col_arrow1, col_step2, col_arrow2, col_fund = st.columns([2,1,2,1,2])
            
            with col_step1:
                st.info("##### 1️⃣ Fase de Evaluación")
                st.metric("Pasar Fase 1", f"{stats['prob_p1']:.1f}%")
                if is_2step:
                    st.metric("Pasar Fase 2", f"{stats['prob_p2']:.1f}%")
            
            with col_arrow1:
                st.markdown("<h1 style='text-align: center; color: grey;'>⮕</h1>", unsafe_allow_html=True)

            with col_step2:
                st.warning("##### 2️⃣ Primer Cobro")
                st.metric("Prob. 1er Retiro", f"{stats['prob_pay1']:.1f}%", help="Probabilidad de pasar TODO y cobrar al menos una vez.")
            
            with col_arrow2:
                st.markdown("<h1 style='text-align: center; color: grey;'>⮕</h1>", unsafe_allow_html=True)

            with col_fund:
                st.success("##### 3️⃣ Consistencia")
                st.metric("Llegar a 2do Retiro", f"{stats['prob_pay2']:.1f}%")
                st.metric("Llegar a 3er Retiro", f"{stats['prob_pay3']:.1f}%")

        # PESTAÑA 2: EL NEGOCIO (NUMEROS DUROS)
        with tab_business:
            st.subheader("Análisis Financiero")
            
            b_col1, b_col2, b_col3 = st.columns(3)
            
            # Costo Real Ajustado
            real_attempts = 100 / stats['prob_pay1'] if stats['prob_pay1'] > 0 else 100
            real_budget = math.ceil(real_attempts) * firm['cost']
            
            b_col1.metric("Costo Real Adquisición", f"${real_budget}", 
                         help="Dinero que estadísticamente debes tener preparado para lograr 1 retiro exitoso.")
            
            b_col2.metric("Intentos Estimados", f"{real_attempts:.1f}", 
                         help="Cuántas cuentas sueles quemar por cada una que cobra.")
            
            # ROI
            roi_val = stats['ev_net']
            roi_label = "Rentable" if roi_val > 0 else "No Rentable"
            b_col3.metric("Expectativa (EV) por Intento", f"${roi_val:.0f}", roi_label, 
                         delta_color="normal" if roi_val > 0 else "inverse")
            
            st.info("""
            **Interpretación:**
            * **Prob. 1er Retiro:** Es tu métrica más importante. Si es baja (<20%), estás regalando dinero en fees.
            * **Consistencia:** Si la prob. cae drásticamente entre el 1er y 3er retiro, tu estrategia es demasiado arriesgada para mantener una cuenta viva a largo plazo.
            """)

    st.divider()
    with st.expander("📜 Historial"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob Payout %", "Costo Real $", "Fecha"]), use_container_width=True)