import streamlit as st
import random
import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
import os

# Configuración inicial
st.set_page_config(page_title="Prop Firm Unit Economics", page_icon="🛡️", layout="wide")

# --- CONEXIÓN BASE DE DATOS ---
# Intentamos conectar solo si existe la variable (para evitar errores en local si no configuraste)
db_url = os.getenv("DATABASE_URL")
engine = None

if db_url:
    try:
        # Ajuste necesario para SQLAlchemy con URLs de Railway (postgres:// -> postgresql://)
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url)
    except Exception as e:
        st.error(f"Error conectando a BD: {e}")

# --- FUNCIONES DE BASE DE DATOS ---
def init_db():
    """Crea las tablas si no existen"""
    if engine:
        with engine.connect() as conn:
            # Tabla Usuarios
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT
                );
            """))
            # Tabla Planes Guardados
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

def register_user(username, password):
    if not engine: return False
    try:
        with engine.connect() as conn:
            # Verificar si existe
            res = conn.execute(text("SELECT username FROM users WHERE username = :u"), {"u": username}).fetchone()
            if res:
                return False # Ya existe
            conn.execute(text("INSERT INTO users (username, password) VALUES (:u, :p)"), {"u": username, "p": password})
            conn.commit()
            return True
    except:
        return False

def login_user(username, password):
    if not engine: return False
    with engine.connect() as conn:
        res = conn.execute(text("SELECT password FROM users WHERE username = :u"), {"u": username}).fetchone()
        if res and res[0] == password:
            return True
    return False

def save_plan_db(username, firm, wr, rr, prob, inv):
    if engine:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO plans (username, firm_name, win_rate, risk_reward, pass_prob, investment_needed)
                VALUES (:u, :f, :w, :r, :p, :i)
            """), {"u": username, "f": firm, "w": wr, "r": rr, "p": prob, "i": inv})
            conn.commit()

def get_user_plans(username):
    if not engine: return []
    with engine.connect() as conn:
        result = conn.execute(text("SELECT firm_name, pass_prob, investment_needed, created_at FROM plans WHERE username = :u ORDER BY created_at DESC"), {"u": username})
        return result.fetchall()

# Inicializar BD al arrancar
if engine:
    init_db()

# --- DATOS Y LÓGICA (Igual que antes) ---
PROP_FIRMS = {
    "FTMO - 100k Swing": {"cost": 540, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 10.0},
    "FundedNext - 100k Stellar": {"cost": 519, "size": 100000, "daily_dd": 5.0, "total_dd": 10.0, "profit": 8.0},
    "Apex - 50k Futures": {"cost": 167, "size": 50000, "daily_dd": 0.0, "total_dd": 4.0, "profit": 6.0}
}

def run_simulation(balance, risk_pct, win_rate, rr, profit_target, max_total_dd):
    passed = 0
    sims = 500 # Reducido para rapidez en ejemplo
    risk_amt = balance * (risk_pct/100)
    win_amt = risk_amt * rr
    limit = balance - (balance * (max_total_dd/100))
    target = balance + (balance * (profit_target/100))
    
    for _ in range(sims):
        curr = balance
        trades = 0
        while curr > limit and curr < target and trades < 500:
            trades += 1
            if random.random() < (win_rate/100): curr += win_amt
            else: curr -= risk_amt
        if curr >= target: passed += 1
            
    return (passed/sims)*100

# --- GESTIÓN DE ESTADO (LOGIN) ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

# --- INTERFAZ PRINCIPAL ---

if not st.session_state['logged_in']:
    # VISTA DE LOGIN / REGISTRO
    st.title("🔐 Acceso a Prop Firm Planner")
    
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab1:
        l_user = st.text_input("Usuario", key="l_u")
        l_pass = st.text_input("Contraseña", type="password", key="l_p")
        if st.button("Entrar"):
            if login_user(l_user, l_pass):
                st.session_state['logged_in'] = True
                st.session_state['username'] = l_user
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")

    with tab2:
        r_user = st.text_input("Nuevo Usuario", key="r_u")
        r_pass = st.text_input("Nueva Contraseña", type="password", key="r_p")
        if st.button("Crear Cuenta"):
            if register_user(r_user, r_pass):
                st.success("Cuenta creada. Ahora puedes iniciar sesión.")
            else:
                st.error("El usuario ya existe o hubo un error.")

else:
    # VISTA DE LA APLICACIÓN (DASHBOARD)
    st.sidebar.write(f"👤 Hola, **{st.session_state['username']}**")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False
        st.rerun()
    
    st.title("🛡️ Prop Firm Unit Economics")
    
    # --- INPUTS ---
    col1, col2 = st.columns(2)
    with col1:
        firm_name = st.selectbox("Empresa", list(PROP_FIRMS.keys()))
        firm = PROP_FIRMS[firm_name]
    with col2:
        wr = st.slider("Win Rate (%)", 20, 80, 45)
        rr = st.slider("Ratio R:R", 1.0, 4.0, 2.0)
        risk = st.slider("Riesgo %", 0.25, 2.0, 1.0)

    # --- SIMULACIÓN ---
    if st.button("🔄 Simular Escenario"):
        prob = run_simulation(firm['size'], risk, wr, rr, firm['profit'], firm['total_dd'])
        attempts = 100/prob if prob > 0 else 100
        inv = attempts * firm['cost']
        
        st.metric("Probabilidad de Pasar", f"{prob:.1f}%")
        st.metric("Inversión Estimada (Costo Real)", f"${inv:,.0f}")
        
        # GUARDAR RESULTADO
        save_plan_db(st.session_state['username'], firm_name, wr, rr, prob, inv)
        st.toast("Escenario guardado en tu historial")

    # --- HISTORIAL ---
    st.divider()
    st.subheader("📜 Tus Planes Guardados")
    planes = get_user_plans(st.session_state['username'])
    if planes:
        df = pd.DataFrame(planes, columns=["Empresa", "Probabilidad", "Inversión Est.", "Fecha"])
        st.dataframe(df)
    else:
        st.info("Aún no tienes planes guardados.")