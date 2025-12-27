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
    # En cuenta fondeada, no hay profit target para "pasar", pero definimos un umbral mínimo de retiro (ej. 2%) para considerar "Éxito"
    target_equity = balance + (balance * (profit_target_pct/100)) if not is_funded else balance + (balance * 0.025) 
    limit_equity = balance - (balance * (max_total_dd_pct/100))
    trades = 0
    
    while curr > limit_equity and curr < target_equity and trades < 1000:
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
    return success, trades, curr

def run_business_simulation(firm_data, risk_pct, win_rate, rr, comm, sl_min, sl_max):
    n_sims = 1000
    
    # Contadores de Resultados
    fail_p1 = 0
    fail_p2 = 0
    fail_funded = 0 # Llegó a fondeada pero la quemó antes de retirar
    got_payout = 0  # Llegó a retirar
    
    total_payout_amount = 0
    
    balance = firm_data['size']
    risk_money = balance * (risk_pct / 100)
    pip_val = 10 
    is_two_step = firm_data.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        # 1. FASE 1
        p1_ok, _, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p1'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
        
        if not p1_ok:
            fail_p1 += 1
            continue
            
        # 2. FASE 2 (Si existe)
        if is_two_step:
            p2_ok, _, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p2'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
            if not p2_ok:
                fail_p2 += 1
                continue
        
        # 3. FASE FONDEADA (El objetivo aquí es sobrevivir hasta el primer retiro, ej 2.5% profit)
        funded_ok, _, final_balance = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True)
        
        if funded_ok:
            got_payout += 1
            # Calculamos cuanto retiraría (Profit Split 80% aprox del profit generado)
            profit_generated = final_balance - balance
            payout_val = profit_generated * 0.80 
            
            # Sumamos reembolso del fee si aplica
            payout_val += firm_data['cost'] 
            # Sumamos bonus fase 1 si aplica
            payout_val += firm_data.get('p1_bonus', 0)
            
            total_payout_amount += payout_val
        else:
            fail_funded += 1

    # Métricas Finales
    prob_funded = ((got_payout + fail_funded) / n_sims) * 100 # Probabilidad de obtener la cuenta
    prob_payout = (got_payout / n_sims) * 100                 # Probabilidad de RETIRAR dinero
    
    avg_payout = total_payout_amount / got_payout if got_payout > 0 else 0
    
    # Unit Economics (ROI)
    # Costo Ponderado = Costo Cuenta * (Intentos necesarios estadísticos)
    attempts_needed = 100 / prob_funded if prob_funded > 0 else 100
    real_cost_acquisition = math.ceil(attempts_needed) * firm_data['cost']
    
    # Expectativa Matemática (EV) = (Prob Retiro * Promedio Retiro) - Costo Real
    ev_net = ((prob_payout/100) * avg_payout) - firm_data['cost'] # Usamos costo unitario para EV simple por intento

    return {
        "fail_p1": fail_p1, "fail_p2": fail_p2, "fail_funded": fail_funded, "success": got_payout,
        "prob_funded": prob_funded, "prob_payout": prob_payout,
        "avg_payout": avg_payout, "real_cost": real_cost_acquisition, "ev_net": ev_net
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

    # --- SIDEBAR ---
    st.sidebar.header("1. Configuración de Negocio")
    sel_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    sel_program = st.sidebar.selectbox("Programa", list(FIRMS_DATA[sel_company].keys()))
    sel_size = st.sidebar.selectbox("Capital Inicial", list(FIRMS_DATA[sel_company][sel_program].keys()))
    
    firm = FIRMS_DATA[sel_company][sel_program][sel_size]
    full_name_db = f"{sel_company} - {sel_program} ({sel_size})"
    
    st.sidebar.info(f"💰 Costo: ${firm['cost']} | 🎯 Profit Payout: ~80%")

    st.sidebar.header("2. Tu Sistema")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. Costos Operativos")
    comm = st.sidebar.number_input("Comisión ($/Lote)", 0.0, 10.0, 7.0)
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mín", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Max", 1, 200, 15)

    if st.button("📊 Analizar Viabilidad del Negocio", type="primary", use_container_width=True):
        
        with st.spinner("Proyectando flujos de caja y tasas de retiro..."):
            stats = run_business_simulation(firm, risk, wr, rr, comm, sl_min, sl_max)
            save_plan_db(st.session_state['username'], full_name_db, wr, rr, stats['prob_payout'], stats['real_cost'])

        # --- SECCIÓN 1: EL VEREDICTO (KPIs Financieros) ---
        st.subheader("1. Viabilidad Financiera")
        
        kpi1, kpi2, kpi3 = st.columns(3)
        
        # Color del ROI
        roi_delta = "off"
        roi_color = "normal"
        if stats['ev_net'] > 0:
            roi_delta = f"+${int(stats['ev_net'])} de Ganancia Esperada"
            roi_color = "normal" # Verde por defecto en delta positivo
        else:
            roi_delta = f"-${int(abs(stats['ev_net']))} de Pérdida Esperada"
            roi_color = "inverse" # Rojo

        kpi1.metric("Costo Real de Adquisición", f"${stats['real_cost']}", 
                   help="Basado en la probabilidad de fallo, este es el capital que deberías tener listo para asegurar el fondeo.")
        
        kpi2.metric("Primer Retiro Promedio", f"${int(stats['avg_payout'])}",
                   help="Si logras cobrar, este es el monto estimado (incluyendo reembolso + profit split).")
        
        kpi3.metric("Expectativa Matemática (EV)", f"{'✅ Rentable' if stats['ev_net']>0 else '❌ No Rentable'}", 
                   delta=roi_delta, delta_color=roi_color)

        # --- SECCIÓN 2: EL EMBUDO (Visualización Simple) ---
        st.subheader("2. El Embudo de Probabilidad (1,000 Traders)")
        st.caption("Si 1,000 traders operan con tu sistema, este sería su destino:")
        
        # Datos para gráfico de barras simple
        funnel_data = pd.DataFrame({
            "Etapa": ["1. Pierden Fase 1", "2. Pierden Fase 2", "3. Pierden Fondeada", "4. 🎉 LOGRAN RETIRO"],
            "Cantidad": [stats['fail_p1'], stats['fail_p2'], stats['fail_funded'], stats['success']]
        }).set_index("Etapa")
        
        # Usamos colores personalizados si es posible, sino default
        st.bar_chart(funnel_data, color="#2ecc71") # Verde genérico, pero el gráfico ayuda mucho

        # --- SECCIÓN 3: PROBABILIDADES CLAVE ---
        st.divider()
        col_p1, col_p2 = st.columns(2)
        
        col_p1.info(f"""
        **🎯 Probabilidad de Fondeo: {stats['prob_funded']:.1f}%**
        Es la probabilidad de pasar todas las fases de evaluación.
        """)
        
        col_p2.success(f"""
        **💸 Probabilidad de Cobrar: {stats['prob_payout']:.1f}%**
        Es la probabilidad real de que este dinero retorne a tu bolsillo.
        *(Incluye pasar las pruebas + sobrevivir el primer mes)*.
        """)

    st.divider()
    with st.expander("📜 Historial de Análisis"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob Payout %", "Costo Real $", "Fecha"]), use_container_width=True)