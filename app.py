import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time
import math

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Prop Firm Portfolio Pro", page_icon="📊", layout="wide")

# --- GESTIÓN DE ESTADO ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''
if 'portfolio' not in st.session_state: st.session_state['portfolio'] = [] 

# --- BASE DE DATOS ---
db_url = os.getenv("DATABASE_URL")
engine = None
if db_url:
    try:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url)
    except: pass

def init_db():
    if engine:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, auth_type TEXT DEFAULT 'manual');"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS plans (id SERIAL PRIMARY KEY, username TEXT, portfolio_summary TEXT, total_investment FLOAT, total_salary FLOAT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"))
            conn.commit()

# --- AUTENTICACIÓN ---
def register_user(u, p):
    if not engine: return "Error: Sin conexión a BD (Modo Local)"
    try:
        with engine.connect() as conn:
            if conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": u}).fetchone(): return "El usuario ya existe"
            conn.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u, "p": p})
            conn.commit()
            return "OK"
    except Exception as e: return f"Error DB: {str(e)}"

def login_user(u, p):
    if not engine: return False 
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT password FROM users WHERE username = :u"), {"u": u}).fetchone()
            return res and res[0] == p
    except: return False

def save_plan(u, summary, inv, salary):
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO plans (username, portfolio_summary, total_investment, total_salary) VALUES (:u, :s, :i, :sal)"), {"u": u, "s": summary, "i": inv, "sal": salary})
                conn.commit()
        except: pass

def get_history(u):
    if not engine: return []
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT portfolio_summary, total_investment, total_salary, created_at FROM plans WHERE username = :u ORDER BY created_at DESC LIMIT 10"), {"u": u}).fetchall()
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
def simulate_phase(initial_balance, current_balance, risk_pct, win_rate, rr, target_pct, max_dd_pct, daily_dd_pct, comm, sl_min, sl_max, trades_per_day, is_funded=False):
    curr = current_balance
    target_equity = initial_balance + (initial_balance * (target_pct/100))
    static_limit = initial_balance - (initial_balance * (max_dd_pct/100))
    
    trades = 0
    max_trades = 1500 
    pip_val = 10
    
    day_start_equity = curr
    trades_today = 0
    
    while curr > static_limit and curr < target_equity and trades < max_trades:
        trades += 1
        trades_today += 1
        
        if trades_today > trades_per_day:
            day_start_equity = curr 
            trades_today = 1        
            
        daily_loss_limit = day_start_equity * (daily_dd_pct / 100)
        
        current_sl = random.uniform(sl_min, sl_max)
        risk_money = initial_balance * (risk_pct / 100) 
        
        lot_size = risk_money / (current_sl * pip_val)
        trade_comm = lot_size * comm
        
        slippage = random.uniform(0.95, 1.05) 
        is_error = random.random() < 0.01 
        
        if random.random() < (win_rate/100):
            profit = (risk_money * rr * slippage) - trade_comm
            curr += profit
        else:
            loss_amount = (risk_money * slippage) + trade_comm
            if is_error: loss_amount *= 1.5 
            curr -= loss_amount
            
        if curr <= static_limit:
            return False, trades, curr
            
        current_daily_drawdown = day_start_equity - curr
        if current_daily_drawdown >= daily_loss_limit:
            return False, trades, curr
            
    return curr >= target_equity, trades, curr

def run_account_simulation(account_data, strategy_params, n_sims_requested):
    wr = strategy_params['win_rate']
    rr = strategy_params['rr']
    risk = strategy_params['risk']
    w_target = strategy_params['withdrawal_target']
    comm = strategy_params['comm']
    trades_day = strategy_params['trades_day']
    
    sl_min = 5; sl_max = 15 
    firm = account_data
    n_sims = n_sims_requested
    
    daily_dd = firm.get('daily_dd', 100.0)
    
    pass_p1 = 0; pass_p2 = 0
    pass_c1 = 0; pass_c2 = 0; pass_c3 = 0
    
    # Acumuladores de Dinero (Estrictos al Target)
    sum_pay1 = 0
    sum_pay2 = 0
    sum_pay3 = 0
    
    is_2step = firm.get('profit_p2', 0) > 0
    
    # --- CÁLCULO DE PAYOUT FIJO SEGÚN TARGET USUARIO ---
    # Esto asegura que el simulador respete el 3% exacto si el usuario pide 3%
    profit_target_amount = firm['size'] * (w_target / 100)
    
    # Profit Split (80%)
    net_split_share = profit_target_amount * 0.80
    
    # Payouts Fijos Teóricos
    payout_val_1 = net_split_share + firm['cost'] + firm.get('p1_bonus', 0)
    payout_val_2 = net_split_share # Solo split
    payout_val_3 = net_split_share
    
    for _ in range(n_sims):
        # FASE 1
        ok1, _, bal1 = simulate_phase(firm['size'], firm['size'], risk, wr, rr, firm['profit_p1'], firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
        if not ok1: continue
        pass_p1 += 1
        
        # FASE 2
        if is_2step:
            ok2, _, bal2 = simulate_phase(firm['size'], firm['size'], risk, wr, rr, firm['profit_p2'], firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
            if not ok2: continue
            pass_p2 += 1
        else:
            pass_p2 += 1
            
        # RETIRO 1
        ok_c1, _, _ = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
        if ok_c1:
            pass_c1 += 1
            sum_pay1 += payout_val_1 # Sumamos el valor exacto del target, no el overshoot
            
            # RETIRO 2
            ok_c2, _, _ = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
            if ok_c2:
                pass_c2 += 1
                sum_pay2 += payout_val_2
                
                # RETIRO 3
                ok_c3, _, _ = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
                if ok_c3:
                    pass_c3 += 1
                    sum_pay3 += payout_val_3

    # Probabilidades
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 if is_2step else 100.0
    prob_c1 = (pass_c1/n_sims)*100
    prob_c2 = (pass_c2/n_sims)*100
    prob_c3 = (pass_c3/n_sims)*100
    
    # Financials
    if prob_c1 >= 98.0: attempts = 1.0 
    else: attempts = 100/prob_c1 if prob_c1 > 0 else 100
        
    inventory = math.ceil(attempts)
    investment = inventory * firm['cost']
    
    avg_pay1 = sum_pay1 / pass_c1 if pass_c1 > 0 else 0
    avg_pay2 = sum_pay2 / pass_c2 if pass_c2 > 0 else 0
    avg_pay3 = sum_pay3 / pass_c3 if pass_c3 > 0 else 0
    
    salary = (avg_pay1 - investment) 
    
    # Breakdown visual del Payout 1 (Coincidirá con avg_pay1)
    est_pay_breakdown = {
        "split": net_split_share,
        "refund": firm['cost'],
        "bonus": firm.get('p1_bonus', 0),
        "total": payout_val_1
    }
    
    months_time = 3.0 if is_2step else 2.0 
    
    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, 
        "prob_c1": prob_c1, "prob_c2": prob_c2, "prob_c3": prob_c3,
        "avg_pay1": avg_pay1, "avg_pay2": avg_pay2, "avg_pay3": avg_pay3,
        "inventory": inventory, "investment": investment,
        "net_profit": salary, "months": months_time,
        "is_2step": is_2step,
        "first_pay_breakdown": est_pay_breakdown
    }

# --- INTERFAZ ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Portfolio Manager")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        tab_login, tab_reg = st.tabs(["Entrar", "Registrar"])
        with tab_login:
            with st.form("login"):
                u = st.text_input("Usuario"); p = st.text_input("Clave", type="password")
                if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
                    if login_user(u, p): st.session_state['logged_in']=True; st.session_state['username']=u; st.rerun()
                    else: st.error("Error credenciales")
        with tab_reg:
            with st.form("register"):
                nu = st.text_input("Usuario"); np = st.text_input("Clave", type="password")
                if st.form_submit_button("Crear Cuenta", use_container_width=True):
                    if nu and np: 
                        r = register_user(nu, np)
                        if r=="OK": st.success("Creado");
                        else: st.error(r)
else:
    c_head, c_user = st.columns([4,1])
    c_head.title("💼 Gestor de Portafolio Pro")
    c_user.write(f"👤 **{st.session_state['username']}**")
    if c_user.button("Salir"): st.session_state['logged_in']=False; st.rerun()
    st.markdown("---")
    
    with st.sidebar:
        st.header("1. Configuración Global")
        sim_precision = st.select_slider("Precisión", options=[500, 1000, 5000], value=1000, format_func=lambda x: f"{x} Escenarios")
        st.divider()
        st.header("2. Agregar Activos")
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        d = FIRMS_DATA[s_firm][s_prog][s_size]
        is_2s = d.get('profit_p2', 0) > 0
        
        with st.container(border=True):
            st.markdown(f"**📜 Reglas: {s_firm} {s_size}**")
            c1, c2 = st.columns(2)
            c1.markdown(f"💰 Costo: **${d['cost']}**")
            c2.markdown(f"📉 DD Max: **{d['total_dd']}%**")
            c3, c4 = st.columns(2)
            c3.markdown(f"📉 Diario: **{d.get('daily_dd', 'N/A')}%**")
            c4.markdown(f"🎁 Bonus: **${d.get('p1_bonus', 0)}**")
            st.markdown(f"🎯 **Target:** F1: `{d['profit_p1']}%` | F2: `{'{}%'.format(d['profit_p2']) if is_2s else 'N/A'}`")

        if st.button("➕ Agregar al Portafolio", type="primary", use_container_width=True):
            st.session_state['portfolio'].append({
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": d,
                "params": {"win_rate": 45, "rr": 2.0, "risk": 1.0, "withdrawal_target": 3.0, "trades_day": 3, "comm": 7.0}
            })
            st.toast("Activo agregado")

    if not st.session_state['portfolio']:
        st.info("👈 Tu portafolio está vacío. Comienza agregando cuentas.")
    else:
        st.subheader(f"🎛️ Configuración ({len(st.session_state['portfolio'])} Activos)")
        for i, item in enumerate(st.session_state['portfolio']):
            with st.expander(f"⚙️ {item['full_name']}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                k = str(item['id'])
                item['params']['win_rate'] = c1.number_input("WR %", 10, 90, item['params']['win_rate'], key=f"w{k}")
                item['params']['rr'] = c2.number_input("R:R", 0.5, 10.0, item['params']['rr'], step=0.1, key=f"r{k}")
                item['params']['risk'] = c3.number_input("Riesgo %", 0.1, 5.0, item['params']['risk'], step=0.1, key=f"rk{k}")
                item['params']['withdrawal_target'] = c4.number_input("Meta Retiro %", 0.5, 20.0, item['params']['withdrawal_target'], step=0.5, key=f"wt{k}")
                c5, c6, c7 = st.columns([1,1,2])
                item['params']['trades_day'] = c5.number_input("Trades/Día", 1, 50, item['params']['trades_day'], key=f"td{k}")
                item['params']['comm'] = c6.number_input("Comisión ($)", 0.0, 20.0, item['params']['comm'], key=f"cm{k}")
                if c7.button("Eliminar", key=f"d{k}"): 
                    st.session_state['portfolio'].pop(i)
                    st.rerun()
        
        st.divider()
        if st.button(f"🚀 Simular Portafolio ({sim_precision} Escenarios)", type="primary", use_container_width=True):
            with st.spinner(f"Procesando simulaciones detalladas..."):
                results = []
                g_inv = 0; g_net = 0
                
                # Acumuladores globales para flujos combinados
                g_pay1 = 0; g_pay2 = 0; g_pay3 = 0
                
                for item in st.session_state['portfolio']:
                    s = run_account_simulation(item['data'], item['params'], sim_precision)
                    g_inv += s['investment']; g_net += s['net_profit']
                    
                    # Sumamos al flujo combinado ponderado por probabilidad
                    # (Mostramos el potencial total si todo sale bien, o ponderado? 
                    # Tu pedido fue "Proyeccion de Flujo", usualmente se muestra el potencial de éxito)
                    g_pay1 += s['avg_pay1']
                    g_pay2 += s['avg_pay2']
                    g_pay3 += s['avg_pay3']
                    
                    results.append({"name": item['full_name'], "stats": s})
                
                save_plan(st.session_state['username'], f"{len(results)} Cuentas", g_inv, g_net)
                
                # --- RESULTADOS CONSOLIDADOS ---
                st.markdown("### 📊 Resultados Consolidados")
                m1, m2, m3 = st.columns(3)
                m1.metric("Inversión Total (Riesgo)", f"${g_inv:,.0f}")
                m2.metric("Beneficio Neto (Ciclo 1)", f"${g_net:,.0f}")
                roi = (g_net / g_inv * 100) if g_inv > 0 else 0
                m3.metric("ROI Potencial", f"{roi:.1f}%")
                
                # --- NUEVA SECCIÓN: FLUJO COMBINADO ---
                st.markdown("### 💰 Proyección de Flujo de Caja Combinado")
                st.caption("Suma de retiros esperados si todas las cuentas del portafolio tienen éxito.")
                fc1, fc2, fc3 = st.columns(3)
                fc1.metric("Total Retiro 1", f"${g_pay1:,.0f}", help="Suma de primeros retiros (incluye reembolsos y bonus).")
                fc2.metric("Total Retiro 2", f"${g_pay2:,.0f}", help="Suma de segundos retiros (solo split).")
                fc3.metric("Total Retiro 3", f"${g_pay3:,.0f}", help="Suma de terceros retiros (solo split).")
                
                st.divider()

                # --- DESGLOSE INDIVIDUAL ---
                st.subheader("🔍 Detalle de Retención por Cuenta")
                for res in results:
                    s = res['stats']
                    bk = s['first_pay_breakdown']
                    with st.expander(f"📈 {res['name']} (Prob. 1er Cobro: {s['prob_c1']:.1f}%)"):
                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("1. Fase 1", f"{s['prob_p1']:.1f}%")
                        c2.metric("2. Fase 2", f"{s['prob_p2']:.1f}%" if s['is_2step'] else "N/A")
                        
                        # MONTOS EN VERDE
                        c3.metric("3. Retiro 1", f"{s['prob_c1']:.1f}%", f"${s['avg_pay1']:,.0f}")
                        c4.metric("4. Retiro 2", f"{s['prob_c2']:.1f}%", f"${s['avg_pay2']:,.0f}")
                        c5.metric("5. Retiro 3", f"{s['prob_c3']:.1f}%", f"${s['avg_pay3']:,.0f}")
                        
                        st.markdown("---")
                        st.caption("💰 **Desglose del 1er Payout (Teórico según Meta):**")
                        col_pay1, col_pay2, col_pay3, col_pay4 = st.columns(4)
                        col_pay1.metric("Split", f"${bk['split']:,.0f}")
                        col_pay2.metric("Refund", f"+${bk['refund']}")
                        col_pay3.metric("Bonus", f"+${bk['bonus']}")
                        col_pay4.metric("TOTAL", f"${bk['total']:,.0f}", delta="Neto")

    st.divider()
    with st.expander("Historial"):
        h = get_history(st.session_state.get('username',''))
        if h: st.dataframe(pd.DataFrame(h))