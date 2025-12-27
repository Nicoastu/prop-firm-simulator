import streamlit as st
import random
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time
import math # Importamos math para redondear intentos hacia arriba

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

# --- DATOS ESTRUCTURADOS DE EMPRESAS ---
# Actualizado con The5ers Hyper Growth (1 Step)
FIRMS_DATA = {
    "The5ers": {
        "Hyper Growth - 5K": {
            "cost": 260, "size": 5000, "daily_dd": 3.0, "total_dd": 6.0, "profit": 10.0, "bonus": 15
        },
        "Hyper Growth - 10K": {
            "cost": 450, "size": 10000, "daily_dd": 3.0, "total_dd": 6.0, "profit": 10.0, "bonus": 25
        },
        "Hyper Growth - 20K": {
            "cost": 850, "size": 20000, "daily_dd": 3.0, "total_dd": 6.0, "profit": 10.0, "bonus": 50
        }
    },
    "FTMO": {
        "Swing - 100k": {
            "cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 10.0, "bonus": 0
        },
        "Normal - 100k": {
            "cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 10.0, "bonus": 0
        }
    },
    "FundedNext": {
        "Stellar - 100k": {
            "cost": 519, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0, "bonus": 0
        }
    }
}

# --- SIMULACIÓN DINÁMICA ---
def run_dynamic_simulation(balance, risk_pct, win_rate, rr, profit_target, max_total_dd, 
                          trades_per_day, comm_per_lot, sl_min, sl_max):
    
    n_sims = 1000
    passed_count = 0
    total_trades_log = []
    max_losing_streak_log = []
    equity_curves = [] 
    avg_lots_used_log = []
    
    risk_money = balance * (risk_pct / 100)
    pip_value_std = 10 
    
    limit_equity = balance - (balance * (max_total_dd/100))
    target_equity = balance + (balance * (profit_target/100))
    
    for i in range(n_sims):
        curr = balance
        trades = 0
        current_streak = 0
        max_streak = 0
        curve = [curr]
        
        while curr > limit_equity and curr < target_equity and trades < 1000:
            trades += 1
            
            # Dinámica de Mercado
            current_trade_sl = random.uniform(sl_min, sl_max)
            
            current_lot_size = risk_money / (current_trade_sl * pip_value_std)
            if i < 5: avg_lots_used_log.append(current_lot_size)
            
            trade_commission = current_lot_size * comm_per_lot
            
            if random.random() < (win_rate/100):
                gross_profit = risk_money * rr
                net_profit = gross_profit - trade_commission
                curr += net_profit
                current_streak = 0
            else:
                total_loss = risk_money + trade_commission
                curr -= total_loss
                current_streak += 1
                if current_streak > max_streak: max_streak = current_streak
            
            if i < 20: curve.append(curr)
                
        if curr >= target_equity:
            passed_count += 1
            total_trades_log.append(trades)
        
        max_losing_streak_log.append(max_streak)
        if i < 20: equity_curves.append(curve)

    pass_rate = (passed_count / n_sims) * 100
    avg_trades = sum(total_trades_log) / len(total_trades_log) if total_trades_log else 0
    avg_days = avg_trades / trades_per_day if trades_per_day > 0 else 0
    avg_max_streak = sum(max_losing_streak_log) / len(max_losing_streak_log)
    avg_lot_metric = sum(avg_lots_used_log) / len(avg_lots_used_log) if avg_lots_used_log else 0
    
    return pass_rate, avg_days, avg_max_streak, equity_curves, avg_lot_metric

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
    # --- DASHBOARD LOGUEADO ---
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("🛡️ Prop Firm Unit Economics")
    col_h2.write(f"👤 {st.session_state['username']}")
    if col_h2.button("Salir"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # --- SIDEBAR (SELECCIÓN JERÁRQUICA) ---
    st.sidebar.header("1. La Empresa")
    
    selected_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    selected_account_name = st.sidebar.selectbox("Tipo de Cuenta", list(FIRMS_DATA[selected_company].keys()))
    
    firm = FIRMS_DATA[selected_company][selected_account_name]
    full_firm_name = f"{selected_company} - {selected_account_name}"
    
    # Mostrar Reglas
    st.sidebar.markdown(f"""
    **Reglas Cargadas:**
    * 💰 Costo Unitario: **${firm['cost']}**
    * 📉 Max DD: **{firm['total_dd']}%** (Pausa Diaria: {firm.get('daily_dd', 0)}%)
    * 🎯 Objetivo: **{firm['profit']}%**
    * 🎁 Bonus Fondeo: **${firm.get('bonus', 0)}**
    """)

    st.sidebar.header("2. Gestión de Riesgo")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo Fijo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. Realidad de Mercado")
    trades_day = st.sidebar.number_input("Trades por día", 1, 20, 3)
    comm = st.sidebar.number_input("Comisión ($ por Lote)", 0.0, 10.0, 7.0)
    
    st.sidebar.caption("Variabilidad del Stop Loss")
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mín (Pips)", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Max (Pips)", 1, 200, 15)

    if st.button("🚀 Simular Negocio", type="primary", use_container_width=True):
        
        with st.spinner(f"Simulando {full_firm_name}..."):
            prob, days, streak, curves, avg_lot = run_dynamic_simulation(
                firm['size'], risk, wr, rr, firm['profit'], firm['total_dd'],
                trades_day, comm, sl_min, sl_max
            )
            
            # --- CÁLCULO DE PRESUPUESTO REALISTA (ENTEROS) ---
            # Si prob es 50%, necesitas 2 intentos (1/0.5). Usamos math.ceil para redondear hacia arriba.
            # Ejemplo: Si necesitas 1.1 intentos, tienes que comprar 2 cuentas.
            attempts_needed_math = 100/prob if prob > 0 else 100
            attempts_recommended = math.ceil(attempts_needed_math)
            
            # Si la probabilidad es muy alta (>90%), asumimos 1 intento es seguro.
            if prob > 90: attempts_recommended = 1
            
            budget_suggested = attempts_recommended * firm['cost']
            
            save_plan_db(st.session_state['username'], full_firm_name, wr, rr, prob, budget_suggested)

        # --- RESULTADOS VISUALES ---
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        kpi1.metric("Probabilidad Éxito", f"{prob:.1f}%")
        kpi2.metric("Costo Unitario", f"${firm['cost']}", help="Lo que pagas por UN intento.")
        
        # Métrica condicional de alerta
        color_presupuesto = "normal"
        label_presupuesto = "Capital Sugerido"
        if attempts_recommended > 1:
            label_presupuesto = f"⚠️ Sugerencia: {attempts_recommended} Intentos"
            color_presupuesto = "inverse" # Lo destaca en rojo/negro
            
        kpi3.metric(label_presupuesto, f"${budget_suggested}", 
                   help=f"Como tu probabilidad es {prob:.1f}%, existe un riesgo real de perder la primera cuenta. Te sugerimos tener capital para {attempts_recommended} intentos.",
                   delta_color=color_presupuesto)
                   
        kpi4.metric("Días Estimados", f"{int(days)}")

        st.markdown(f"""
        ### ⚖️ Análisis de The5ers - Hyper Growth
        * Estás operando una cuenta de **${firm['size']:,}**.
        * El costo de cada intento es **${firm['cost']}**.
        * Según tu probabilidad, **{'te sugerimos tener dinero para reintentar (Back-up)' if attempts_recommended > 1 else 'es muy probable que pases a la primera'}**.
        * Costo promedio de comisiones: **${(avg_lot*comm):.2f}** por trade.
        """)

        st.subheader("🔮 Curvas de Equity (20 Simulaciones)")
        chart_data = pd.DataFrame()
        max_len = max(len(c) for c in curves)
        for idx, c in enumerate(curves):
            extended_c = c + [np.nan] * (max_len - len(c))
            chart_data[f"Sim {idx}"] = extended_c 
        st.line_chart(chart_data, height=300)

    st.divider()
    with st.expander("📜 Historial"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob %", "Presupuesto $", "Fecha"]), use_container_width=True)