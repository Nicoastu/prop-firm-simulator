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
st.set_page_config(page_title="Prop Firm Business Planner", page_icon="💼", layout="wide")

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

# --- DATOS JERÁRQUICOS ---
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
def simulate_phase(balance, risk_money, win_rate, rr, profit_target_pct, max_total_dd_pct, comm_per_lot, pip_val, sl_min, sl_max, is_funded=False):
    curr = balance
    # En cuenta fondeada, definimos "Exito de cobro" como sobrevivir y hacer al menos 2%
    target_equity = balance + (balance * (profit_target_pct/100)) if not is_funded else balance + (balance * 0.02) 
    limit_equity = balance - (balance * (max_total_dd_pct/100))
    trades = 0
    
    # Límite técnico para evitar bucles infinitos
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

def run_business_simulation(firm_data, risk_pct, win_rate, rr, trades_per_day, comm, sl_min, sl_max):
    n_sims = 1000
    
    pass_p1 = 0
    pass_p2 = 0 # Si es 1-step, esto será igual a pass_p1
    pass_payout = 0 
    
    total_trades_p1 = []
    total_trades_p2 = []
    total_trades_payout = []
    
    total_payout_amount = 0
    
    balance = firm_data['size']
    risk_money = balance * (risk_pct / 100)
    pip_val = 10 
    is_two_step = firm_data.get('profit_p2', 0) > 0
    
    for _ in range(n_sims):
        # 1. FASE 1
        p1_ok, t1, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p1'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
        
        if not p1_ok: continue
        pass_p1 += 1
        total_trades_p1.append(t1)
            
        # 2. FASE 2
        trades_this_p2 = 0
        if is_two_step:
            p2_ok, t2, _ = simulate_phase(balance, risk_money, win_rate, rr, firm_data['profit_p2'], firm_data['total_dd'], comm, pip_val, sl_min, sl_max)
            if not p2_ok: continue
            pass_p2 += 1
            trades_this_p2 = t2
        else:
            pass_p2 += 1
        
        total_trades_p2.append(trades_this_p2)
        
        # 3. FASE FONDEADA (Hasta primer cobro)
        funded_ok, t3, final_balance = simulate_phase(balance, risk_money, win_rate, rr, 0, firm_data['total_dd'], comm, pip_val, sl_min, sl_max, is_funded=True)
        
        if funded_ok:
            pass_payout += 1
            total_trades_payout.append(t3)
            
            profit = final_balance - balance
            payout_val = (profit * 0.8) + firm_data['cost'] + firm_data.get('p1_bonus', 0)
            total_payout_amount += payout_val

    # --- ESTADÍSTICAS DE TIEMPO Y NEGOCIO ---
    
    # Probabilidades
    prob_funded = (pass_p2 / n_sims) * 100
    prob_cash = (pass_payout / n_sims) * 100
    
    # Tiempo Promedio (Días de Trading)
    avg_trades_p1 = sum(total_trades_p1) / len(total_trades_p1) if total_trades_p1 else 0
    avg_trades_p2 = sum(total_trades_p2) / len(total_trades_p2) if total_trades_p2 else 0
    avg_trades_pay = sum(total_trades_payout) / len(total_trades_payout) if total_trades_payout else 0
    
    # Convertir Trades a Días de Calendario (Aprox 20 días trading = 1 mes calendario)
    total_trading_days = (avg_trades_p1 + avg_trades_p2 + avg_trades_pay) / trades_per_day if trades_per_day > 0 else 999
    
    # Meses Reales hasta Liquidez (Asumiendo pausas, fines de semana, etc)
    months_to_liquidity = total_trading_days / 20 
    
    # Dinero
    avg_first_payout = total_payout_amount / pass_payout if pass_payout > 0 else 0
    
    # Unit Economics
    attempts_needed = 100 / prob_cash if prob_cash > 0 else 100
    inventory_needed = math.ceil(attempts_needed) # Cuentas a comprar
    total_investment = inventory_needed * firm_data['cost']
    
    # ROI Mensualizado
    # Profit Neto = Payout - InversionTotal
    # ROI Mensual = Profit Neto / Meses que tardaste
    net_profit = avg_first_payout - total_investment
    monthly_salary_equiv = net_profit / months_to_liquidity if months_to_liquidity > 0 else 0

    return {
        "prob_cash": prob_cash,
        "inventory": inventory_needed,
        "investment": total_investment,
        "months_time": months_to_liquidity,
        "first_payout": avg_first_payout,
        "net_profit": net_profit,
        "monthly_salary": monthly_salary_equiv,
        "trading_days_total": total_trading_days
    }

# --- FRONTEND ---
if not st.session_state['logged_in']:
    st.title("🛡️ Prop Firm Business Planner")
    # (Mismo código de login que antes...)
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
    # --- DASHBOARD EMPRESARIAL ---
    col_h1, col_h2 = st.columns([3,1])
    col_h1.title("💼 Prop Firm Business Planner")
    col_h2.write(f"Empresario: **{st.session_state['username']}**")
    if col_h2.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False; st.rerun()
    st.markdown("---")

    # SIDEBAR
    st.sidebar.header("1. El Producto (Cuenta)")
    sel_company = st.sidebar.selectbox("Empresa", list(FIRMS_DATA.keys()))
    sel_program = st.sidebar.selectbox("Programa", list(FIRMS_DATA[sel_company].keys()))
    sel_size = st.sidebar.selectbox("Capital", list(FIRMS_DATA[sel_company][sel_program].keys()))
    firm = FIRMS_DATA[sel_company][sel_program][sel_size]
    full_name_db = f"{sel_company} - {sel_program} ({sel_size})"
    
    st.sidebar.header("2. Tu Operativa (Insumos)")
    trades_day = st.sidebar.number_input("Trades por Día", 0.1, 20.0, 2.0, help="Frecuencia real promedio")
    wr = st.sidebar.slider("Win Rate (%)", 20, 80, 45)
    rr = st.sidebar.slider("Ratio R:R", 0.5, 5.0, 2.0)
    risk = st.sidebar.slider("Riesgo por Trade (%)", 0.1, 3.0, 1.0)
    
    st.sidebar.header("3. Costos Variables")
    comm = st.sidebar.number_input("Comisión ($/Lote)", 0.0, 10.0, 7.0)
    c_sl1, c_sl2 = st.sidebar.columns(2)
    sl_min = c_sl1.number_input("SL Mín", 1, 100, 5)
    sl_max = c_sl2.number_input("SL Max", 1, 200, 15)

    # REGLAS VISIBLES
    st.markdown("### 📋 Ficha Técnica del Activo")
    is_2step = firm.get('profit_p2', 0) > 0
    target_txt = f"{firm['profit_p1']}% (F1) / {firm['profit_p2']}% (F2)" if is_2step else f"{firm['profit_p1']}%"
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Costo Unitario", f"${firm['cost']}", border=True)
    r2.metric("Objetivos", target_txt, border=True)
    r3.metric("Drawdown Max", f"{firm['total_dd']}%", f"Diario: {firm.get('daily_dd',0)}%", border=True)
    r4.metric("Capital Nominal", f"${firm['size']:,}", border=True)

    if st.button("🚀 Generar Plan de Negocios", type="primary", use_container_width=True):
        
        with st.spinner("Calculando tiempos, costos y proyecciones de flujo de caja..."):
            stats = run_business_simulation(firm, risk, wr, rr, trades_day, comm, sl_min, sl_max)
            save_plan_db(st.session_state['username'], full_name_db, wr, rr, stats['prob_cash'], stats['investment'])

        # --- RESULTADOS: ENFOQUE EMPRESARIAL ---
        
        st.divider()
        
        # 1. INVENTARIO (CUANTAS COMPRAR)
        st.subheader("1. Estrategia de Inversión (Inventory)")
        
        inv_col1, inv_col2, inv_col3 = st.columns(3)
        
        inv_col1.metric("Probabilidad Real de Cobro", f"{stats['prob_cash']:.1f}%", 
                       help="Probabilidad de pasar todas las fases y realizar el primer retiro.")
        
        inv_col2.metric("Stock Necesario (Cuentas)", f"{stats['inventory']} Unidades", 
                       help="Para garantizar estadísticamente el éxito, debes tener presupuesto para comprar esta cantidad de cuentas.")
        
        inv_col3.metric("Capital de Riesgo Total", f"${stats['investment']}", 
                       f"Buffer de {stats['inventory']} intentos", delta_color="inverse")

        # 2. TIEMPO (CUANTO TARDARÉ)
        st.subheader("2. Tiempo hasta Liquidez (Time to Cash)")
        
        time_col1, time_col2 = st.columns(2)
        
        months_clean = f"{stats['months_time']:.1f} Meses"
        days_clean = f"{int(stats['trading_days_total'])} Días Operativos"
        
        time_color = "normal"
        if stats['months_time'] > 4: time_color = "inverse" # Alerta si tarda mucho
        
        time_col1.metric("Tiempo Estimado hasta 1er Cobro", months_clean, days_clean, delta_color=time_color)
        
        time_msg = "⏱️ Velocidad Óptima"
        if stats['months_time'] > 6:
            time_msg = "⚠️ Demasiado Lento: El costo de oportunidad es alto."
            st.warning(f"OJO: Tardarías **{months_clean}** en cobrar. Considera aumentar la frecuencia operativa (Trades/día) o el riesgo para acelerar el flujo de caja, aunque aumente el riesgo de quema.")
        else:
            st.success(f"✅ Buen Ritmo: Cobrar en **{months_clean}** es un ciclo de negocio saludable.")

        # 3. RENTABILIDAD (SUELDO)
        st.subheader("3. Viabilidad Financiera (Bottom Line)")
        
        fin_col1, fin_col2, fin_col3 = st.columns(3)
        
        fin_col1.metric("Primer Payout Estimado", f"${stats['first_payout']:,.0f}", help="Ingreso Bruto esperado")
        
        fin_col2.metric("Beneficio Neto (Post-Costos)", f"${stats['net_profit']:,.0f}", 
                       help="Payout - Inversión Total en cuentas")
        
        fin_col3.metric("Salario Mensual Equivalente", f"${stats['monthly_salary']:,.0f} / mes", 
                       help="Tu beneficio neto dividido por el tiempo que tardaste. ¿Vale la pena tu tiempo por este sueldo?")
        
        if stats['monthly_salary'] < 500:
            st.error("❌ Negocio NO Viable: Tu esfuerzo paga menos que un salario mínimo. Revisa tu estrategia.")
        elif stats['monthly_salary'] > 2000:
            st.balloons()
            st.success("🚀 Negocio Altamente Rentable: ¡Tienes una máquina de hacer dinero!")
        else:
            st.info("⚠️ Negocio Marginal: Es rentable, pero revisa si compensa tu tiempo.")

    st.divider()
    with st.expander("📜 Historial de Planes"):
        planes = get_user_plans(st.session_state['username'])
        if planes: st.dataframe(pd.DataFrame(planes, columns=["Empresa", "Prob Cobro %", "Inversión Total $", "Fecha"]), use_container_width=True)