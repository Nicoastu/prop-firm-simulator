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

# --- BASE DE DATOS (Solo Usuarios) ---
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

if engine: init_db()

# --- DATOS DE EMPRESAS (Solo High Stakes) ---
FIRMS_DATA = {
    "The5ers": {
        "High Stakes (2 Step)": {
            "5K":   {"cost": 39,  "size": 5000,   "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 5},
            "10K":  {"cost": 78,  "size": 10000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 10},
            "20K":  {"cost": 165, "size": 20000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 15},
            "60K":  {"cost": 329, "size": 60000,  "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 25},
            "100K": {"cost": 545, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit_p1": 8.0, "profit_p2": 5.0, "p1_bonus": 40}
        }
    },
    # Mantenemos otras firmas para comparación si el usuario lo desea, 
    # pero Hyper Growth ha sido eliminado.
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
    
    # Límite de pérdida diaria es un MONTO FIJO basado en el Balance Inicial
    fixed_daily_loss_amount = initial_balance * (daily_dd_pct / 100)
    
    while curr > static_limit and curr < target_equity and trades < max_trades:
        trades += 1
        trades_today += 1
        
        # Reset Diario
        if trades_today > trades_per_day:
            day_start_equity = curr 
            trades_today = 1        
            
        # Operativa
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
            
        # --- DIAGNÓSTICO DE MUERTE ---
        # A. Max DD Estático
        if curr <= static_limit:
            return False, trades, curr, "Max Drawdown (Total)"
            
        # B. Daily DD (Límite Fijo sobre Balance Inicial)
        current_daily_drawdown = day_start_equity - curr
        if current_daily_drawdown >= fixed_daily_loss_amount:
            return False, trades, curr, "Daily Drawdown"
            
    # Si sale del bucle por Target
    if curr >= target_equity:
        return True, trades, curr, "Success"
    else:
        # Si sale del bucle por Timeout
        return False, trades, curr, "Timeout (Lento)"

def calculate_time_metrics(trades_list, trades_per_day):
    if not trades_list: return 0.0
    avg_trades = sum(trades_list) / len(trades_list)
    trading_days = avg_trades / trades_per_day
    months = trading_days / 20.0
    return months

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
    
    fail_reasons = {"Max Drawdown (Total)": 0, "Daily Drawdown": 0, "Timeout (Lento)": 0}
    
    trades_p1 = []; trades_p2 = []; trades_c1 = []; trades_c2 = []; trades_c3 = []
    sum_pay1 = 0; sum_pay2 = 0; sum_pay3 = 0
    
    is_2step = firm.get('profit_p2', 0) > 0
    
    # Payouts Teóricos (Estrictos al Target)
    target_amount = firm['size'] * (w_target / 100)
    split_share = target_amount * 0.80
    pay_val_1 = split_share + firm['cost'] + firm.get('p1_bonus', 0)
    pay_val_2 = split_share
    pay_val_3 = split_share
    
    for _ in range(n_sims):
        # FASE 1
        ok1, t1, _, cause1 = simulate_phase(firm['size'], firm['size'], risk, wr, rr, firm['profit_p1'], firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
        if not ok1: 
            if cause1 in fail_reasons: fail_reasons[cause1] += 1
            continue
        pass_p1 += 1
        trades_p1.append(t1)
        
        # FASE 2
        if is_2step:
            ok2, t2, _, cause2 = simulate_phase(firm['size'], firm['size'], risk, wr, rr, firm['profit_p2'], firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day)
            if not ok2: 
                if cause2 in fail_reasons: fail_reasons[cause2] += 1
                continue
            pass_p2 += 1
            trades_p2.append(t2)
        else:
            pass_p2 += 1
            
        # RETIRO 1
        ok_c1, tc1, _, cause3 = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
        if ok_c1:
            pass_c1 += 1
            trades_c1.append(tc1)
            sum_pay1 += pay_val_1
            
            # RETIRO 2
            ok_c2, tc2, _, _ = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
            if ok_c2:
                pass_c2 += 1
                trades_c2.append(tc2)
                sum_pay2 += pay_val_2
                
                # RETIRO 3
                ok_c3, tc3, _, _ = simulate_phase(firm['size'], firm['size'], risk, wr, rr, w_target, firm['total_dd'], daily_dd, comm, sl_min, sl_max, trades_day, is_funded=True)
                if ok_c3:
                    pass_c3 += 1
                    trades_c3.append(tc3)
                    sum_pay3 += pay_val_3
        else:
            if cause3 in fail_reasons: fail_reasons[cause3] += 1

    # Métricas
    prob_p1 = (pass_p1/n_sims)*100
    prob_p2 = (pass_p2/n_sims)*100 if is_2step else 100.0
    prob_c1 = (pass_c1/n_sims)*100
    prob_c2 = (pass_c2/n_sims)*100
    prob_c3 = (pass_c3/n_sims)*100
    
    # TIEMPOS
    time_p1 = calculate_time_metrics(trades_p1, trades_day)
    time_p2 = calculate_time_metrics(trades_p2, trades_day) if is_2step else 0
    time_c1 = calculate_time_metrics(trades_c1, trades_day)
    time_c2 = calculate_time_metrics(trades_c2, trades_day)
    time_c3 = calculate_time_metrics(trades_c3, trades_day)
    total_time_to_cash = time_p1 + time_p2 + time_c1
    
    # LÓGICA DE STOCK
    if prob_c1 >= 98.0: 
        attempts = 1.0
        stock_reason = "Probabilidad > 98%. Estadísticamente 1 cuenta es suficiente."
    elif prob_c1 <= 0.5:
        attempts = 100.0 
        stock_reason = "Probabilidad nula. Estrategia no viable."
    else: 
        attempts = 100/prob_c1 
        stock_reason = f"Con una probabilidad de éxito del {prob_c1:.1f}%, la estadística dicta que necesitas {math.ceil(attempts)} intentos (100 / {prob_c1:.1f}) para asegurar 1 éxito."

    inventory = math.ceil(attempts)
    investment = inventory * firm['cost']
    
    avg_pay1 = sum_pay1 / pass_c1 if pass_c1 > 0 else 0
    avg_pay2 = sum_pay2 / pass_c2 if pass_c2 > 0 else 0
    avg_pay3 = sum_pay3 / pass_c3 if pass_c3 > 0 else 0
    
    salary = (avg_pay1 - investment)
    
    est_pay_breakdown = {
        "split": split_share,
        "refund": firm['cost'],
        "bonus": firm.get('p1_bonus', 0),
        "total": pay_val_1
    }
    
    # Diagnóstico Fallos
    total_failures = n_sims - pass_c1
    failure_stats = {}
    if total_failures > 0:
        for k, v in fail_reasons.items():
            failure_stats[k] = (v / total_failures) * 100
    
    return {
        "prob_p1": prob_p1, "prob_p2": prob_p2, 
        "prob_c1": prob_c1, "prob_c2": prob_c2, "prob_c3": prob_c3,
        "time_p1": time_p1, "time_p2": time_p2, 
        "time_c1": time_c1, "time_c2": time_c2, "time_c3": time_c3,
        "avg_pay1": avg_pay1, "avg_pay2": avg_pay2, "avg_pay3": avg_pay3,
        "inventory": inventory, "investment": investment, "stock_reason": stock_reason,
        "net_profit": salary, "months_total": total_time_to_cash,
        "is_2step": is_2step, "first_pay_est": est_pay_breakdown,
        "failure_stats": failure_stats, "total_failures": total_failures
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
            with st.spinner(f"Simulando tiempos y pagos..."):
                results = []
                g_inv = 0; g_net = 0
                g_pay1 = 0; g_pay2 = 0; g_pay3 = 0
                
                for item in st.session_state['portfolio']:
                    s = run_account_simulation(item['data'], item['params'], sim_precision)
                    g_inv += s['investment']; g_net += s['net_profit']
                    g_pay1 += s['avg_pay1']; g_pay2 += s['avg_pay2']; g_pay3 += s['avg_pay3']
                    results.append({"name": item['full_name'], "stats": s})
                
                # --- RESULTADOS ---
                st.markdown("### 📊 Resultados Consolidados")
                m1, m2, m3 = st.columns(3)
                m1.metric("Inversión Total", f"${g_inv:,.0f}")
                m2.metric("Beneficio Neto (Ciclo 1)", f"${g_net:,.0f}")
                roi = (g_net / g_inv * 100) if g_inv > 0 else 0
                m3.metric("ROI Potencial", f"{roi:.1f}%")
                
                st.markdown("### 💰 Proyección de Flujo de Caja Combinado")
                fc1, fc2, fc3 = st.columns(3)
                fc1.metric("Total Retiro 1", f"${g_pay1:,.0f}")
                fc2.metric("Total Retiro 2", f"${g_pay2:,.0f}")
                fc3.metric("Total Retiro 3", f"${g_pay3:,.0f}")
                
                st.divider()
                st.subheader("🔍 Detalle de Retención y Tiempos")
                
                for res in results:
                    s = res['stats']
                    bk = s['first_pay_est']
                    with st.expander(f"📈 {res['name']} (Prob. 1er Cobro: {s['prob_c1']:.1f}%)"):
                        # Fila 1: Probabilidad y Tiempo
                        c1, c2, c3, c4, c5 = st.columns(5)
                        
                        c1.metric("1. Fase 1", f"{s['prob_p1']:.1f}%", f"⏱ {s['time_p1']:.1f} Meses", delta_color="off")
                        p2_label = f"{s['prob_p2']:.1f}%" if s['is_2step'] else "N/A"
                        p2_time = f"⏱ {s['time_p2']:.1f} Meses" if s['is_2step'] else "-"
                        c2.metric("2. Fase 2", p2_label, p2_time, delta_color="off")
                        c3.metric("3. Retiro 1", f"{s['prob_c1']:.1f}%", f"${s['avg_pay1']:,.0f} | ⏱ {s['time_c1']:.1f} m")
                        c4.metric("4. Retiro 2", f"{s['prob_c2']:.1f}%", f"${s['avg_pay2']:,.0f} | ⏱ {s['time_c2']:.1f} m")
                        c5.metric("5. Retiro 3", f"{s['prob_c3']:.1f}%", f"${s['avg_pay3']:,.0f} | ⏱ {s['time_c3']:.1f} m")
                        
                        st.markdown("---")
                        
                        # DIAGNÓSTICO DE MUERTE
                        if s['total_failures'] > 0:
                            st.caption("💀 **Feedback de Fallo (Distribución de causas):**")
                            f_cols = st.columns(3)
                            fail_stats = s['failure_stats']
                            
                            with f_cols[0]:
                                v = fail_stats.get('Max Drawdown (Total)', 0)
                                st.progress(int(v))
                                st.caption(f"Max Drawdown: {v:.1f}%")
                            
                            with f_cols[1]:
                                v = fail_stats.get('Daily Drawdown', 0)
                                st.progress(int(v))
                                st.caption(f"Daily Drawdown: {v:.1f}%")
                                
                            with f_cols[2]:
                                v = fail_stats.get('Timeout (Lento)', 0)
                                st.progress(int(v))
                                st.caption(f"Lento/Timeout: {v:.1f}%")
                        else:
                            st.success("🎉 ¡Felicidades! En esta simulación no hubo fallos (Prob 100%).")

                        st.markdown("---")
                        # RACIONAL DE STOCK
                        st.caption("💡 **Racional de Inversión:**")
                        st.info(f"**Stock Sugerido: {s['inventory']} Cuentas.** \n\n {s['stock_reason']}")
                        
                        st.markdown("---")
                        st.caption("💰 **Desglose del 1er Payout:**")
                        col_pay1, col_pay2, col_pay3, col_pay4 = st.columns(4)
                        col_pay1.metric("Split", f"${bk['split']:,.0f}")
                        col_pay2.metric("Refund", f"+${bk['refund']}")
                        col_pay3.metric("Bonus", f"+${bk['bonus']}")
                        col_pay4.metric("TOTAL", f"${bk['total']:,.0f}", delta="Neto")