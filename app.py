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
if 'sim_results_theoretical' not in st.session_state: st.session_state['sim_results_theoretical'] = None
if 'sim_results_real' not in st.session_state: st.session_state['sim_results_real'] = None

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
        json_data = json.dumps(portfolio_data, default=str)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM user_portfolios WHERE username = :u"), {"u": username})
            conn.execute(text("INSERT INTO user_portfolios (username, portfolio_json) VALUES (:u, :d)"), {"u": username, "d": json_data})
            conn.commit()
        return True
    except Exception as e: return False

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

# --- MOTOR DE SIMULACIÓN ---
def simulate_phase(initial_balance, current_balance, risk_pct, win_rate, rr, target_pct, max_dd_pct, daily_dd_pct, comm, sl_min, sl_max, trades_per_day, is_funded=False):
    curr = current_balance
    target_equity = initial_balance + (initial_balance * (target_pct/100))
    static_limit = initial_balance - (initial_balance * (max_dd_pct/100))
    
    if curr <= static_limit: return False, 0, curr, "Ya perdida (Real)"
    if curr >= target_equity: return True, 0, curr, "Ya ganada (Real)"

    trades = 0
    max_trades = 1500 
    pip_val = 10
    
    day_start_equity = curr 
    trades_today = 0
    fixed_daily_loss_amount = initial_balance * (daily_dd_pct / 100)
    
    while curr > static_limit and curr < target_equity and trades < max_trades:
        trades += 1
        trades_today += 1
        
        if trades_today > trades_per_day:
            day_start_equity = curr 
            trades_today = 1        
            
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
            loss = (risk_money * slippage) + trade_comm
            if is_error: loss *= 1.5 
            curr -= loss
            
        if curr <= static_limit:
            return False, trades, curr, "Max Drawdown"
            
        if (day_start_equity - curr) >= fixed_daily_loss_amount:
            return False, trades, curr, "Daily Drawdown"
            
    if curr >= target_equity: return True, trades, curr, "Success"
    else: return False, trades, curr, "Timeout"

def calculate_time_metrics(trades_list, trades_per_day):
    if not trades_list: return 0.0
    avg_trades = sum(trades_list) / len(trades_list)
    trading_days = avg_trades / trades_per_day
    months = trading_days / 20.0
    return months

def run_account_simulation(account_data, strategy_params, n_sims, current_balance_real):
    wr = strategy_params['win_rate']; rr = strategy_params['rr']
    risk = strategy_params['risk']; w_target = strategy_params['withdrawal_target']
    comm = strategy_params['comm']; trades_day = strategy_params['trades_day']
    sl_min = 5; sl_max = 15; daily_dd = account_data.get('daily_dd', 100.0)
    
    initial_size = account_data['size']
    
    pass_c1 = 0; pass_c2 = 0; pass_c3 = 0
    sum_pay1 = 0; sum_pay2 = 0; sum_pay3 = 0
    fail_reasons = {"Max Drawdown": 0, "Daily Drawdown": 0, "Timeout": 0, "Ya perdida (Real)": 0}
    
    trades_p1 = []; trades_p2 = []; trades_c1 = []; trades_c2 = []; trades_c3 = []
    
    target_profit_amount = initial_size * (w_target / 100)
    split_share = target_profit_amount * 0.80
    pay_val_1 = split_share + account_data['cost'] + account_data.get('p1_bonus', 0)
    pay_val_2 = split_share
    pay_val_3 = split_share
    
    is_2step = account_data.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        # 1. FASE ACTUAL
        ok1, t1, _, cause1 = simulate_phase(initial_size, current_balance_real, risk, wr, rr, account_data['profit_p1'], account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
        
        if not ok1:
            if cause1 in fail_reasons: fail_reasons[cause1] += 1
            continue
        trades_p1.append(t1)
        
        # 2. FASE 2
        if is_2step:
            ok2, t2, _, cause2 = simulate_phase(initial_size, initial_size, risk, wr, rr, account_data['profit_p2'], account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
            if not ok2:
                if cause2 in fail_reasons: fail_reasons[cause2] += 1
                continue
            trades_p2.append(t2)
            
        # 3. FONDEO
        ok_c1, tc1, _, cause3 = simulate_phase(initial_size, initial_size, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
        if ok_c1:
            pass_c1 += 1
            trades_c1.append(tc1)
            sum_pay1 += pay_val_1 
            
            ok_c2, tc2, _, _ = simulate_phase(initial_size, initial_size, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
            if ok_c2:
                pass_c2 += 1
                trades_c2.append(tc2)
                sum_pay2 += pay_val_2
                
                ok_c3, tc3, _, _ = simulate_phase(initial_size, initial_size, risk, wr, rr, w_target, account_data['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
                if ok_c3:
                    pass_c3 += 1
                    trades_c3.append(tc3)
                    sum_pay3 += pay_val_3
        else:
            if cause3 in fail_reasons: fail_reasons[cause3] += 1

    prob_c1 = (pass_c1/n_sims)*100
    prob_c2 = (pass_c2/n_sims)*100
    prob_c3 = (pass_c3/n_sims)*100
    
    avg_pay1 = sum_pay1 / pass_c1 if pass_c1 > 0 else 0
    avg_pay2 = sum_pay2 / pass_c2 if pass_c2 > 0 else 0
    avg_pay3 = sum_pay3 / pass_c3 if pass_c3 > 0 else 0
    
    time_p1 = calculate_time_metrics(trades_p1, trades_day)
    time_p2 = calculate_time_metrics(trades_p2, trades_day) if is_2step else 0
    time_c1 = calculate_time_metrics(trades_c1, trades_day)
    time_c2 = calculate_time_metrics(trades_c2, trades_day)
    time_c3 = calculate_time_metrics(trades_c3, trades_day)
    
    if prob_c1 >= 98.0: attempts = 1.0; reason="Probabilidad > 98%. 1 cuenta basta."
    elif prob_c1 <= 0.5: attempts = 100.0; reason="Probabilidad nula."
    else: attempts = 100/prob_c1; reason=f"Con {prob_c1:.1f}% prob, necesitas {math.ceil(attempts)} intentos."
    
    inv_req = math.ceil(attempts) * account_data['cost']
    salary = avg_pay1 - inv_req
    
    est_breakdown = {
        "split": split_share, "refund": account_data['cost'], "bonus": account_data.get('p1_bonus', 0), "total": pay_val_1
    }
    
    total_failures = n_sims - pass_c1
    fail_stats = {}
    if total_failures > 0:
        for k, v in fail_reasons.items(): fail_stats[k] = (v/total_failures)*100
            
    return {
        "prob_c1": prob_c1, "prob_c2": prob_c2, "prob_c3": prob_c3,
        "avg_pay1": avg_pay1, "avg_pay2": avg_pay2, "avg_pay3": avg_pay3,
        "time_p1": time_p1, "time_p2": time_p2, "time_c1": time_c1, "time_c2": time_c2, "time_c3": time_c3,
        "inventory": math.ceil(attempts), "investment": inv_req, "net_profit": salary,
        "stock_reason": reason, "first_pay_est": est_breakdown, "fail_stats": fail_stats, "total_failures": total_failures,
        "is_2step": is_2step
    }

# --- FUNCIÓN VISUALIZADORA (Con Soporte Delta) ---
def display_rich_results(results_list, title_prefix=""):
    g_inv = 0; g_pay1 = 0; g_pay2 = 0; g_pay3 = 0
    for res in results_list:
        g_inv += res['stats']['investment']
        g_pay1 += res['stats']['avg_pay1']
        g_pay2 += res['stats']['avg_pay2']
        g_pay3 += res['stats']['avg_pay3']
    
    st.markdown(f"### 📊 {title_prefix} - Resultados Consolidados")
    m1, m2, m3 = st.columns(3)
    m1.metric("Inversión Total (Riesgo)", f"${g_inv:,.0f}")
    total_potential = g_pay1 + g_pay2 + g_pay3
    roi = ((total_potential - g_inv)/g_inv)*100 if g_inv > 0 else 0
    m2.metric("Retorno Potencial (Ciclo 1)", f"${total_potential:,.0f}")
    m3.metric("ROI Potencial", f"{roi:.1f}%")
    
    st.markdown("### 💰 Proyección de Flujo de Caja")
    fc1, fc2, fc3 = st.columns(3)
    fc1.metric("Retiro 1 (Recuperación)", f"${g_pay1:,.0f}")
    fc2.metric("Retiro 2 (Beneficio)", f"${g_pay2:,.0f}")
    fc3.metric("Retiro 3 (Consistencia)", f"${g_pay3:,.0f}")
    
    st.divider()
    st.subheader("🔍 Desglose Detallado por Cuenta")
    
    for res in results_list:
        s = res['stats']
        bk = s['first_pay_est']
        
        # LÓGICA DE COMPARACIÓN (DELTA)
        # Si existe 'baseline' (Teórico) y estamos en modo Real, calculamos deltas
        d_prob = None
        d_time = None
        d_money = None
        
        if 'baseline' in res:
            b = res['baseline']
            # Prob: Más es mejor
            diff_prob = s['prob_c1'] - b['prob_c1']
            if abs(diff_prob) > 0.1: d_prob = f"{diff_prob:+.1f}%"
            
            # Time: Menos es mejor (Inverse)
            diff_time = s['time_c1'] - b['time_c1']
            if abs(diff_time) > 0.1: d_time = f"{diff_time:+.1f} m"
            
            # Money: Más es mejor
            diff_money = s['avg_pay1'] - b['avg_pay1']
            if abs(diff_money) > 10: d_money = f"{diff_money:+.0f}"

        header_text = f"📈 {res['name']}"
        if 'start_bal' in res:
             header_text += f" (Desde: ${res['start_bal']:,.0f})"
        
        with st.expander(f"{header_text} | Prob. Cobro: {s['prob_c1']:.1f}%"):
            c1, c2, c3, c4, c5 = st.columns(5)
            total_time_eval = s['time_p1'] + s['time_p2']
            c1.metric("1. Fases Eval", "En Proceso", f"⏱ {total_time_eval:.1f} m", delta_color="off")
            c2.metric("2. Stock Req.", f"{s['inventory']} u.", f"Inv: ${s['investment']:,.0f}", delta_color="off")
            
            # 1er Retiro CON DELTA
            c3.metric("1er Retiro", f"{s['prob_c1']:.1f}%", delta=d_prob)
            c3.caption(f"${s['avg_pay1']:,.0f} | ⏱ {s['time_c1']:.1f} m") # Caption para detalle secundario
            
            # 2do y 3er Retiro
            c4.metric("2do Retiro", f"{s['prob_c2']:.1f}%", f"${s['avg_pay2']:,.0f} | ⏱ {s['time_c2']:.1f} m")
            c5.metric("3er Retiro", f"{s['prob_c3']:.1f}%", f"${s['avg_pay3']:,.0f} | ⏱ {s['time_c3']:.1f} m")
            
            st.markdown("---")
            if s['total_failures'] > 0:
                st.caption("💀 **Análisis de Riesgos (Causas de fallo):**")
                f_cols = st.columns(3)
                for k, v in s['fail_stats'].items():
                    if v > 0:
                        with f_cols[list(s['fail_stats'].keys()).index(k) % 3]:
                            st.progress(int(v))
                            st.caption(f"{k}: {v:.1f}%")
            
            st.markdown("---")
            st.info(f"**Estrategia:** {s['stock_reason']}")
            st.caption("💰 **Desglose 1er Pago:**")
            col_pay1, col_pay2, col_pay3, col_pay4 = st.columns(4)
            col_pay1.metric("Split", f"${bk['split']:,.0f}")
            col_pay2.metric("Refund", f"+${bk['refund']}")
            col_pay3.metric("Bonus", f"+${bk['bonus']}")
            col_pay4.metric("TOTAL", f"${bk['total']:,.0f}", delta=d_money) # Delta en dinero tambien

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
    c_head, c_user = st.columns([4,1])
    c_head.title("💼 Portfolio Manager Pro")
    c_user.write(f"👤 **{st.session_state['username']}**")
    if c_user.button("Salir"): st.session_state['logged_in']=False; st.rerun()
    st.markdown("---")
    
    with st.sidebar:
        st.header("1. Global")
        sim_precision = st.select_slider("Simulaciones", options=[500, 1000, 5000], value=1000)
        
        c_save, c_load = st.columns(2)
        with c_save:
            if st.button("💾 Guardar", type="secondary", use_container_width=True):
                if save_portfolio_db(st.session_state['username'], st.session_state['portfolio']): st.toast("Guardado")
        with c_load:
            if st.button("🔄 Restaurar", type="secondary", use_container_width=True):
                saved = load_portfolio_db(st.session_state['username'])
                if saved:
                    st.session_state['portfolio'] = saved
                    st.rerun()
                else: st.warning("No hay datos guardados.")
        
        st.divider()
        st.header("2. Catálogo")
        s_firm = st.selectbox("Empresa", list(FIRMS_DATA.keys()))
        s_prog = st.selectbox("Programa", list(FIRMS_DATA[s_firm].keys()))
        s_size = st.selectbox("Capital", list(FIRMS_DATA[s_firm][s_prog].keys()))
        d = FIRMS_DATA[s_firm][s_prog][s_size]
        
        if st.button("➕ Agregar Cuenta", use_container_width=True):
            st.session_state['portfolio'].append({
                "id": int(time.time()*1000),
                "full_name": f"{s_firm} {s_prog} ({s_size})",
                "data": d,
                "params": {"win_rate": 45, "rr": 2.0, "risk": 1.0, "withdrawal_target": 3.0, "trades_day": 3, "comm": 7.0},
                "journal": [] 
            })
            st.toast("Agregada")

    if not st.session_state['portfolio']:
        st.info("Portafolio vacío. Agrega una cuenta para comenzar.")
    else:
        tab_teorica, tab_journal, tab_real = st.tabs(["Proyección Teórica Portafolio", "Diario / Ejecución", "Proyección Real Portafolio"])
        
        # 1. TEÓRICA
        with tab_teorica:
            st.subheader("Parametrización y Escenarios Ideales")
            for i, item in enumerate(st.session_state['portfolio']):
                if 'journal' not in item: item['journal'] = []
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
            
            st.markdown("---")
            if st.button("🚀 Simular Portafolio (TEÓRICO)", type="secondary", use_container_width=True):
                with st.spinner("Calculando Escenario Ideal..."):
                    results = []
                    for item in st.session_state['portfolio']:
                        start_bal = item['data']['size']
                        s = run_account_simulation(item['data'], item['params'], sim_precision, start_bal)
                        results.append({"name": item['full_name'], "stats": s, "start_bal": start_bal})
                    st.session_state['sim_results_theoretical'] = results
            
            if st.session_state['sim_results_theoretical']:
                display_rich_results(st.session_state['sim_results_theoretical'], title_prefix="TEÓRICO")

        # 2. DIARIO
        with tab_journal:
            st.subheader("📓 Registro de Operaciones Reales")
            for item in st.session_state['portfolio']:
                if 'journal' not in item: item['journal'] = []
                with st.expander(f"📖 {item['full_name']} - Ingresar Trades", expanded=True):
                    with st.form(key=f"form_{item['id']}"):
                        f1, f2, f3, f4 = st.columns(4)
                        t_date = f1.date_input("Fecha")
                        t_gross = f2.number_input("Bruto ($)", value=0.0, step=10.0)
                        t_comm = f3.number_input("Comisión ($)", value=0.0, step=1.0)
                        t_swap = f4.number_input("Swap ($)", value=0.0, step=1.0)
                        if st.form_submit_button("💾 Registrar Trade"):
                            net = t_gross - t_comm - t_swap
                            item['journal'].append({"date": str(t_date), "gross": t_gross, "comm": t_comm, "swap": t_swap, "net": net})
                            st.success(f"Trade guardado: ${net:.2f}"); st.rerun()

                    if item['journal']:
                        df_j = pd.DataFrame(item['journal'])
                        total_pnl = df_j['net'].sum()
                        current_bal = item['data']['size'] + total_pnl
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Balance Inicial", f"${item['data']['size']:,.0f}")
                        c2.metric("P&L Acumulado", f"${total_pnl:,.2f}", delta_color="normal")
                        c3.metric("Balance ACTUAL", f"${current_bal:,.2f}")
                        st.dataframe(df_j.tail(5), use_container_width=True)
                    else: st.info("Sin trades registrados.")

# 3. PROYECCIÓN REAL (OPTIMIZADA)
        with tab_real:
            total_trades_count = sum(len(item.get('journal', [])) for item in st.session_state['portfolio'])
            
            if total_trades_count == 0:
                st.info("⚠️ Para generar una Proyección Real, primero debes registrar al menos una operación en la pestaña 'Diario / Ejecución'.")
                st.caption("Esta sección compara tu realidad vs el plan ideal.")
            else:
                if st.button("🚀 Proyectar desde Balance Actual (REAL)", type="primary", use_container_width=True):
                    with st.spinner("Ejecutando Montecarlo desde tu realidad..."):
                        results = []
                        
                        # --- LÓGICA DE REUTILIZACIÓN ---
                        # Verificamos si ya tenemos la teórica en caché
                        theoretical_cache = {}
                        if st.session_state.get('sim_results_theoretical'):
                            # Creamos un mapa rápido {nombre_cuenta: stats_teoricos}
                            for t_res in st.session_state['sim_results_theoretical']:
                                theoretical_cache[t_res['name']] = t_res['stats']
                        
                        for item in st.session_state['portfolio']:
                            if 'journal' not in item: item['journal'] = []
                            
                            # 1. Simulación Real (Siempre se calcula nueva)
                            start_bal_real = item['data']['size'] + sum(t['net'] for t in item['journal'])
                            s_real = run_account_simulation(item['data'], item['params'], sim_precision, start_bal_real)
                            
                            # 2. Simulación Base (Teórica)
                            # Intentamos sacarla del caché, si no existe, la calculamos on-the-fly
                            if item['full_name'] in theoretical_cache:
                                s_theory = theoretical_cache[item['full_name']]
                            else:
                                # Cálculo forzoso solo si no existe previo
                                s_theory = run_account_simulation(item['data'], item['params'], sim_precision, item['data']['size'])
                            
                            results.append({
                                "name": item['full_name'], 
                                "stats": s_real, 
                                "start_bal": start_bal_real,
                                "baseline": s_theory # Aquí pasamos la base para el Delta
                            })
                        
                        st.session_state['sim_results_real'] = results
                
                if st.session_state['sim_results_real']:
                    display_rich_results(st.session_state['sim_results_real'], title_prefix="REAL")