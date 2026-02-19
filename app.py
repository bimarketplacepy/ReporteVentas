import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
import plotly.graph_objects as go

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
@st.cache_data(ttl=600) 
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) 
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sh = client.open("DB_VENTAS_MASTER")
    
    # 3.1 Leer datos históricos (TD_Anual_Data)
    ws_anual = sh.worksheet("TD_Anual_Data")
    df = pd.DataFrame(ws_anual.get_all_records())
    cols_numericas = ['TOTAL_VENTA_DIARIA_GS', 'UTILIDAD_BRUTA_DIARIA_GS', 
                      'CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS', 
                      'TICKET_PROMEDIO_MENSUAL_DATO']
    for col in cols_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
    # Convertir fecha y SOLUCIÓN AL ERROR: Recrear las columnas 'anio' y 'mes'
    df['fecha'] = pd.to_datetime(df['fecha'])
    df['anio'] = df['fecha'].dt.year
    df['mes'] = df['fecha'].dt.month

    # 3.2 Leer KPIs Complejos (Para las nuevas pestañas)
    try:
        ws_kpis = sh.worksheet("KPIs_Complejos")
        df_kpis = pd.DataFrame(ws_kpis.get_all_records())
        cols_kpi = ['Anio_Actual', 'Anio_Anterior', 'Variacion_Pct', 'Diferencia_Val']
        for col in cols_kpi:
            if col in df_kpis.columns:
                df_kpis[col] = pd.to_numeric(df_kpis[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    except Exception:
        df_kpis = pd.DataFrame()

    return df, df_kpis

# --- INICIO DE LA APP ---
if check_password():
    
    # --- BARRA LATERAL ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.sidebar.title("Filtros")
    
    if st.sidebar.button("🔄 Actualizar Datos Ahora"):
        st.cache_data.clear() 
        st.rerun() 
    
    st.sidebar.divider()

    try:
        with st.spinner('⏳ Conectando con Google Sheets...'):
            df, df_kpis = load_data()
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    fecha_max = df['fecha'].max()
    fecha_selec = st.sidebar.date_input("Seleccionar Fecha", fecha_max)
    fecha_selec = pd.to_datetime(fecha_selec)

    df_dia = df[df['fecha'] == fecha_selec]
    
    st.title(f"📊 Reporte Diario Marketplace S.A.: {fecha_selec.strftime('%d/%m/%Y')}")
    st.markdown("---")

    if not df_dia.empty:
        # =====================================================================
        # 1. LA VISTA BASE ORIGINAL (TARJETAS GRANDES)
        # =====================================================================
        col1, col2, col3, col4 = st.columns(4)
        
        venta = df_dia['TOTAL_VENTA_DIARIA_GS'].sum()
        utilidad = df_dia['UTILIDAD_BRUTA_DIARIA_GS'].sum()
        tickets = df_dia['CANT_TICKETS_DIARIOS'].sum()
        visitas = df_dia['NRO_VISITAS_DIARIAS'].sum()
        
        ticket_prom = venta / tickets if tickets > 0 else 0
        conversion = (tickets / visitas * 100) if visitas > 0 else 0
        mdr_dia = (utilidad / venta * 100) if venta > 0 else 0

        col1.metric("💰 Venta Total", f"₲ {venta:,.0f}")
        col2.metric("📈 Utilidad", f"₲ {utilidad:,.0f}", f"{mdr_dia:.1f}% Mrg")
        col3.metric("🧾 Tickets", f"{tickets:,.0f}", f"Prom: ₲ {ticket_prom:,.0f}")
        col4.metric("👥 Visitas", f"{visitas:,.0f}", f"Conv: {conversion:.1f}%")

        st.markdown("### 📅 Análisis de Datos")
        
        # Datos para gráficos de 30 días
        fecha_inicio_30 = fecha_selec - pd.Timedelta(days=30)
        df_30 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > fecha_inicio_30)].sort_values('fecha')

        # =====================================================================
        # 2. SISTEMA DE PESTAÑAS (TUS 2 ORIGINALES + LAS 5 NUEVAS)
        # =====================================================================
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📈 Ventas Diarias",           # Tuya original 1
            "👥 Ticket vs Visitas",        # Tuya original 2
            "1️⃣ Resumen (KPIs)",           # Nueva 1
            "2️⃣ Ventas y Rentabilidad",    # Nueva 2
            "3️⃣ Operaciones y Clientes",   # Nueva 3
            "4️⃣ Inventario",               # Nueva 4
            "5️⃣ Medias (14 Días)"          # Nueva 5
        ])

        # --- PESTAÑAS ORIGINALES ---
        with tab1:
            fig_v = px.bar(df_30, x='fecha', y='TOTAL_VENTA_DIARIA_GS', 
                           title="Evolución de Venta Diaria (Últimos 30 días)", text_auto='.2s')
            fig_v.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False, marker_color='#1F497D')
            st.plotly_chart(fig_v, use_container_width=True)
            
        with tab2:
            fig_mix = px.line(df_30, x='fecha', y=['CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS'], 
                              title="Comparativo Tráfico vs Compra (Últimos 30 días)", markers=True)
            st.plotly_chart(fig_mix, use_container_width=True)

        # Función auxiliar para extraer datos de la tabla de KPIs
        def get_kpi(nombre):
            if not df_kpis.empty:
                fila = df_kpis[df_kpis['KPI'] == nombre]
                if not fila.empty:
                    return fila.iloc[0]
            return None

        # --- NUEVA PESTAÑA 1: RESUMEN EJECUTIVO ---
        with tab3:
            st.subheader("Indicadores Acumulados del Año")
            c1, c2, c3, c4 = st.columns(4)
            k_venta = get_kpi("Ventas Anuales")
            k_util  = get_kpi("Utilidad Bruta Anual")
            k_vis   = get_kpi("Visitas")
            k_mdr   = get_kpi("MDR (Margen)")

            if k_venta is not None:
                c1.metric("Ventas Anuales", f"₲ {k_venta['Anio_Actual']:,.0f}", f"{k_venta['Variacion_Pct']:.2%} vs Ant.")
            if k_util is not None:
                c2.metric("Utilidad Bruta", f"₲ {k_util['Anio_Actual']:,.0f}", f"{k_util['Variacion_Pct']:.2%} vs Ant.")
            if k_vis is not None:
                c3.metric("Visitas Acumuladas", f"{k_vis['Anio_Actual']:,.0f}", f"{k_vis['Variacion_Pct']:.2%} vs Ant.")

            if k_mdr is not None:
                mdr_actual = k_mdr['Anio_Actual'] * 100
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=mdr_actual,
                    title={'text': "Margen de Rentabilidad (MDR)"},
                    delta={'reference': k_mdr['Anio_Anterior'] * 100, 'position': "top"},
                    gauge={
                        'axis': {'range': [None, 50]},
                        'bar': {'color': "#1F497D"},
                        'steps': [{'range': [0, 25], 'color': "lightgray"}, {'range': [25, 35], 'color': "gray"}],
                        'threshold': {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': 36}
                    }
                ))
                fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
                c4.plotly_chart(fig_gauge, use_container_width=True)

        # --- NUEVA PESTAÑA 2: VENTAS Y RENTABILIDAD ---
        with tab4:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.subheader("Comparativo Multianual (2022-2026)")
                df_historico_anual = df.groupby('anio').agg({'TOTAL_VENTA_DIARIA_GS':'sum', 'UTILIDAD_BRUTA_DIARIA_GS':'sum'}).reset_index()
                fig_multi = px.bar(df_historico_anual, x='anio', y=['TOTAL_VENTA_DIARIA_GS', 'UTILIDAD_BRUTA_DIARIA_GS'], 
                                   barmode='group', labels={'value': 'Guaraníes', 'variable': 'Métrica'},
                                   color_discrete_sequence=['#1F497D', '#2ca02c'])
                st.plotly_chart(fig_multi, use_container_width=True)

            with col_v2:
                st.subheader("Relación Mensual (Año Actual)")
                df_meses = df[df['anio'] == df['anio'].max()].groupby('mes').agg({'TOTAL_VENTA_DIARIA_GS':'sum', 'UTILIDAD_BRUTA_DIARIA_GS':'sum'}).reset_index()
                fig_combo = go.Figure()
                fig_combo.add_trace(go.Bar(x=df_meses['mes'], y=df_meses['TOTAL_VENTA_DIARIA_GS'], name='Ventas', marker_color='#1F497D'))
                fig_combo.add_trace(go.Scatter(x=df_meses['mes'], y=df_meses['UTILIDAD_BRUTA_DIARIA_GS'], name='Utilidad', mode='lines+markers', line=dict(color='red', width=3)))
                fig_combo.update_layout(xaxis_title="Mes", yaxis_title="Guaraníes")
                st.plotly_chart(fig_combo, use_container_width=True)

        # --- NUEVA PESTAÑA 3: OPERACIONES Y CLIENTES ---
        with tab5:
            df_90 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > (fecha_selec - pd.Timedelta(days=90)))].sort_values('fecha')
            c_op1, c_op2 = st.columns(2)
            
            with c_op1:
                st.subheader("Tendencia de Visitas (90 días)")
                fig_visitas = px.area(df_90, x='fecha', y='NRO_VISITAS_DIARIAS', color_discrete_sequence=['#ff7f0e'])
                st.plotly_chart(fig_visitas, use_container_width=True)
                
            with c_op2:
                st.subheader("Tickets vs Monto Promedio")
                fig_tck = go.Figure()
                fig_tck.add_trace(go.Bar(x=df_90['fecha'], y=df_90['CANT_TICKETS_DIARIOS'], name='Cant. Tickets', yaxis='y1'))
                fig_tck.add_trace(go.Scatter(x=df_90['fecha'], y=df_90['TICKET_PROMEDIO_MENSUAL_DATO'], name='Monto Ticket', yaxis='y2', line=dict(color='red')))
                fig_tck.update_layout(yaxis=dict(title='Cantidad', side='left'), yaxis2=dict(title='Monto (Gs)', side='right', overlaying='y', showgrid=False))
                st.plotly_chart(fig_tck, use_container_width=True)
                
            st.subheader("Embudo de Conversión (Día Seleccionado)")
            fig_funnel = go.Figure(go.Funnel(
                y=["Total Visitas", "Tickets Emitidos"], x=[visitas, tickets],
                textinfo="value+percent initial", marker={"color": ["#1F497D", "#2ca02c"]}
            ))
            fig_funnel.update_layout(height=250)
            st.plotly_chart(fig_funnel, use_container_width=True)

        # --- NUEVA PESTAÑA 4: INVENTARIO ---
        with tab6:
            st.subheader("Fotografía del Stock Actual")
            k_val = get_kpi("Stock Valorizado")
            k_qty = get_kpi("Cant. Items Stock")
            
            i1, i2, i3 = st.columns(3)
            if k_val is not None:
                i1.metric("Valorizado de Salón", f"₲ {k_val['Anio_Actual']:,.0f}", f"{k_val['Variacion_Pct']:.2%} vs Año Ant.")
            if k_qty is not None:
                i2.metric("Unidades Físicas", f"{k_qty['Anio_Actual']:,.0f}", f"{k_qty['Variacion_Pct']:.2%} vs Año Ant.")
            
            # Puedes reemplazar este placeholder cuando calcules los SKUs reales en Python
            i3.metric("SKUs Activos", "N/D", "Sin datos en el modelo actual")

        # --- NUEVA PESTAÑA 5: MEDIAS (14 DÍAS) Y ALERTAS ---
        with tab7:
            st.subheader("Desviación contra Media Móvil (14 días)")
            st.info("💡 Este panel alerta sobre caídas abruptas en la operativa diaria comparada con el ritmo de las últimas dos semanas.")
            
            def renderizar_alerta_delta(kpi_data, titulo):
                if kpi_data is None: return
                var = kpi_data['Variacion_Pct']
                val = kpi_data['Anio_Actual']
                media = kpi_data['Anio_Anterior']
                
                # Manejo de alertas según el requerimiento (-100% o anómalo)
                if var <= -0.99:
                    st.error(f"🚨 **ALERTA CRÍTICA - {titulo}:** Caída del {var:.2%}. Valor actual ₲ {val:,.0f} vs Media ₲ {media:,.0f}. Revisar carga de datos.")
                else:
                    color = "normal" if var > 0 else "inverse"
                    st.metric(f"{titulo} (Actual vs Media)", f"₲ {val:,.0f}", f"{var:.2%}", delta_color=color)
            
            col_m1, col_m2 = st.columns(2)
            with col_m1: renderizar_alerta_delta(get_kpi("Media Movil 14 Dias (Ventas)"), "Ventas Diarias")
            with col_m2: renderizar_alerta_delta(get_kpi("Media Movil 14 Dias (Utilidad)"), "Utilidad Diaria")

        # =====================================================================
        # 3. TABLA DE DATOS ORIGINAL AL FINAL
        # =====================================================================
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📂 Ver Tabla de Datos Completa (30 Días)"):
            st.dataframe(df_30.sort_values('fecha', ascending=False).style.format({
                'TOTAL_VENTA_DIARIA_GS': '₲ {:,.0f}',
                'UTILIDAD_BRUTA_DIARIA_GS': '₲ {:,.0f}',
            }))

    else:
        st.warning(f"⚠️ No se encontraron datos cargados para la fecha: {fecha_selec.strftime('%d/%m/%Y')}")
        st.info("Intenta seleccionar una fecha anterior en el menú de la izquierda.")
