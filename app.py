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
st.set_page_config(page_title="Prop Firm Portfolio Pro", page_icon="📈", layout="wide")

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
    if not engine: return "Error: Sin conexión a Base de Datos"
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

# --- DATOS COMPLETOS DE EMPRESAS ---
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
def simulate_phase(balance, risk_pct, win_rate, rr, target_pct, max_dd_pct, comm, sl_min, sl_max, is_funded=False):
    curr = balance
    start_balance = balance
    target_equity = balance + (balance * (target_pct/100))
    limit_equity = balance - (balance * (max_dd_pct/100))
    trades = 0
    max_trades = 1500 
    pip_val = 10
    
    while curr > limit_equity and curr < target_equity and trades < max_trades:
        trades += 1
        current_sl = random.uniform(sl_min, sl_max)
        risk_money = start_balance * (risk_pct / 100) 
        lot_size = risk_money / (current_sl * pip_val)
        trade_comm = lot_size * comm
        
        if random.random() < (win_rate/100):
            profit = (risk_money * rr) - trade_comm
            curr += profit
        else:
            loss = risk_money + trade_comm
            curr -= loss
            
    return curr >= target_equity, trades, curr

def run_account_simulation(account_data, strategy_params):
    wr = strategy_params['win_rate']
    rr = strategy_params['rr']
    risk = strategy_params['risk']
    w_target = strategy_params['withdrawal_target']
    comm = strategy_params['comm']
    trades_day = strategy_params['trades_day']
    
    sl_min = 5; sl_max = 15 
    firm = account_data
    n_sims = 800
    
    pass_p1 = 0; pass_p2 = 0; pass_cash = 0
    total_trades = 0
    
    is_2step = firm.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        sim_trades = 0
        
        # FASE 1
        ok1, t1, _ = simulate_phase(firm['size'], risk, wr, rr, firm['profit_p1'], firm['total_dd'], comm, sl_min, sl_max)
        sim_trades += t1
        if not ok1: continue
        pass_p1 += 1
        
        # FASE 2
        if is_2step:
            ok2, t2, _ = simulate_phase(firm['size'], risk, wr, rr, firm['profit_p2'], firm['total_dd'], comm, sl_min, sl_max)
            sim_trades += t2
            if not ok2: continue
            pass_p2 += 1
        else:
            pass_p2 += 1
            
        # FASE FONDEADA
        ok_fund, t3, final_bal = simulate_phase(firm['size'], risk, wr, rr, w_target, firm['total_dd'], comm, sl_min, sl_max, is_funded=True)
        sim_trades += t3
        if ok_fund:
            pass_cash += 1
            total_trades += sim_trades

    # Estadísticas
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 # Probabilidad absoluta
    prob_cash = (pass_cash/n_sims)*100
    
    # --- CÁLCULO PAYOUT EXACTO ---
    # Usamos la meta estricta del usuario para la proyección financiera
    # Profit Bruto = Capital * Meta %
    gross_profit_projected = firm['size'] * (w_target / 100)
    
    # Profit Split (80%)
    net_split_projected = gross_profit_projected * 0.80
    
    # Total Payout = Split + Refund + Bonus
    estimated_payout = net_split_projected + firm['cost'] + firm.get('p1_bonus', 0)
    
    # Desglose para tooltip
    breakdown = {
        "split": net_split_projected,
        "refund": firm['cost'],
        "bonus": firm.get('p1_bonus', 0)
    }
    
    avg_trades = total_trades / pass_cash if pass_cash > 0 else 0
    attempts = 100/prob_cash if prob_cash > 0 else 100
    inventory = math.ceil(attempts)
    investment = inventory * firm['cost']
    
    days = avg_trades / trades_day if trades_day > 0 else 0
    months = days / 20
    
    salary = (estimated_payout - investment) / months if months > 0 else 0
    
    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, "prob_cash": prob_cash,
        "inventory": inventory, "investment": investment,
        "payout": estimated_payout, "salary": salary, "months": months,
        "is_2step": is_2step, "breakdown": breakdown
    }

# --- INTERFAZ ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Portfolio Manager")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        tab_login, tab_reg = st.tabs(["Iniciar Sesión", "Registrarse"])
        
        with tab_login:
            with st.form("login_form"):
                u = st.text_input("Usuario")
                p = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)
                if submit:
                    if login_user(u, p):
                        st.session_state['logged_in'] = True; st.session_state['username'] = u; st.rerun()
                    else: st.error("❌ Credenciales incorrectas")

        with tab_reg:
            with st.form("register_form"):
                nu = st.text_input("Nuevo Usuario")
                np = st.text_input("Nueva Contraseña", type="password")
                submit_reg = st.form_submit_button("Crear Cuenta", use_container_width=True)
                if submit_reg:
                    if nu and np:
                        msg = register_user(nu, np)
                        if msg == "OK": st.success("✅ Cuenta creada.")
                        else: st.error(f"❌ Error: {msg}")

else:
    # --- APP PRINCIPAL ---
    col_logo, col_user = st.columns([3,1])
    col_logo.title("💼 Portfolio Manager")
    col_user.write(f"Operador: **{st.session_state['username']}**")
    if col_user.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")
    
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("1. Agregar Cuenta")
        
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        
        # --- VISUALIZACIÓN DE REGLAS MEJORADA ---
        sel_data = FIRMS_DATA[s_firm][s_prog][s_size]
        is_2s = sel_data.get('profit_p2', 0) > 0
        
        st.info("ℹ️ **Reglas del Desafío**")
        st.markdown(f"""
        * **Costo:** `${sel_data['cost']}`
        * **Tamaño:** `${sel_data['size']:,}`
        * **DD Máximo:** `{sel_data['total_dd']}%`
        * **DD Diario:** `{sel_data.get('daily_dd', 'N/A')}%`
        * **Objetivo F1:** `{sel_data['profit_p1']}%`
        * **Objetivo F2:** `{'{}%'.format(sel_data['profit_p2']) if is_2s else 'N/A'}`
        * **Bonus Fondeo:** `${sel_data.get('p1_bonus', 0)}`
        * **Profit Split:** `80%` (Estándar)
        * **Reembolso:** `100%` en 1er Payout
        """)
        
        if st.button("➕ Añadir al Portafolio", type="primary", use_container_width=True):
            new_item = {
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": sel_data,
                "params": { 
                    "win_rate": 45, "rr": 2.0, "risk": 1.0, 
                    "withdrawal_target": 1.0, "trades_day": 3, "comm": 7.0
                }
            }
            st.session_state['portfolio'].append(new_item)
            st.toast("Cuenta agregada")

    # --- BODY ---
    if not st.session_state['portfolio']:
        st.info("👈 Tu portafolio está vacío. Agrega cuentas desde la barra lateral.")
    else:
        # 1. CONFIGURACIÓN
        st.subheader(f"🎛️ Configuración de Operativa ({len(st.session_state['portfolio'])} Cuentas)")
        
        for i, item in enumerate(st.session_state['portfolio']):
            with st.expander(f"⚙️ {item['full_name']} - Editar Parámetros", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                k = str(item['id'])
                
                # Fila 1
                item['params']['win_rate'] = c1.number_input("WinRate %", 10, 90, item['params']['win_rate'], key=f"wr_{k}")
                item['params']['rr'] = c2.number_input("Ratio R:R", 0.1, 10.0, item['params']['rr'], step=0.1, key=f"rr_{k}")
                item['params']['risk'] = c3.number_input("Riesgo %", 0.1, 5.0, item['params']['risk'], step=0.1, key=f"rk_{k}")
                item['params']['withdrawal_target'] = c4.number_input("Meta Retiro %", 0.5, 20.0, item['params']['withdrawal_target'], step=0.5, key=f"wt_{k}", help="Calcularemos el payout basado en este % exacto.")

                # Fila 2
                c5, c6, c7 = st.columns([1, 1, 2])
                item['params']['trades_day'] = c5.number_input("Trades/Día", 1, 50, item['params']['trades_day'], step=1, key=f"td_{k}")
                item['params']['comm'] = c6.number_input("Comisión ($)", 0.0, 20.0, item['params']['comm'], step=0.5, key=f"cm_{k}")
                
                if c7.button("🗑️ Eliminar Cuenta", key=f"del_{k}"):
                    st.session_state['portfolio'].pop(i)
                    st.rerun()

        st.divider()
        
        # 2. SIMULACIÓN
        if st.button("🚀 Ejecutar Simulación de Portafolio", type="primary", use_container_width=True):
            
            with st.spinner("Simulando escenarios..."):
                global_inv = 0; global_sal = 0
                results = []
                
                for item in st.session_state['portfolio']:
                    stats = run_account_simulation(item['data'], item['params'])
                    global_inv += stats['investment']
                    global_sal += stats['salary']
                    results.append({"name": item['full_name'], "stats": stats, "params": item['params']})
                
                save_plan(st.session_state['username'], f"{len(results)} Cuentas", global_inv, global_sal)

            # 3. RESULTADOS GLOBALES
            st.markdown("### 🌍 Resultados Consolidados")
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Capital de Riesgo Total", f"${global_inv:,.0f}")
            kc2.metric("Flujo Mensual Neto", f"${global_sal:,.0f}")
            roi = (global_sal * 12 / global_inv * 100) if global_inv > 0 else 0
            kc3.metric("ROI Anual", f"{roi:.1f}%")

            # 4. DESGLOSE DETALLADO
            st.subheader("🔍 Desglose Detallado")
            
            for res in results:
                s = res['stats']
                bk = s['breakdown']
                status = "🟢" if s['salary'] > 0 else "🔴"
                
                with st.expander(f"{status} {res['name']} | Prob. Cobro: {s['prob_cash']:.1f}% | Sueldo: ${s['salary']:,.0f}", expanded=False):
                    
                    # Embudo
                    st.caption("🔻 Embudo de Fases")
                    ec1, ec2, ec3 = st.columns(3)
                    ec1.metric("1. Fase 1", f"{s['prob_p1']:.1f}%")
                    
                    # Lógica Visual Fase 2 corregida
                    label_p2 = f"{s['prob_p2']:.1f}%" if s['is_2step'] else "N/A"
                    ec2.metric("2. Fase 2", label_p2)
                    
                    ec3.metric("3. Payout", f"{s['prob_cash']:.1f}%")
                    
                    st.divider()
                    
                    # Datos Financieros con Tooltip de Desglose
                    fc1, fc2, fc3, fc4 = st.columns(4)
                    fc1.metric("Stock Sugerido", f"{s['inventory']} Cuentas")
                    fc2.metric("Inversión", f"${s['investment']:,.0f}")
                    
                    # Tooltip Payout
                    payout_tooltip = f"""
                    Desglose Payout:
                    + Profit Split (80%): ${bk['split']:,.2f}
                    + Reembolso Fee: ${bk['refund']}
                    + Bonus F1: ${bk['bonus']}
                    -------------------
                    Total: ${s['payout']:,.2f}
                    """
                    fc3.metric("1er Retiro Est.", f"${s['payout']:,.0f}", help=payout_tooltip)
                    fc4.metric("Tiempo", f"{s['months']:.1f} Meses")

    st.divider()
    with st.expander("📜 Historial"):
        h = get_history(st.session_state.get('username',''))
        if h: st.dataframe(pd.DataFrame(h, columns=["Resumen", "Inv Total", "Sueldo Total", "Fecha"]))