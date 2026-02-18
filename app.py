import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Reporte Diario Marketplace", layout="wide", page_icon="📊")

# Estilos CSS para que se parezca a tu Excel (Encabezados azules)
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-left: 5px solid #1F497D;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .stMetric {
        background-color: white !important;
        padding: 10px !important;
        border-radius: 5px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
    }
    /* Títulos de sección estilo Excel */
    .section-header {
        background-color: #1F497D;
        color: white;
        padding: 8px 15px;
        border-radius: 5px;
        font-weight: bold;
        margin-top: 20px;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- SEGURIDAD ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 Contraseña:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 Contraseña:", type="password", on_change=password_entered, key="password")
        st.error("❌ Contraseña incorrecta")
        return False
    else:
        return True

# --- CARGA DE DATOS ---
@st.cache_data(ttl=600)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sh = client.open("DB_VENTAS_MASTER")

    # 1. Cargar Histórico (Para gráficos)
    try:
        ws_anual = sh.worksheet("TD_Anual_Data")
        df_anual = pd.DataFrame(ws_anual.get_all_records())
        # Limpieza
        cols_num = ['TOTAL_VENTA_DIARIA_GS', 'CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS']
        for col in cols_num:
            if col in df_anual.columns:
                df_anual[col] = pd.to_numeric(df_anual[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_anual['fecha'] = pd.to_datetime(df_anual['fecha'])
    except:
        df_anual = pd.DataFrame()

    # 2. Cargar KPIs Complejos (Los cuadros azules)
    try:
        ws_kpis = sh.worksheet("KPIs_Complejos")
        df_kpis = pd.DataFrame(ws_kpis.get_all_records())
        # Limpiar números que vienen como texto
        cols_kpi = ['Anio_Actual', 'Anio_Anterior', 'Variacion_Pct', 'Diferencia_Val']
        for col in cols_kpi:
            if col in df_kpis.columns:
                df_kpis[col] = pd.to_numeric(df_kpis[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    except:
        df_kpis = pd.DataFrame()

    return df_anual, df_kpis

# --- RENDERIZADO DE LA WEB ---
if check_password():
    try:
        with st.spinner('⏳ Actualizando Tablero...'):
            df_anual, df_kpis = load_data()
    except Exception as e:
        st.error(f"Error conectando: {e}")
        st.stop()

    # Título
    st.title("📊 Tablero de Control - Marketplace S.A.")
    
    if not df_kpis.empty:
        # Aquí reconstruimos tu Excel usando los datos de la hoja KPIs_Complejos
        # Filtramos por nombre de KPI para ponerlos en orden
        
        # --- FILA 1: VENTAS Y UTILIDAD ---
        st.markdown('<div class="section-header">💵 VENTAS Y RENTABILIDAD</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)

        def mostrar_metrica(columna, nombre_kpi, etiqueta, formato="Gs"):
            """Busca el KPI en el dataframe y lo dibuja"""
            dato = df_kpis[df_kpis['KPI'] == nombre_kpi]
            if not dato.empty:
                val_actual = dato.iloc[0]['Anio_Actual']
                delta_val = dato.iloc[0]['Variacion_Pct']
                
                if formato == "Gs":
                    columna.metric(etiqueta, f"₲ {val_actual:,.0f}", f"{delta_val:.2%}")
                elif formato == "Pct":
                    columna.metric(etiqueta, f"{val_actual:.2f}%", f"{delta_val:.2%}")
                else:
                    columna.metric(etiqueta, f"{val_actual:,.0f}", f"{delta_val:.2%}")

        mostrar_metrica(c1, "Ventas Anuales", "Ventas Anuales (Acum)")
        mostrar_metrica(c2, "Ventas Mensual", "Ventas Mes Actual")
        mostrar_metrica(c3, "Utilidad Bruta Anual", "Utilidad Bruta (Acum)")
        mostrar_metrica(c4, "MDR (Margen)", "Margen Promedio", formato="Pct")

        # --- FILA 2: MEDIAS MÓVILES (14 Días) ---
        st.markdown('<div class="section-header">📅 TENDENCIA 14 DÍAS (Media Móvil)</div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        
        mostrar_metrica(m1, "Media Movil 14 Dias (Ventas)", "Media Ventas (14d)")
        mostrar_metrica(m2, "Media Movil 14 Dias (Utilidad)", "Media Utilidad (14d)")
        # Si agregaste Tickets/MDR en media móvil, agrégalos aquí. Si no, usa placeholders.
        
        # --- FILA 3: OPERATIVOS (Tickets, Visitas, Stock) ---
        st.markdown('<div class="section-header">📦 OPERACIONES Y STOCK</div>', unsafe_allow_html=True)
        o1, o2, o3, o4 = st.columns(4)
        
        mostrar_metrica(o1, "Visitas", "Visitas Acumuladas", formato="Num")
        mostrar_metrica(o2, "Tickets Acumulados", "Tickets Acumulados", formato="Num")
        mostrar_metrica(o3, "Conversion Diaria", "Conversión Diaria", formato="Pct")
        mostrar_metrica(o4, "Stock Valorizado", "Stock Valorizado")

        st.divider()

    # --- GRÁFICOS (Usando df_anual) ---
    if not df_anual.empty:
        st.subheader("📈 Evolución Diaria (Últimos 30 días)")
        fecha_max = df_anual['fecha'].max()
        df_30 = df_anual[df_anual['fecha'] > (fecha_max - pd.Timedelta(days=30))]
        
        g1, g2 = st.columns(2)
        with g1:
            fig = px.bar(df_30, x='fecha', y='TOTAL_VENTA_DIARIA_GS', title="Venta Diaria")
            st.plotly_chart(fig, use_container_width=True)
        with g2:
            fig2 = px.line(df_30, x='fecha', y=['CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS'], title="Tráfico vs Tickets")
            st.plotly_chart(fig2, use_container_width=True)
    
    # Botón de recarga manual
    if st.button("🔄 Recargar Datos"):
        st.cache_data.clear()
        st.experimental_rerun()
