import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time
import math

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Prop Firm Portfolio Manager", page_icon="💼", layout="wide")

# --- ESTADO Y SESIÓN ---
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

# --- FUNCIONES DB ---
def register_user(u, p):
    if not engine: return "Sin BD"
    try:
        with engine.connect() as conn:
            if conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": u}).fetchone(): return "Existe"
            conn.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": u, "p": p})
            conn.commit()
            return "OK"
    except Exception as e: return str(e)

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
    
    # Objetivo
    target_equity = balance + (balance * (target_pct/100))
    limit_equity = balance - (balance * (max_dd_pct/100))
    
    trades = 0
    max_trades = 1500 # Safety limit
    
    pip_val = 10
    
    while curr > limit_equity and curr < target_equity and trades < max_trades:
        trades += 1
        
        # Dinámica operativa
        current_sl = random.uniform(sl_min, sl_max)
        risk_money = start_balance * (risk_pct / 100) # Riesgo basado en balance inicial (estático)
        
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
    # Desempaquetar estrategia específica de ESTA cuenta
    wr = strategy_params['win_rate']
    rr = strategy_params['rr']
    risk = strategy_params['risk']
    w_target = strategy_params['withdrawal_target']
    
    # Inputs globales fijos (para simplificar UX individual)
    comm = 7.0; sl_min = 5; sl_max = 15; trades_day = 3
    
    firm = account_data
    n_sims = 800 # Optimizado para velocidad
    
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
            
        # FASE FONDEADA (Target = Withdrawal %)
        ok_fund, t3, final_bal = simulate_phase(firm['size'], risk, wr, rr, w_target, firm['total_dd'], comm, sl_min, sl_max, is_funded=True)
        sim_trades += t3
        
        if ok_fund:
            pass_cash += 1
            total_trades += sim_trades
            
            # --- CÁLCULO EXACTO PAYOUT ---
            # 1. Profit Bruto generado (según el % retiro configurado)
            gross_profit = final_bal - firm['size']
            
            # 2. Profit Split (80% estándar)
            net_profit_share = gross_profit * 0.80
            
            # 3. Reembolso y Bonus
            total_pay = net_profit_share + firm['cost'] + firm.get('p1_bonus', 0)
            total_payouts += total_pay

    # Estadísticas
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 if is_2step else 100.0
    # Probabilidad condicional real de pasar P2 dado P1 ya está implícita en el contador
    # Ajustamos para mostrar probabilidad ABSOLUTA del paso
    
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

# --- INTERFAZ ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Manager")
    # Login simple
    c1, c2 = st.tabs(["Entrar", "Crear"])
    with c1:
        if st.button("Login"): st.session_state['logged_in'] = True; st.rerun() # Bypass simple para demo
else:
    # HEADER
    c1, c2 = st.columns([3,1])
    c1.title("💼 Portfolio Manager")
    if c2.button("Salir"): st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")
    
    # --- BARRA LATERAL: ADD ACCOUNTS ---
    st.sidebar.header("🛒 Agregar Cuenta")
    s_firm = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    s_prog = st.sidebar.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
    s_size = st.sidebar.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
    
    # Defaults globales
    def_wr = 45; def_rr = 2.0; def_risk = 1.0; def_target = 3.0
    
    if st.sidebar.button("➕ Añadir al Portafolio"):
        firm_data = FIRMS_DATA[s_firm][s_prog][s_size]
        new_item = {
            "id": int(time.time()*1000),
            "name": f"{s_firm} - {s_size}",
            "full_name": f"{s_firm} {s_prog} ({s_size})",
            "data": firm_data,
            # ESTRATEGIA INDIVIDUAL POR CUENTA
            "params": {
                "win_rate": def_wr,
                "rr": def_rr,
                "risk": def_risk,
                "withdrawal_target": def_target
            }
        }
        st.session_state['portfolio'].append(new_item)
        st.success("Agregada")

    # --- BODY PRINCIPAL ---
    
    if not st.session_state['portfolio']:
        st.info("👈 Tu portafolio está vacío. Agrega cuentas desde la barra lateral.")
    else:
        # --- 1. GESTIÓN DE CUENTAS (EDITABLE) ---
        st.subheader(f"🎛️ Configuración de Portafolio ({len(st.session_state['portfolio'])} Cuentas)")
        
        for i, item in enumerate(st.session_state['portfolio']):
            with st.expander(f"⚙️ {item['full_name']} (Configurar Estrategia)", expanded=True):
                c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.5])
                
                # INPUTS INDIVIDUALES CON KEYS ÚNICAS
                k = str(item['id'])
                
                item['params']['win_rate'] = c1.number_input("WinRate %", 10, 90, item['params']['win_rate'], key=f"wr_{k}")
                item['params']['rr'] = c2.number_input("Ratio R:R", 0.1, 10.0, item['params']['rr'], step=0.1, key=f"rr_{k}")
                item['params']['risk'] = c3.number_input("Riesgo %", 0.1, 5.0, item['params']['risk'], step=0.1, key=f"rk_{k}")
                item['params']['withdrawal_target'] = c4.number_input("Meta Retiro %", 0.5, 20.0, item['params']['withdrawal_target'], step=0.5, key=f"wt_{k}", help="¿A qué % solicitas retiro?")
                
                if c5.button("🗑️", key=f"del_{k}"):
                    st.session_state['portfolio'].pop(i)
                    st.rerun()

        # --- 2. BOTÓN SIMULAR ---
        st.divider()
        if st.button("🚀 Simular Escenario Completo", type="primary", use_container_width=True):
            
            with st.spinner("Calculando probabilidades individuales y consolidando resultados..."):
                global_inv = 0
                global_sal = 0
                results = []
                
                for item in st.session_state['portfolio']:
                    # Corremos simulación con los parámetros específicos de esa cuenta
                    stats = run_account_simulation(item['data'], item['params'])
                    
                    global_inv += stats['investment']
                    global_sal += stats['salary']
                    
                    results.append({"name": item['full_name'], "stats": stats, "params": item['params']})
                
                # Guardar Historial
                summary = f"{len(results)} Cuentas | Inv: ${global_inv:,.0f}"
                save_plan(st.session_state['username'], summary, global_inv, global_sal)

            # --- 3. RESULTADOS GLOBALES ---
            st.markdown("### 🌍 Resultados Consolidados")
            k1, k2, k3 = st.columns(3)
            k1.metric("Capital de Riesgo Total", f"${global_inv:,.0f}", help="Suma de todos los presupuestos de seguridad.")
            k2.metric("Flujo Mensual Esperado", f"${global_sal:,.0f}", help="Suma de salarios mensuales.")
            roi = ((global_sal * 12) / global_inv * 100) if global_inv > 0 else 0
            k3.metric("ROI Anualizado", f"{roi:.1f}%")

            # --- 4. DETALLE POR CUENTA (EL EMBUDO) ---
            st.subheader("🔍 Análisis Detallado por Cuenta")
            
            for res in results:
                s = res['stats']
                p = res['params']
                
                # Tarjeta de Resultados
                with st.container(border=True):
                    head_c1, head_c2 = st.columns([3,1])
                    head_c1.markdown(f"#### 📊 {res['name']}")
                    
                    # El Embudo Visual
                    st.caption("🔻 Embudo de Probabilidad Realista")
                    step1, step2, step3 = st.columns(3)
                    step1.metric("1. Pasar Fase 1", f"{s['prob_p1']:.1f}%")
                    
                    # Lógica visual Fase 2
                    label_p2 = "2. Pasar Fase 2" if s['prob_p2'] < 100 else "2. Fase 2 (N/A)"
                    val_p2 = f"{s['prob_p2']:.1f}%" if s['prob_p2'] < 100 else "✅"
                    step2.metric(label_p2, val_p2)
                    
                    step3.metric("3. Cobrar Dinero", f"{s['prob_cash']:.1f}%", help="Probabilidad final de éxito (dinero en banco).")
                    
                    st.divider()
                    
                    # Datos Financieros
                    f1, f2, f3, f4 = st.columns(4)
                    f1.metric("Stock Sugerido", f"{s['inventory']} Cuentas", help="Cuentas a comprar para asegurar éxito estadístico.")
                    f2.metric("Inversión Riesgo", f"${s['investment']:,.0f}")
                    f3.metric("1er Payout Real", f"${s['payout']:,.0f}", help=f"Basado en retirar el {p['withdrawal_target']}% + Split + Refund.")
                    f4.metric("Sueldo / Mes", f"${s['salary']:,.0f}", help=f"Considerando un tiempo de {s['months']:.1f} meses.")

    # HISTORIAL
    st.divider()
    with st.expander("📜 Historial"):
        h = get_history(st.session_state.get('username',''))
        if h: st.dataframe(pd.DataFrame(h, columns=["Resumen", "Inv Total", "Sueldo Total", "Fecha"]))