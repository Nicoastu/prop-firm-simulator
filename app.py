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
st.set_page_config(page_title="Prop Firm Business Portfolio", page_icon="💼", layout="wide")

# --- GESTIÓN DE ESTADO ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''
if 'portfolio' not in st.session_state:
    st.session_state['portfolio'] = [] 

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
                    portfolio_summary TEXT,
                    total_investment FLOAT,
                    total_salary FLOAT,
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

def save_plan_db(username, summary, inv, salary):
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO plans (username, portfolio_summary, total_investment, total_salary)
                    VALUES (:u, :s, :i, :sal)
                """), {"u": username, "s": summary, "i": inv, "sal": salary})
                conn.commit()
        except: pass

def get_user_plans(username):
    if not engine: return []
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT portfolio_summary, total_investment, total_salary, created_at FROM plans WHERE username = :u ORDER BY created_at DESC LIMIT 10"), {"u": username})
            return result.fetchall()
    except: return []

if engine: init_db()

# --- DATOS DE EMPRESAS ---
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
def simulate_phase(balance, risk_money, win_rate, rr, profit_target_pct, max_total_dd_pct, comm_per_lot, pip_val, sl_min, sl_max, is_funded=False, withdrawal_target=None):
    curr = balance
    
    # DEFINICIÓN DE OBJETIVO (TARGET)
    if is_funded:
        # En fase fondeada, el target es el % de retiro que el usuario quiere alcanzar
        target_equity = balance + (balance * (withdrawal_target/100))
    else:
        # En fases de evaluación, es el objetivo de la firma
        target_equity = balance + (balance * (profit_target_pct/100))
        
    limit_equity = balance - (balance * (max_total_dd_pct/100))
    trades = 0
    max_trades_allowed = 2000 
    
    while curr > limit_equity and curr < target_equity and trades < max_trades_allowed:
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

def run_business_simulation(firm_data, risk_pct, win_rate, rr, trades_per_day, comm, sl_min, sl_max, withdrawal_pct):
    n_sims = 1000
    pass_payout = 0 
    
    total_trades_accum = []
    total_payout_amount = 0
    
    balance = firm_data['size']
    risk_money = balance * (risk_pct / 100)
    pip_val = 10 
    is_two_step = firm_data.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        sim_trades = 0
        
        # 1. FASE 1
        p1_ok, t1, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p1'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
        sim_trades += t1
        if not p1_ok: 
            total_trades_accum.append(sim_trades)
            continue
            
        # 2. FASE 2
        if is_two_step:
            p2_ok, t2, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p2'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
            sim_trades += t2
            if not p2_ok: 
                total_trades_accum.append(sim_trades)
                continue
        
        # 3. FASE FONDEADA (Target = Withdrawal %)
        funded_ok, t3, final_balance = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True, withdrawal_target=withdrawal_pct)
        sim_trades += t3
        total_trades_accum.append(sim_trades)
        
        if funded_ok:
            pass_payout += 1
            # El profit es exactamente lo que el usuario definió como objetivo de retiro (o un poco más por el salto del último trade)
            profit = final_balance - balance
            
            # Profit Split estándar 80% (Para simplificar MVP, aunque algunas dan 90%)
            payout_val = (profit * 0.8) + firm_data['cost'] + firm_data.get('p1_bonus', 0)
            total_payout_amount += payout_val

    prob_cash = (pass_payout / n_sims) * 100
    
    # Tiempo
    avg_trades_total = sum(total_trades_accum) / len(total_trades_accum) if total_trades_accum else 0
    total_trading_days = avg_trades_total / trades_per_day if trades_per_day > 0 else 999
    months_to_liquidity = total_trading_days / 20 
    
    # Dinero
    avg_first_payout = total_payout_amount / pass_payout if pass_payout > 0 else 0
    attempts_needed = 100 / prob_cash if prob_cash > 0 else 100
    inventory_needed = math.ceil(attempts_needed) 
    total_investment = inventory_needed * firm_data['cost']
    
    net_profit = avg_first_payout - total_investment
    monthly_salary_equiv = net_profit / months_to_liquidity if months_to_liquidity > 0 else 0

    return {
        "prob_cash": prob_cash, "inventory": inventory_needed, "investment": total_investment,
        "months_time": months_to_liquidity, "first_payout": avg_first_payout,
        "net_profit": net_profit, "monthly_salary": monthly_salary_equiv, "trading_days_total": total_trading_days,
        "raw_cost": firm_data['cost']
    }

# --- FRONTEND ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Business Planner")
    # (Login Code)
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
            if msg == "OK": st.success("Creado.")
            else: st.error(msg)
else:
    # --- DASHBOARD DE PORTAFOLIO ---
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("💼 Prop Firm Portfolio Planner")
    col_h2.write(f"Trader: **{st.session_state['username']}**")
    if col_h2.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # --- SIDEBAR: TU HABILIDAD (GLOBAL) ---
    st.sidebar.header("1. Tu Estrategia (Global)")
    
    trades_day = st.sidebar.number_input("Trades por Día", min_value=1, max_value=50, value=3, step=1)
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0, step=0.1, format="%.1f")
    risk = st.sidebar.slider("Riesgo por Trade (%)", 0.1, 3.0, 1.0, step=0.1, format="%.1f")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**💰 Objetivo de Cobro**")
    withdrawal_pct = st.sidebar.slider("Quiero retirar al (%)", 1.0, 10.0, 3.0, step=0.5, 
                                     help="¿A qué % de beneficio solicitas el retiro? (Ej: Retirar cada 3%)")
    
    st.sidebar.divider()
    st.sidebar.header("2. Agregar Cuentas")
    
    sel_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    sel_program = st.sidebar.selectbox("Programa", list(FIRMS_DATA[sel_company].keys()))
    sel_size = st.sidebar.selectbox("Capital", list(FIRMS_DATA[sel_company][sel_program].keys()))
    
    # Botón Agregar
    if st.sidebar.button("➕ Agregar al Carrito"):
        firm_details = FIRMS_DATA[sel_company][sel_program][sel_size]
        item_id = int(time.time() * 1000) # ID único simple
        item = {
            "name": f"{sel_company} {sel_program} ({sel_size})",
            "data": firm_details,
            "id": item_id
        }
        st.session_state['portfolio'].append(item)
        st.success("Cuenta agregada.")

    # --- ÁREA PRINCIPAL ---
    
    # 1. MOSTRAR PORTAFOLIO EDITABLE
    if len(st.session_state['portfolio']) == 0:
        st.info("👈 Tu portafolio está vacío. Agrega cuentas desde la barra lateral.")
    else:
        st.subheader(f"📦 Tu Portafolio ({len(st.session_state['portfolio'])} cuentas)")
        
        # Iteramos para mostrar y permitir borrar
        for idx, item in enumerate(st.session_state['portfolio']):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                c1.markdown(f"**{item['name']}**")
                c2.caption(f"Costo: ${item['data']['cost']}")
                c3.caption(f"DD: {item['data']['total_dd']}%")
                
                # Botón de borrar con clave única
                if c4.button("🗑️", key=f"del_{item['id']}"):
                    st.session_state['portfolio'].pop(idx)
                    st.rerun()
        
        st.divider()

        # 2. BOTÓN DE SIMULACIÓN
        if st.button("🚀 Simular Viabilidad del Portafolio", type="primary", use_container_width=True):
            
            with st.spinner("Ejecutando simulaciones masivas con tu objetivo de retiro..."):
                
                # VARS GLOBALES
                global_investment = 0
                global_monthly_salary = 0
                global_net_profit = 0
                portfolio_results = []
                
                # INPUTS DE COSTOS VARIOS
                comm = 7.0 
                sl_min = 5
                sl_max = 15
                
                for item in st.session_state['portfolio']:
                    stats = run_business_simulation(item['data'], risk, wr, rr, trades_day, comm, sl_min, sl_max, withdrawal_pct)
                    
                    global_investment += stats['investment']
                    global_monthly_salary += stats['monthly_salary']
                    global_net_profit += stats['net_profit']
                    
                    portfolio_results.append({
                        "name": item['name'],
                        "stats": stats
                    })
                
                # Guardar
                summary_txt = f"{len(portfolio_results)} Cuentas | Retiro Obj: {withdrawal_pct}%"
                save_plan_db(st.session_state['username'], summary_txt, global_investment, global_monthly_salary)

            # A. RESULTADOS GLOBALES
            st.markdown("### 🌍 Resultados del Imperio (Consolidado)")
            
            g_col1, g_col2, g_col3 = st.columns(3)
            
            g_col1.metric("Capital Riesgo Total", f"${global_investment:,.0f}", 
                         help="Suma total del presupuesto de seguridad para todas las cuentas.")
            
            g_col2.metric("Sueldo Mensual Proyectado", f"${global_monthly_salary:,.0f} / mes", 
                         help="Beneficio neto mensualizado sumando todas las fuentes.")
            
            roi_color = "normal" if global_net_profit > 0 else "inverse"
            g_col3.metric("Beneficio Neto Total", f"${global_net_profit:,.0f}", 
                         delta_color=roi_color)
            
            st.caption(f"Simulación basada en retirar siempre el **{withdrawal_pct}%** del capital.")

            # B. DETALLE POR CUENTA
            st.subheader("🔍 Detalle Individual")
            
            for res in portfolio_results:
                s = res['stats']
                # Título dinámico
                status_icon = "🟢" if s['monthly_salary'] > 0 else "🔴"
                
                with st.expander(f"{status_icon} {res['name']} - Prob. Cobro: {s['prob_cash']:.1f}%"):
                    d1, d2, d3 = st.columns(3)
                    d1.metric("Stock Necesario", f"{s['inventory']} Intentos", f"Inv: ${s['investment']}")
                    d2.metric("Payout Estimado", f"${s['first_payout']:,.0f}", f"Objetivo: {withdrawal_pct}%")
                    d3.metric("Aporte al Sueldo", f"${s['monthly_salary']:,.0f}", f"Tiempo: {s['months_time']:.1f} Meses")

    st.divider()
    with st.expander("📜 Historial"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Resumen", "Inversión Total", "Sueldo Total", "Fecha"]), use_container_width=True)