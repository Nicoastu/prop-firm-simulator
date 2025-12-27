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
    if not engine: return "Error: Sin conexión a Base de Datos (Modo Local)"
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
            "5K":   {"cost": 39,  "size": 5000,   "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 5},
            "10K":  {"cost": 78,  "size": 10000,  "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 10},
            "20K":  {"cost": 165, "size": 20000,  "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 15},
            "60K":  {"cost": 329, "size": 60000,  "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 25},
            "100K": {"cost": 545, "size": 100000, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 40}
        },
        "Hyper Growth (1 Step)": {
            "5K":   {"cost": 260, "size": 5000,   "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 15},
            "10K":  {"cost": 450, "size": 10000,  "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 25},
            "20K":  {"cost": 850, "size": 20000,  "total_dd": 6.0, "profit_p1": 10.0, "profit_p2": 0.0, "p1_bonus": 50}
        }
    },
    "FTMO": {
        "Swing Challenge": {
            "100K": {"cost": 540, "size": 100000, "total_dd": 10.0, "profit_p1": 10.0, "profit_p2": 5.0, "p1_bonus": 0}
        }
    },
    "FundedNext": {
        "Stellar 1-Step": {
            "100K": {"cost": 519, "size": 100000, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 0.0, "p1_bonus": 0}
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
    n_sims = 1000 # Precisión estándar
    
    # Contadores
    pass_p1 = 0
    pass_p2 = 0
    pass_cash_1 = 0 # Primer cobro
    pass_cash_2 = 0 # Segundo cobro
    pass_cash_3 = 0 # Tercer cobro
    
    total_accumulated_payout = 0 # Suma de todo el dinero extraído en las sims exitosas
    
    is_2step = firm.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        # --- FASE 1 ---
        ok1, _, _ = simulate_phase(firm['size'], risk, wr, rr, firm['profit_p1'], firm['total_dd'], comm, sl_min, sl_max)
        if not ok1: continue
        pass_p1 += 1
        
        # --- FASE 2 ---
        if is_2step:
            ok2, _, _ = simulate_phase(firm['size'], risk, wr, rr, firm['profit_p2'], firm['total_dd'], comm, sl_min, sl_max)
            if not ok2: continue
            pass_p2 += 1
        else:
            pass_p2 += 1
            
        # --- MES 1: Primer Retiro ---
        # Objetivo: Llegar al % de retiro configurado sin quemar
        ok_m1, t3, final_bal_m1 = simulate_phase(firm['size'], risk, wr, rr, w_target, firm['total_dd'], comm, sl_min, sl_max, is_funded=True)
        
        if ok_m1:
            pass_cash_1 += 1
            # Cálculo Payout 1
            gross = final_bal_m1 - firm['size']
            split = gross * 0.80
            pay1 = split + firm['cost'] + firm.get('p1_bonus', 0)
            total_accumulated_payout += pay1
            
            # --- MES 2: Segundo Retiro ---
            # Asumimos reset de cuenta al balance inicial
            ok_m2, _, final_bal_m2 = simulate_phase(firm['size'], risk, wr, rr, w_target, firm['total_dd'], comm, sl_min, sl_max, is_funded=True)
            
            if ok_m2:
                pass_cash_2 += 1
                gross2 = final_bal_m2 - firm['size']
                pay2 = gross2 * 0.80 # Solo split, sin refund ni bonus
                total_accumulated_payout += pay2
                
                # --- MES 3: Tercer Retiro ---
                ok_m3, _, final_bal_m3 = simulate_phase(firm['size'], risk, wr, rr, w_target, firm['total_dd'], comm, sl_min, sl_max, is_funded=True)
                
                if ok_m3:
                    pass_cash_3 += 1
                    gross3 = final_bal_m3 - firm['size']
                    pay3 = gross3 * 0.80
                    total_accumulated_payout += pay3

    # --- ESTADÍSTICAS FINALES ---
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 if is_2step else 100.0
    
    prob_c1 = (pass_cash_1/n_sims)*100
    prob_c2 = (pass_cash_2/n_sims)*100
    prob_c3 = (pass_cash_3/n_sims)*100
    
    # Unit Economics (basado en éxito del 1er retiro)
    attempts = 100/prob_c1 if prob_c1 > 0 else 100
    inventory = math.ceil(attempts)
    investment = inventory * firm['cost']
    
    # EV Total = Total Dinero Sacado / Total Intentos (Sims)
    # Ajustamos para mostrar el "Promedio de cobro acumulado" para alguien que logra pasar
    # Promedio acumulado por CADA cuenta ganadora (ciclo completo)
    avg_total_payout_per_winner = total_accumulated_payout / pass_cash_1 if pass_cash_1 > 0 else 0
    
    # Tiempo estimado (aproximado para MVP)
    months_to_liquidity = 1.0 # Minimo 1 mes
    
    salary = (avg_total_payout_per_winner - investment) # Net Profit total del ciclo
    
    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, 
        "prob_c1": prob_c1, "prob_c2": prob_c2, "prob_c3": prob_c3,
        "inventory": inventory, "investment": investment,
        "total_payout_avg": avg_total_payout_per_winner, 
        "net_profit": salary,
        "is_2step": is_2step
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
                        if r=="OK": st.success("Creado")
                        else: st.error(r)
else:
    # --- APP ---
    c_head, c_user = st.columns([4,1])
    c_head.title("💼 Gestor de Portafolio Pro")
    c_user.write(f"👤 **{st.session_state['username']}**")
    if c_user.button("Salir"): st.session_state['logged_in']=False; st.rerun()
    st.markdown("---")
    
    # SIDEBAR: CATALOGO
    with st.sidebar:
        st.header("1. Agregar Activos")
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        
        d = FIRMS_DATA[s_firm][s_prog][s_size]
        st.caption(f"💰 Costo: ${d['cost']} | 🎯 F1: {d['profit_p1']}% | 📉 DD: {d['total_dd']}%")
        
        if st.button("➕ Agregar al Portafolio", type="primary", use_container_width=True):
            st.session_state['portfolio'].append({
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": d,
                "params": {"win_rate": 45, "rr": 2.0, "risk": 1.0, "withdrawal_target": 3.0, "trades_day": 3, "comm": 7.0}
            })
            st.toast("Activo agregado")

    # BODY
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
        if st.button("🚀 Simular Portafolio Completo", type="primary", use_container_width=True):
            with st.spinner("Simulando proyecciones a 3 meses..."):
                results = []
                g_inv = 0
                g_net = 0
                
                for item in st.session_state['portfolio']:
                    s = run_account_simulation(item['data'], item['params'])
                    g_inv += s['investment']
                    g_net += s['net_profit']
                    results.append({"name": item['full_name'], "stats": s})
                
                save_plan(st.session_state['username'], f"{len(results)} Cuentas", g_inv, g_net)
                
                # --- RESULTADOS ---
                st.markdown("### 📊 Resultados Consolidados")
                m1, m2, m3 = st.columns(3)
                m1.metric("Inversión Total (Riesgo)", f"${g_inv:,.0f}", help="Costo de todas las cuentas necesarias para asegurar éxito.")
                m2.metric("Beneficio Neto Esperado", f"${g_net:,.0f}", help="Ganancia total proyectada tras recuperar inversión.")
                roi = (g_net / g_inv * 100) if g_inv > 0 else 0
                m3.metric("ROI Potencial", f"{roi:.1f}%")
                
                st.subheader("📋 Desglose Combinatorio")
                
                # Tabla Resumen Comparativa
                summary_data = []
                for res in results:
                    s = res['stats']
                    summary_data.append({
                        "Cuenta": res['name'],
                        "Stock": f"{s['inventory']} u.",
                        "Inversión": f"${s['investment']:,.0f}",
                        "Prob. Cobro 1": f"{s['prob_c1']:.1f}%",
                        "Prob. Cobro 3": f"{s['prob_c3']:.1f}%",
                        "Beneficio Neto": f"${s['net_profit']:,.0f}"
                    })
                st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

                st.subheader("🔍 Detalle de Retención")
                for res in results:
                    s = res['stats']
                    with st.expander(f"📈 {res['name']} (Prob. 1er Cobro: {s['prob_c1']:.1f}%)"):
                        # Embudo Horizontal
                        c_prob1, c_prob2, c_prob3, c_prob4, c_prob5 = st.columns(5)
                        c_prob1.metric("1. Fase 1", f"{s['prob_p1']:.1f}%")
                        c_prob2.metric("2. Fase 2", f"{s['prob_p2']:.1f}%" if s['is_2step'] else "N/A")
                        c_prob3.metric("3. Retiro 1", f"{s['prob_c1']:.1f}%", "Recuperación")
                        c_prob4.metric("4. Retiro 2", f"{s['prob_c2']:.1f}%", "Beneficio")
                        c_prob5.metric("5. Retiro 3", f"{s['prob_c3']:.1f}%", "Consistencia")
                        
                        st.caption(f"Payout Total Acumulado (Promedio de ganadores): ${s['total_payout_avg']:,.0f}")

    st.divider()
    with st.expander("Historial"):
        h = get_history(st.session_state.get('username',''))
        if h: st.dataframe(pd.DataFrame(h))