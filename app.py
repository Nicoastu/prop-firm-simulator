import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Simulador de Negocio de Fondeo", layout="wide")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .big-font { font-size:24px !important; font-weight: bold; }
    .metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; margin-bottom: 10px; }
    .stSuccess { color: #00C853 !important; }
    .stDanger { color: #FF5252 !important; }
    </style>
""", unsafe_allow_html=True)

# --- TÍTULO Y ENFOQUE ---
st.title("💼 Planificador de Negocio de Fondeo")
st.markdown("""
Esta herramienta no es solo para ver si tu estrategia gana. Es para calcular **cuánto dinero y tiempo** te costará realmente obtener tu primer retiro. Trata el trading como un negocio de probabilidades.
""")

# --- SIDEBAR: DATOS DEL NEGOCIO ---
with st.sidebar:
    st.header("1. Datos de la Cuenta (Costos)")
    account_size = st.number_input("Tamaño de Cuenta ($)", value=100000, step=10000)
    account_price = st.number_input("Costo de la Prueba ($)", value=500, step=50)
    
    st.header("2. Reglas de la Empresa")
    phase1_target = st.number_input("Objetivo Fase 1 (%)", value=8.0, step=0.5) / 100
    phase2_target = st.number_input("Objetivo Fase 2 (%)", value=5.0, step=0.5) / 100
    max_drawdown = st.number_input("Drawdown Máximo (%)", value=10.0, step=0.5) / 100
    
    st.header("3. Tu Estrategia Operativa")
    winrate = st.slider("Winrate (%)", 30, 80, 45) / 100
    risk_reward = st.number_input("Ratio Riesgo:Beneficio (1:X)", value=2.0, step=0.1)
    risk_per_trade = st.slider("Riesgo por Trade (%)", 0.25, 3.0, 1.0, step=0.25) / 100
    
    # --- NUEVA VARIABLE CLAVE: TIEMPO ---
    st.header("4. Ritmo de Trabajo")
    trades_per_day = st.slider("Promedio Trades al Día", 1, 10, 2, help="¿Cuántas operaciones tomas en un día promedio?")

# --- LÓGICA DE SIMULACIÓN (MONTE CARLO) ---
def run_simulation(n_simulations=1000):
    results = []
    
    # Ajustes matemáticos de la estrategia
    win_size = risk_per_trade * risk_reward
    loss_size = risk_per_trade
    
    for _ in range(n_simulations):
        equity = 1.0 # 100%
        days_passed = 0
        phase = 1
        is_blown = False
        is_funded = False
        
        # Simulamos hasta 300 trades (suficiente para evaluar viabilidad)
        # Optimizamos usando numpy para velocidad en bloques
        trades = np.random.choice([win_size, -loss_size], size=500, p=[winrate, 1-winrate])
        
        current_equity = 1.0
        trades_count = 0
        
        for r in trades:
            trades_count += 1
            current_equity += r
            
            # Chequeo de Drawdown (Pérdida de cuenta)
            # Simplificación: Asumimos DD estático respecto al balance inicial para velocidad
            if current_equity <= (1.0 - max_drawdown):
                is_blown = True
                break
                
            # Lógica Fase 1
            if phase == 1:
                if current_equity >= (1.0 + phase1_target):
                    phase = 2
                    current_equity = 1.0 # Reset balance para Fase 2 (común en prop firms)
            
            # Lógica Fase 2
            elif phase == 2:
                if current_equity >= (1.0 + phase2_target):
                    is_funded = True
                    break
        
        # Calcular días basados en los trades tomados
        days_passed = trades_count / trades_per_day
        
        results.append({
            "funded": is_funded,
            "blown": is_blown,
            "trades": trades_count,
            "days": days_passed
        })
        
    return pd.DataFrame(results)

# Botón para ejecutar
if st.button("🔄 Simular Escenario de Negocio"):
    with st.spinner('Procesando 1,000 escenarios posibles...'):
        df = run_simulation()
        
        # --- CÁLCULOS DE NEGOCIO ---
        pass_rate = df['funded'].mean()
        prob_ruin = df['blown'].mean()
        
        # Evitar división por cero
        if pass_rate > 0:
            accounts_needed = 1 / pass_rate
            avg_days = df[df['funded']]['days'].mean()
            # Asumimos 22 días de trading al mes
            avg_months = avg_days / 22 
        else:
            accounts_needed = float('inf')
            avg_days = 0
            avg_months = 0

        capital_required = accounts_needed * account_price
        
        # --- DASHBOARD DE RESULTADOS ---
        
        st.markdown("---")
        
        # BLOQUE 1: REALIDAD MATEMÁTICA
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 🎯 Probabilidad")
            st.metric(label="Tasa de Éxito (Funded)", value=f"{pass_rate*100:.1f}%")
            if pass_rate < 0.10:
                st.error("Probabilidad baja. Requiere mucho capital.")
            else:
                st.success("Probabilidad saludable.")

        with col2:
            st.markdown("### 💰 Costo Real")
            st.metric(label="Cuentas a Comprar (Estadístico)", value=f"{accounts_needed:.1f}")
            st.caption(f"Para asegurar 1 cuenta fondeada, deberías presupuestar comprar aprox {accounts_needed:.1f} pruebas.")

        with col3:
            st.markdown("### 💸 Inversión Total")
            st.metric(label="Capital Estimado", value=f"${capital_required:,.0f}")
            st.caption(f"Costo unitario (${account_price}) x Cuentas necesarias.")

        st.markdown("---")

        # BLOQUE 2: TIEMPO (LA NUEVA VARIABLE)
        st.subheader("⏳ Análisis de Tiempo (Time to Payout)")
        
        c_time1, c_time2 = st.columns(2)
        
        with c_time1:
            st.markdown(f"""
            <div class="metric-card">
                <h3 style="color:#4FC3F7">Tiempo Promedio para Fondearse</h3>
                <p class="big-font">{avg_days:.1f} Días Operativos</p>
                <p>Aprox. <b>{avg_months:.1f} Meses</b> de calendario.</p>
                <p style="font-size:14px; color:#999">Operando {trades_per_day} veces al día.</p>
            </div>
            """, unsafe_allow_html=True)
            
        with c_time2:
             # Un pequeño consejo basado en datos
            recommendation = ""
            if avg_months > 3:
                recommendation = "⚠️ **Alerta:** Tu operativa es muy lenta. Tardarás más de un trimestre solo en pasar. Considera aumentar ligeramente el riesgo o la frecuencia de trades si la psicología lo permite."
            elif pass_rate < 0.15:
                recommendation = "⚠️ **Alerta:** Tienes un riesgo de ruina alto. Aunque seas rápido, es probable que pierdas la cuenta. Reduce el riesgo por trade."
            else:
                recommendation = "✅ **Excelente:** Tienes un equilibrio sólido entre velocidad y seguridad."
            
            st.info(f"**Diagnóstico de Estrategia:**\n\n{recommendation}")

        # BLOQUE 3: GRÁFICO DE DISTRIBUCIÓN DE TIEMPO
        if pass_rate > 0:
            fig = go.Figure()
            funded_runs = df[df['funded']]
            fig.add_trace(go.Histogram(
                x=funded_runs['days'],
                name='Días para Fondearse',
                marker_color='#00C853',
                opacity=0.75
            ))
            fig.update_layout(
                title='Distribución: ¿Cuántos días tardan los traders exitosos con tu estrategia?',
                xaxis_title='Días Operativos',
                yaxis_title='Frecuencia',
                template='plotly_dark'
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("Con esta configuración, ninguna simulación logró pasar las pruebas. Ajusta el riesgo o el winrate.")

else:
    st.info("👈 Ajusta los parámetros en la barra lateral y presiona 'Simular' para ver tu plan de negocio.")