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

# --- FUNCIONES DE AUTENTICACIÓN (REPARADAS) ---
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

# --- DATOS COMPLETOS DE EMPRESAS (REGLAS RESTAURADAS) ---
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
    
    # Objetivos
    target_equity = balance + (balance * (target_pct/100))
    limit_equity = balance - (balance * (max_dd_pct/100))
    
    trades = 0
    max_trades = 1500 
    pip_val = 10
    
    while curr > limit_equity and curr < target_equity and trades < max_trades:
        trades += 1
        
        # Dinámica operativa
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

def run_account_simulation(account_data, strategy_params, global_ops):
    # Desempaquetar estrategia específica
    wr = strategy_params['win_rate']
    rr = strategy_params['rr']
    risk = strategy_params['risk']
    w_target = strategy_params['withdrawal_target']
    
    # Inputs globales (Operativa del Trader)
    comm = global_ops['comm']
    trades_day = global_ops['trades_day']
    sl_min = 5; sl_max = 15 # Simplificado para MVP, pero podría ser input
    
    firm = account_data
    n_sims = 800
    
    pass_p1 = 0; pass_p2 = 0; pass_cash = 0
    total_payouts = 0
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
            
            # Cálculo Payout (Profit + Refund + Bonus)
            gross_profit = final_bal - firm['size']
            net_profit_share = gross_profit * 0.80 # Split genérico 80%
            total_pay = net_profit_share + firm['cost'] + firm.get('p1_bonus', 0)
            total_payouts += total_pay

    # Métricas
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 if is_2step else 100.0
    prob_cash = (pass_cash/n_sims)*100
    
    avg_payout = total_payouts / pass_cash if pass_cash > 0 else 0
    avg_trades = total_trades / pass_cash if pass_cash > 0 else 0
    
    attempts = 100/prob_cash if prob_cash > 0 else 100
    inventory = math.ceil(attempts)
    investment = inventory * firm['cost']
    
    days = avg_trades / trades_day if trades_day > 0 else 0
    months = days / 20
    
    salary = (avg_payout - investment) / months if months > 0 else 0
    
    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, "prob_cash": prob_cash,
        "inventory": inventory, "investment": investment,
        "payout": avg_payout, "salary": salary, "months": months
    }

# --- INTERFAZ DE USUARIO ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Portfolio Manager")
    st.markdown("Plataforma profesional para la gestión de riesgos y proyección de beneficios en cuentas de fondeo.")
    
    tab_login, tab_reg = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    # --- LOGIN CORREGIDO ---
    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Entrar", type="primary")
            
            if submit:
                if login_user(u, p):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos")

    # --- REGISTRO CORREGIDO ---
    with tab_reg:
        with st.form("register_form"):
            nu = st.text_input("Elige un Usuario")
            np = st.text_input("Elige una Contraseña", type="password")
            submit_reg = st.form_submit_button("Crear Cuenta")
            
            if submit_reg:
                if nu and np:
                    msg = register_user(nu, np)
                    if msg == "OK": 
                        st.success("✅ Cuenta creada. Por favor inicia sesión.")
                    else: 
                        st.error(f"❌ Error: {msg}")
                else:
                    st.warning("⚠️ Completa todos los campos")

else:
    # --- APLICACIÓN PRINCIPAL ---
    
    # Header
    col_logo, col_user = st.columns([3,1])
    col_logo.title("💼 Portfolio Manager")
    col_user.write(f"Operador: **{st.session_state['username']}**")
    if col_user.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.markdown("---")
    
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.header("1. Configuración Global")
        st.caption("Parámetros de tu ejecución operativa diaria.")
        
        # INPUTS FALTANTES AGREGADOS AQUÍ
        gl_trades = st.number_input("Trades Promedio / Día", 1, 50, 3, help="Frecuencia operativa")
        gl_comm = st.number_input("Comisión ($/Lote)", 0.0, 15.0, 7.0, step=0.5, help="Costo del broker por lote ida y vuelta")
        
        st.divider()
        st.header("2. Agregar Cuentas")
        
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        
        # Pre-visualización de reglas antes de agregar
        sel_data = FIRMS_DATA[s_firm][s_prog][s_size]
        with st.expander("ℹ️ Ver Reglas de Cuenta"):
            st.markdown(f"""
            - **Costo:** ${sel_data['cost']}
            - **DD Total:** {sel_data['total_dd']}% | **Diario:** {sel_data.get('daily_dd', 'N/A')}%
            - **Target F1:** {sel_data['profit_p1']}% | **F2:** {sel_data.get('profit_p2', 'N/A')}%
            - **Bonus:** ${sel_data.get('p1_bonus', 0)}
            """)
        
        if st.button("➕ Añadir al Portafolio", type="secondary"):
            new_item = {
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": sel_data,
                "params": { # Defaults
                    "win_rate": 45, "rr": 2.0, "risk": 1.0, "withdrawal_target": 3.0
                }
            }
            st.session_state['portfolio'].append(new_item)
            st.toast("Cuenta agregada exitosamente")

    # --- BODY ---
    
    if not st.session_state['portfolio']:
        st.info("👈 Tu portafolio está vacío. Configura tu operativa global y agrega cuentas desde la barra lateral.")
    else:
        # 1. GESTIÓN DE PORTAFOLIO
        st.subheader(f"🎛️ Estrategia de Portafolio ({len(st.session_state['portfolio'])} Activos)")
        
        for i, item in enumerate(st.session_state['portfolio']):
            # Usamos un expander para editar cada cuenta
            with st.expander(f"⚙️ {item['full_name']} - Editar Estrategia", expanded=True):
                
                # Muestra reglas clave arriba de los inputs
                d = item['data']
                st.caption(f"💰 Costo: ${d['cost']} | 📉 DD: {d['total_dd']}% | 🎯 Targets: {d['profit_p1']}% / {d.get('profit_p2','-')}%")
                
                c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.2])
                
                k = str(item['id'])
                item['params']['win_rate'] = c1.number_input("WinRate %", 10, 90, item['params']['win_rate'], key=f"wr_{k}")
                item['params']['rr'] = c2.number_input("Ratio R:R", 0.1, 10.0, item['params']['rr'], step=0.1, key=f"rr_{k}")
                item['params']['risk'] = c3.number_input("Riesgo %", 0.1, 5.0, item['params']['risk'], step=0.1, key=f"rk_{k}")
                item['params']['withdrawal_target'] = c4.number_input("Meta Retiro %", 0.5, 20.0, item['params']['withdrawal_target'], step=0.5, key=f"wt_{k}", help="Objetivo de beneficio para retirar")
                
                if c5.button("🗑️", key=f"del_{k}", help="Eliminar cuenta"):
                    st.session_state['portfolio'].pop(i)
                    st.rerun()

        st.divider()
        
        # 2. BOTÓN DE ACCIÓN
        if st.button("🚀 Ejecutar Simulación Profesional", type="primary", use_container_width=True):
            
            with st.spinner("Procesando Montecarlo para todo el portafolio..."):
                global_inv = 0
                global_sal = 0
                results = []
                
                global_ops = {"comm": gl_comm, "trades_day": gl_trades}
                
                for item in st.session_state['portfolio']:
                    stats = run_account_simulation(item['data'], item['params'], global_ops)
                    global_inv += stats['investment']
                    global_sal += stats['salary']
                    results.append({"name": item['full_name'], "stats": stats, "params": item['params']})
                
                save_plan(st.session_state['username'], f"{len(results)} Cuentas", global_inv, global_sal)

            # 3. RESULTADOS
            st.markdown("### 📊 Resultados Consolidados")
            
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("Capital de Riesgo Total", f"${global_inv:,.0f}", help="Inversión total requerida para asegurar estadísticamente el éxito.")
            kc2.metric("Flujo de Caja Mensual", f"${global_sal:,.0f}", help="Salario neto promedio descontando costos.")
            
            roi = (global_sal * 12 / global_inv * 100) if global_inv > 0 else 0
            kc3.metric("ROI Anual Proyectado", f"{roi:.1f}%")

            st.subheader("🔍 Desglose por Cuenta")
            
            for res in results:
                s = res['stats']
                # Icono de estado
                status = "🟢" if s['salary'] > 0 else "🔴"
                
                with st.container(border=True):
                    head_col1, head_col2 = st.columns([3, 1])
                    head_col1.markdown(f"**{status} {res['name']}**")
                    head_col2.caption(f"Prob. Cobro: {s['prob_cash']:.1f}%")
                    
                    # Embudo
                    col_step1, col_step2, col_step3 = st.columns(3)
                    col_step1.metric("1. Fase 1", f"{s['prob_p1']:.1f}%")
                    col_step2.metric("2. Fase 2", f"{s['prob_p2']:.1f}%" if s['prob_p2'] < 100 else "N/A")
                    col_step3.metric("3. Payout", f"{s['prob_cash']:.1f}%")
                    
                    st.divider()
                    
                    # Datos Económicos
                    ec1, ec2, ec3, ec4 = st.columns(4)
                    ec1.metric("Stock (Intentos)", f"{s['inventory']}")
                    ec2.metric("Inversión", f"${s['investment']:,.0f}")
                    ec3.metric("1er Retiro", f"${s['payout']:,.0f}")
                    ec4.metric("Sueldo Neto", f"${s['salary']:,.0f}")

    # HISTORIAL
    st.divider()
    with st.expander("📜 Historial de Simulaciones"):
        h = get_history(st.session_state.get('username',''))
        if h: st.dataframe(pd.DataFrame(h, columns=["Resumen", "Inv Total", "Sueldo Total", "Fecha"]))