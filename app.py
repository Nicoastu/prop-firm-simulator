import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time
import math
import json
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Prop Firm Portfolio Pro", page_icon="📈", layout="wide")

# --- ESTADO ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''
if 'portfolio' not in st.session_state: st.session_state['portfolio'] = [] 

# --- DB ---
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
            conn.execute(text("CREATE TABLE IF NOT EXISTS user_portfolios (username TEXT PRIMARY KEY, portfolio_json TEXT);"))
            conn.commit()

# --- PERSISTENCIA ---
def save_portfolio_db(username, portfolio_data):
    if not engine: return False
    try:
        # Serializamos fechas a string para JSON
        # (Simple hack: el JSON guarda todo como estructura, al cargar convertimos si hace falta)
        json_data = json.dumps(portfolio_data, default=str)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM user_portfolios WHERE username = :u"), {"u": username})
            conn.execute(text("INSERT INTO user_portfolios (username, portfolio_json) VALUES (:u, :d)"), {"u": username, "d": json_data})
            conn.commit()
        return True
    except Exception as e:
        print(e)
        return False

def load_portfolio_db(username):
    if not engine: return []
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT portfolio_json FROM user_portfolios WHERE username = :u"), {"u": username}).fetchone()
            if res: return json.loads(res[0])
            return []
    except: return []

# --- AUTH ---
def register_user(u, p):
    if not engine: return "Error BD Local"
    try:
        with engine.connect() as conn:
            if conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": u}).fetchone(): return "Usuario existe"
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

if engine: init_db()

# --- DATOS ---
FIRMS_DATA = {
    "The5ers": {
        "High Stakes (2 Step)": {
            "5K":   {"cost": 39,  "size": 5000,   "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 5},
            "10K":  {"cost": 78,  "size": 10000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 10},
            "20K":  {"cost": 165, "size": 20000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 15},
            "60K":  {"cost": 329, "size": 60000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 25},
            "100K": {"cost": 545, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 40}
        }
    }
}

# --- SIMULACIÓN (ADAPTATIVA) ---
def simulate_phase(initial_balance, current_balance, risk_pct, win_rate, rr, target_pct, max_dd_pct, daily_dd_pct, comm, sl_min, sl_max, trades_per_day, is_funded=False):
    curr = current_balance
    
    # Objetivo: Se calcula sobre el balance INICIAL (High Water Mark para target)
    # Ej: Si inicias con 100k y meta 8%, target es 108k. Aunque vayas en 98k, debes llegar a 108k.
    target_equity = initial_balance + (initial_balance * (target_pct/100))
    
    # Límite Estático: Basado en balance INICIAL
    static_limit = initial_balance - (initial_balance * (max_dd_pct/100))
    
    # Si ya perdimos la cuenta en la vida real, retornamos fallo inmediato
    if curr <= static_limit: return False, 0, curr, "Ya perdida (Real)"
    if curr >= target_equity: return True, 0, curr, "Ya ganada (Real)"

    trades = 0
    max_trades = 1500 
    pip_val = 10
    
    day_start_equity = curr # Asumimos que la simulación arranca "hoy"
    trades_today = 0
    fixed_daily_loss_amount = initial_balance * (daily_dd_pct / 100)
    
    while curr > static_limit and curr < target_equity and trades < max_trades:
        trades += 1
        trades_today += 1
        
        if trades_today > trades_per_day:
            day_start_equity = curr 
            trades_today = 1        
            
        current_sl = random.uniform(sl_min, sl_max)
        # Riesgo se calcula sobre Balance INICIAL (Fijo) para no reducir lotaje en drawdown (agresivo para recuperar)
        # Ojo: Gestión conservadora reduciría riesgo, aquí asumimos riesgo fijo para recuperar.
        risk_money = initial_balance * (risk_pct / 100) 
        
        lot_size = risk_money / (current_sl * pip_val)
        trade_comm = lot_size * comm
        
        slippage = random.uniform(0.95, 1.05) 
        is_error = random.random() < 0.01 
        
        if random.random() < (win_rate/100):
            profit = (risk_money * rr * slippage) - trade_comm
            curr += profit
        else:
            loss = (risk_money * slippage) + trade_comm
            if is_error: loss *= 1.5 
            curr -= loss
            
        if curr <= static_limit:
            return False, trades, curr, "Max Drawdown"
            
        if (day_start_equity - curr) >= fixed_daily_loss_amount:
            return False, trades, curr, "Daily Drawdown"
            
    if curr >= target_equity: return True, trades, curr, "Success"
    else: return False, trades, curr, "Timeout"

def run_account_simulation(account_data, strategy_params, n_sims, current_balance_real):
    # Extraemos params
    wr = strategy_params['win_rate']; rr = strategy_params['rr']
    risk = strategy_params['risk']; w_target = strategy_params['withdrawal_target']
    comm = strategy_params['comm']; trades_day = strategy_params['trades_day']
    sl_min = 5; sl_max = 15; daily_dd = account_data.get('daily_dd', 100.0)
    
    initial_size = account_data['size']
    
    # Determinar en qué fase estamos basado en el progreso real no es trivial sin estado de fase.
    # ASUNCIÓN PARA MVP: Si estamos simulando, asumimos que estamos en FASE 1 intentando pasar,
    # O si es fondeada, intentando cobrar.
    # Para simplificar la visualización combinada, simularemos el CAMINO COMPLETO desde el estado actual.
    
    pass_c1 = 0; pass_c2 = 0; pass_c3 = 0
    sum_pay1 = 0; sum_pay2 = 0; sum_pay3 = 0
    
    # Target monetario para retiro (Ej: 3% de 100k = 3k)
    target_profit_amount = initial_size * (w_target / 100)
    split_share = target_profit_amount * 0.80
    payout_val = split_share + account_data['cost'] + account_data.get('p1_bonus', 0)
    
    # Si el usuario ya está en drawdown (ej: 98k), debe recuperar 2k + hacer 3k = 5k total.
    # El simulador se encarga de esto porque target_equity es fijo (103k).
    
    fail_reasons = {"Max Drawdown": 0, "Daily Drawdown": 0, "Timeout": 0, "Ya perdida (Real)": 0}
    
    for _ in range(n_sims):
        # FASE 1 / TRAYECTO AL PRIMER COBRO
        # Usamos current_balance_real como punto de partida
        ok1, _, bal1, cause1 = simulate_phase(initial_size, current_balance_real, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
        
        if ok1:
            pass_c1 += 1
            sum_pay1 += payout_val # Asumimos cobro completo si llega al target
            
            # RETIRO 2 (Reset a Inicial)
            ok2, _, bal2, _ = simulate_phase(initial_size, initial_size, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
            if ok2:
                pass_c2 += 1
                sum_pay2 += split_share # Solo split
                
                # RETIRO 3
                ok3, _, _, _ = simulate_phase(initial_size, initial_size, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
                if ok3:
                    pass_c3 += 1
                    sum_pay3 += split_share
        else:
            if cause1 in fail_reasons: fail_reasons[cause1] += 1

    prob_c1 = (pass_c1/n_sims)*100
    prob_c2 = (pass_c2/n_sims)*100
    prob_c3 = (pass_c3/n_sims)*100
    
    avg_pay1 = sum_pay1 / pass_c1 if pass_c1 > 0 else 0
    
    return {
        "prob_c1": prob_c1, "prob_c2": prob_c2, "prob_c3": prob_c3,
        "avg_pay1": avg_pay1, "fail_reasons": fail_reasons,
        "total_failures": n_sims - pass_c1
    }

# --- UI ---
if not st.session_state['logged_in']:
    st.title("💼 Prop Firm Portfolio Manager")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        tab1, tab2 = st.tabs(["Ingresar", "Registrar"])
        with tab1:
            u = st.text_input("Usuario"); p = st.text_input("Clave", type="password")
            if st.button("Login", type="primary", use_container_width=True):
                if login_user(u, p):
                    st.session_state['logged_in'] = True; st.session_state['username'] = u
                    saved = load_portfolio_db(u)
                    if saved: st.session_state['portfolio'] = saved
                    st.rerun()
                else: st.error("Error")
        with tab2:
            nu = st.text_input("Nuevo Usuario"); np = st.text_input("Nueva Clave", type="password")
            if st.button("Crear", use_container_width=True):
                if register_user(nu, np) == "OK": st.success("Creado")
else:
    # HEADER
    c_head, c_user = st.columns([4,1])
    c_head.title("💼 Portfolio Manager Pro")
    c_user.write(f"👤 **{st.session_state['username']}**")
    if c_user.button("Salir"): st.session_state['logged_in']=False; st.rerun()
    st.markdown("---")
    
    # SIDEBAR
    with st.sidebar:
        st.header("1. Global")
        sim_precision = st.select_slider("Simulaciones", options=[500, 1000, 5000], value=1000)
        if st.button("💾 Guardar Todo", type="primary"):
            if save_portfolio_db(st.session_state['username'], st.session_state['portfolio']): st.toast("Guardado")
        
        st.divider()
        st.header("2. Catálogo")
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        d = FIRMS_DATA[s_firm][s_prog][s_size]
        
        with st.container(border=True):
            st.caption("Reglas:")
            c1, c2 = st.columns(2)
            c1.markdown(f"💰 **${d['cost']}**"); c2.markdown(f"📉 **{d['total_dd']}%**")
        
        if st.button("➕ Agregar Cuenta"):
            # Inicializamos la cuenta con un Diario vacío
            st.session_state['portfolio'].append({
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": d,
                "params": {"win_rate": 45, "rr": 2.0, "risk": 1.0, "withdrawal_target": 3.0, "trades_day": 3, "comm": 7.0},
                "journal": [] # LISTA PARA LOS TRADES REALES
            })
            st.toast("Agregada")

    if not st.session_state['portfolio']:
        st.info("Portafolio vacío. Agrega una cuenta.")
    else:
        # PESTAÑAS PRINCIPALES
        tab_config, tab_journal, tab_sim = st.tabs(["⚙️ Configuración", "📝 Diario / Ejecución", "🚀 Simulación & Proyección"])
        
        # 1. CONFIGURACIÓN
        with tab_config:
            for i, item in enumerate(st.session_state['portfolio']):
                with st.expander(f"⚙️ {item['full_name']} (Config)", expanded=False):
                    c1, c2, c3, c4 = st.columns(4)
                    k = str(item['id'])
                    item['params']['win_rate'] = c1.number_input("WR %", 10, 90, item['params']['win_rate'], key=f"w{k}")
                    item['params']['rr'] = c2.number_input("R:R", 0.5, 10.0, item['params']['rr'], step=0.1, key=f"r{k}")
                    item['params']['risk'] = c3.number_input("Riesgo %", 0.1, 5.0, item['params']['risk'], step=0.1, key=f"rk{k}")
                    item['params']['withdrawal_target'] = c4.number_input("Meta Retiro %", 0.5, 20.0, item['params']['withdrawal_target'], step=0.5, key=f"wt{k}")
                    c5, c6, c7 = st.columns([1,1,2])
                    item['params']['trades_day'] = c5.number_input("Max Trades/Día", 1, 50, item['params']['trades_day'], key=f"td{k}")
                    item['params']['comm'] = c6.number_input("Comisión ($)", 0.0, 20.0, item['params']['comm'], key=f"cm{k}")
                    if c7.button("Eliminar Cuenta", key=f"d{k}"): 
                        st.session_state['portfolio'].pop(i); st.rerun()

        # 2. DIARIO (NUEVO)
        with tab_journal:
            st.subheader("📓 Registro de Operaciones Reales")
            
            for item in st.session_state['portfolio']:
                with st.expander(f"📖 {item['full_name']} - Ingresar Trades", expanded=True):
                    # Formulario de Entrada
                    with st.form(key=f"form_{item['id']}"):
                        f1, f2, f3, f4 = st.columns(4)
                        t_date = f1.date_input("Fecha")
                        t_gross = f2.number_input("Bruto ($)", value=0.0, step=10.0, help="Ganancia/Pérdida antes de comisiones")
                        t_comm = f3.number_input("Comisión ($)", value=0.0, step=1.0)
                        t_swap = f4.number_input("Swap ($)", value=0.0, step=1.0)
                        
                        if st.form_submit_button("💾 Registrar Trade"):
                            net = t_gross - t_comm - t_swap
                            new_trade = {
                                "date": str(t_date),
                                "gross": t_gross, "comm": t_comm, "swap": t_swap,
                                "net": net
                            }
                            item['journal'].append(new_trade)
                            st.success(f"Trade registrado. Neto: ${net:.2f}")
                            st.rerun()

                    # Lógica de Validación de Reglas (Trades diarios)
                    if item['journal']:
                        df_j = pd.DataFrame(item['journal'])
                        # Contar trades de HOY (o última fecha ingresada)
                        last_date = df_j.iloc[-1]['date']
                        trades_on_date = df_j[df_j['date'] == last_date].shape[0]
                        
                        limit_trades = item['params']['trades_day']
                        if trades_on_date > limit_trades:
                            st.warning(f"⚠️ **ALERTA DE DISCIPLINA:** Has registrado {trades_on_date} trades el día {last_date}. Tu plan permite máximo {limit_trades}. ¡Cuidado con el Overtrading!")

                        # Tabla Resumen
                        st.dataframe(df_j.tail(5), use_container_width=True)
                        
                        # Cálculo Balance Actual
                        total_pnl = df_j['net'].sum()
                        current_bal = item['data']['size'] + total_pnl
                        
                        # Métrica de Estado
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.metric("Balance Inicial", f"${item['data']['size']:,.0f}")
                        col_m2.metric("P&L Real Acumulado", f"${total_pnl:,.2f}", delta_color="normal")
                        col_m3.metric("Balance ACTUAL", f"${current_bal:,.2f}")
                    else:
                        st.info("Sin trades registrados aún. El balance es el inicial.")

        # 3. SIMULACIÓN (CON DATOS REALES)
        with tab_sim:
            if st.button("🚀 Re-Calcular Proyecciones (Basado en Balance Actual)", type="primary", use_container_width=True):
                with st.spinner("Simulando futuros posibles desde tu situación actual..."):
                    results = []
                    g_pay1 = 0
                    
                    for item in st.session_state['portfolio']:
                        # Calcular Balance Real de Inicio
                        start_bal = item['data']['size']
                        if item['journal']:
                            start_bal += sum(t['net'] for t in item['journal'])
                        
                        # Ejecutar Simulación desde ese punto
                        s = run_account_simulation(item['data'], item['params'], sim_precision, start_bal)
                        g_pay1 += s['avg_pay1']
                        results.append({"name": item['full_name'], "stats": s, "start_bal": start_bal})
                    
                    # RESULTADOS
                    st.markdown("### 🔮 Proyección Actualizada")
                    st.metric("Potencial 1er Retiro (Combinado)", f"${g_pay1:,.0f}")
                    
                    for res in results:
                        s = res['stats']
                        bal_fmt = f"${res['start_bal']:,.0f}"
                        
                        with st.expander(f"📊 {res['name']} (Desde: {bal_fmt})"):
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Prob. Cobro", f"{s['prob_c1']:.1f}%")
                            c2.metric("Monto Est.", f"${s['avg_pay1']:,.0f}")
                            
                            # Diagnóstico
                            if s['total_failures'] > 0:
                                fail_stats = s['fail_reasons']
                                total = s['total_failures']
                                st.caption("Riesgos Principales desde aquí:")
                                # Convertir a %
                                for k, v in fail_stats.items():
                                    if v > 0:
                                        pct = (v/total)*100
                                        st.progress(int(pct), text=f"{k}: {pct:.1f}%")