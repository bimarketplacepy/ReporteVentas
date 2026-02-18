import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px

# 1. Configuración de página
st.set_page_config(page_title="Reporte Diario Marketplace", layout="wide", page_icon="📊")

# 2. Función de Seguridad (Password)
def check_password():
    """Retorna True si el usuario ingresa la contraseña correcta."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Borrar pass por seguridad
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 Contraseña de acceso", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 Contraseña de acceso", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta")
        return False
    else:
        return True

# 3. Cargar Datos desde Google Sheets
@st.cache_data(ttl=600) # Guardar en memoria 10 mins para no gastar cuota de Google
def load_data():
    # Conexión usando Secretos de Streamlit (Nube)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) # Lee los secretos ocultos
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Abrir hoja maestra
    sh = client.open("DB_VENTAS_MASTER")
    
    # Leer datos históricos
    ws = sh.worksheet("TD_Anual_Data")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    # Limpieza de datos (Convertir texto a números)
    cols_numericas = ['TOTAL_VENTA_DIARIA_GS', 'UTILIDAD_BRUTA_DIARIA_GS', 
                      'CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS', 
                      'TICKET_PROMEDIO_MENSUAL_DATO']
    
    for col in cols_numericas:
        if col in df.columns:
            # Eliminar puntos, comas y convertir a float
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
    # Convertir fecha
    df['fecha'] = pd.to_datetime(df['fecha'])
    return df

# --- INICIO DE LA APP ---
if check_password():
    try:
        with st.spinner('⏳ Conectando con Google Sheets...'):
            df = load_data()
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    # Barra lateral (Sidebar)
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.sidebar.title("Filtros")
    
    # Selector de Fecha (Por defecto: La última fecha disponible en los datos)
    fecha_max = df['fecha'].max()
    fecha_selec = st.sidebar.date_input("Seleccionar Fecha", fecha_max)
    fecha_selec = pd.to_datetime(fecha_selec)

    # Filtrar datos
    df_dia = df[df['fecha'] == fecha_selec]
    
    # Título Principal
    st.title(f"📊 Reporte Diario: {fecha_selec.strftime('%d/%m/%Y')}")
    st.markdown("---")

    if not df_dia.empty:
        # --- KPI CARDS (Tarjetas Grandes) ---
        col1, col2, col3, col4 = st.columns(4)
        
        venta = df_dia['TOTAL_VENTA_DIARIA_GS'].sum()
        utilidad = df_dia['UTILIDAD_BRUTA_DIARIA_GS'].sum()
        tickets = df_dia['CANT_TICKETS_DIARIOS'].sum()
        visitas = df_dia['NRO_VISITAS_DIARIAS'].sum()
        
        # Cálculos extra
        ticket_prom = venta / tickets if tickets > 0 else 0
        conversion = (tickets / visitas * 100) if visitas > 0 else 0
        mdr = (utilidad / venta * 100) if venta > 0 else 0

        col1.metric("💰 Venta Total", f"₲ {venta:,.0f}")
        col2.metric("📈 Utilidad", f"₲ {utilidad:,.0f}", f"{mdr:.1f}% Mrg")
        col3.metric("🧾 Tickets", f"{tickets:,.0f}", f"Prom: ₲ {ticket_prom:,.0f}")
        col4.metric("👥 Visitas", f"{visitas:,.0f}", f"Conv: {conversion:.1f}%")

        # --- GRÁFICOS INTERACTIVOS ---
        st.markdown("### 📅 Tendencia últimos 30 días")
        
        # Datos para gráfico (últimos 30 días desde la fecha seleccionada)
        fecha_inicio_30 = fecha_selec - pd.Timedelta(days=30)
        df_30 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > fecha_inicio_30)].sort_values('fecha')

        tab1, tab2 = st.tabs(["Ventas Diarias", "Ticket vs Visitas"])
        
        with tab1:
            fig_v = px.bar(df_30, x='fecha', y='TOTAL_VENTA_DIARIA_GS', 
                           title="Evolución de Venta Diaria", text_auto='.2s')
            fig_v.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
            st.plotly_chart(fig_v, use_container_width=True)
            
        with tab2:
            fig_mix = px.line(df_30, x='fecha', y=['CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS'], 
                              title="Comparativo Tráfico vs Compra", markers=True)
            st.plotly_chart(fig_mix, use_container_width=True)

        # --- TABLA DE DATOS ---
        with st.expander("📂 Ver Tabla de Datos Completa"):
            st.dataframe(df_30.sort_values('fecha', ascending=False).style.format({
                'TOTAL_VENTA_DIARIA_GS': '₲ {:,.0f}',
                'UTILIDAD_BRUTA_DIARIA_GS': '₲ {:,.0f}',
            }))

    else:
        st.warning(f"⚠️ No se encontraron datos cargados para la fecha: {fecha_selec.strftime('%d/%m/%Y')}")
        st.info("Intenta seleccionar una fecha anterior en el menú de la izquierda.")
