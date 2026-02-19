import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px
import plotly.graph_objects as go

# 1. Configuración de página
st.set_page_config(page_title="Reporte Diario Marketplace", layout="wide", page_icon="📊")

# --- ESTILOS ADICIONALES ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 5px;
        padding: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

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
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"]) 
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sh = client.open("DB_VENTAS_MASTER")
    
    # 3.1 Leer datos históricos (TD_Anual_Data)
    ws_anual = sh.worksheet("TD_Anual_Data")
    df_anual = pd.DataFrame(ws_anual.get_all_records())
    cols_numericas = ['TOTAL_VENTA_DIARIA_GS', 'UTILIDAD_BRUTA_DIARIA_GS', 
                      'CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS', 
                      'TICKET_PROMEDIO_MENSUAL_DATO']
    for col in cols_numericas:
        if col in df_anual.columns:
            df_anual[col] = pd.to_numeric(df_anual[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    df_anual['fecha'] = pd.to_datetime(df_anual['fecha'])

    # 3.2 Leer KPIs Complejos (Para los comparativos y stock)
    try:
        ws_kpis = sh.worksheet("KPIs_Complejos")
        df_kpis = pd.DataFrame(ws_kpis.get_all_records())
        cols_kpi = ['Anio_Actual', 'Anio_Anterior', 'Variacion_Pct', 'Diferencia_Val']
        for col in cols_kpi:
            if col in df_kpis.columns:
                df_kpis[col] = pd.to_numeric(df_kpis[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    except Exception as e:
        print(f"Error cargando KPIs: {e}")
        df_kpis = pd.DataFrame()

    return df_anual, df_kpis

# --- INICIO DE LA APP ---
if check_password():
    
    # --- BARRA LATERAL (Filtros y Recarga) ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.sidebar.title("Menú")
    
    if st.sidebar.button("🔄 Actualizar Datos Ahora"):
        st.cache_data.clear() 
        st.rerun() 
    
    st.sidebar.divider()
    st.sidebar.header("Filtros")

    try:
        with st.spinner('⏳ Conectando con Google Sheets...'):
            df, df_kpis = load_data()
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

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
        # =====================================================================
        # VISTA BASE (Lo que ya tenías y te gustaba)
        # =====================================================================
        st.markdown("### Vista Diaria Rápida")
        col1, col2, col3, col4 = st.columns(4)
        
        venta = df_dia['TOTAL_VENTA_DIARIA_GS'].sum()
        utilidad = df_dia['UTILIDAD_BRUTA_DIARIA_GS'].sum()
        tickets = df_dia['CANT_TICKETS_DIARIOS'].sum()
        visitas = df_dia['NRO_VISITAS_DIARIAS'].sum()
        
        ticket_prom = venta / tickets if tickets > 0 else 0
        conversion = (tickets / visitas * 100) if visitas > 0 else 0
        mdr_dia = (utilidad / venta * 100) if venta > 0 else 0

        col1.metric("💰 Venta Total Día", f"₲ {venta:,.0f}")
        col2.metric("📈 Utilidad Día", f"₲ {utilidad:,.0f}", f"{mdr_dia:.1f}% Mrg")
        col3.metric("🧾 Tickets Día", f"{tickets:,.0f}", f"Prom: ₲ {ticket_prom:,.0f}")
        col4.metric("👥 Visitas Día", f"{visitas:,.0f}", f"Conv: {conversion:.1f}%")
        st.divider()

        # =====================================================================
        # NUEVAS PESTAÑAS (Según tu Prompt)
        # =====================================================================
        # Usamos st.tabs para organizar el contenido nuevo y el viejo
        tabs = st.tabs([
            "1. Resumen Ejecutivo (KPIs)", 
            "2. Ventas y Rentabilidad", 
            "3. Operaciones y Clientes", 
            "4. Gestión de Inventario", 
            "5. Análisis de Medias (14d)",
            "6. Gráficos 30 Días (Original)" # Tu vista de barras original
        ])

        # Función auxiliar para buscar KPIs
        def get_kpi_data(kpi_name):
            if not df_kpis.empty:
                filtro = df_kpis[df_kpis['KPI'] == kpi_name]
                if not filtro.empty:
                    return filtro.iloc[0]
            return None

        # --- PESTAÑA 1: RESUMEN EJECUTIVO (KPIs) ---
        with tabs[0]:
            st.header("Resumen Ejecutivo (Acumulado Anual)")
            
            # Buscar datos
            kpi_ventas = get_kpi_data("Ventas Anuales")
            kpi_utilidad = get_kpi_data("Utilidad Bruta Anual")
            kpi_visitas = get_kpi_data("Visitas")
            kpi_mdr = get_kpi_data("MDR (Margen)")

            c1, c2, c3, c4 = st.columns(4)
            
            if kpi_ventas is not None:
                c1.metric("Ventas Anuales 2026", f"₲ {kpi_ventas['Anio_Actual']:,.0f}", f"{kpi_ventas['Variacion_Pct']:.2%} (₲ {kpi_ventas['Diferencia_Val']:,.0f})")
            if kpi_utilidad is not None:
                c2.metric("Utilidad Bruta 2026", f"₲ {kpi_utilidad['Anio_Actual']:,.0f}", f"{kpi_utilidad['Variacion_Pct']:.2%} (₲ {kpi_utilidad['Diferencia_Val']:,.0f})")
            if kpi_visitas is not None:
                c3.metric("Visitas Acumuladas 2026", f"{kpi_visitas['Anio_Actual']:,.0f}", f"{kpi_visitas['Variacion_Pct']:.2%} ({kpi_visitas['Diferencia_Val']:,.0f} personas)")
            
            # Gráfico Gauge para MDR
            if kpi_mdr is not None:
                mdr_actual = kpi_mdr['Anio_Actual'] * 100 # Asumiendo que viene como decimal (ej. 0.3647)
                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number+delta",
                    value = mdr_actual,
                    title = {'text': "MDR (Margen de Rentabilidad)"},
                    delta = {'reference': kpi_mdr['Anio_Anterior'] * 100, 'position': "top"},
                    gauge = {
                        'axis': {'range': [None, 50]},
                        'bar': {'color': "#1F497D"},
                        'steps': [
                            {'range': [0, 20], 'color': "lightgray"},
                            {'range': [20, 30], 'color': "gray"}],
                        'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 40}
                    }
                ))
                fig_gauge.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
                c4.plotly_chart(fig_gauge, use_container_width=True)

        # --- PESTAÑA 2: VENTAS Y RENTABILIDAD ---
        with tabs[1]:
            st.header("Análisis de Ventas y Rentabilidad")
            
            # Simular datos multianuales para el gráfico (requiere que df_anual tenga data de años anteriores)
            # Como tu df_anual tiene la columna 'anio', agrupamos:
            df_historico_anual = df.groupby('anio').agg({'TOTAL_VENTA_DIARIA_GS':'sum', 'UTILIDAD_BRUTA_DIARIA_GS':'sum'}).reset_index()
            
            col_v1, col_v2 = st.columns(2)
            
            with col_v1:
                st.subheader("Comparativo Multianual")
                fig_multi = px.bar(df_historico_anual, x='anio', y=['TOTAL_VENTA_DIARIA_GS', 'UTILIDAD_BRUTA_DIARIA_GS'], 
                                   barmode='group', title="Ventas vs Utilidad (2022-2026)",
                                   labels={'value': 'Guaraníes', 'variable': 'Métrica'},
                                   color_discrete_sequence=['#1F497D', '#2ca02c'])
                st.plotly_chart(fig_multi, use_container_width=True)

            with col_v2:
                st.subheader("Relación Ventas vs Utilidad (Último Año)")
                # Filtramos el año actual para ver meses
                df_meses = df[df['anio'] == df['anio'].max()].groupby('mes').agg({'TOTAL_VENTA_DIARIA_GS':'sum', 'UTILIDAD_BRUTA_DIARIA_GS':'sum'}).reset_index()
                
                fig_combo = go.Figure()
                fig_combo.add_trace(go.Bar(x=df_meses['mes'], y=df_meses['TOTAL_VENTA_DIARIA_GS'], name='Ventas', marker_color='#1F497D'))
                fig_combo.add_trace(go.Scatter(x=df_meses['mes'], y=df_meses['UTILIDAD_BRUTA_DIARIA_GS'], name='Utilidad', mode='lines+markers', line=dict(color='red', width=3)))
                fig_combo.update_layout(title="Ventas (Barras) vs Utilidad (Línea) Mensual", xaxis_title="Mes", yaxis_title="Guaraníes")
                st.plotly_chart(fig_combo, use_container_width=True)
                
                kpi_v_mes = get_kpi_data("Ventas Mensual")
                if kpi_v_mes is not None:
                     st.info(f"💡 Crecimiento mensual actual vs año anterior: **{kpi_v_mes['Variacion_Pct']:.2%}**")


        # --- PESTAÑA 3: OPERACIONES Y CLIENTES ---
        with tabs[2]:
            st.header("Operaciones y Clientes")
            
            # Últimos 90 días para ver tendencia clara
            fecha_inicio_90 = fecha_selec - pd.Timedelta(days=90)
            df_90 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > fecha_inicio_90)].sort_values('fecha')

            c_op1, c_op2 = st.columns(2)
            
            with c_op1:
                st.subheader("Tendencia de Visitas")
                fig_visitas = px.area(df_90, x='fecha', y='NRO_VISITAS_DIARIAS', title="Visitas (Últimos 90 días)", color_discrete_sequence=['#ff7f0e'])
                st.plotly_chart(fig_visitas, use_container_width=True)
                
            with c_op2:
                st.subheader("Evolución: Ticket vs Cantidad")
                # Gráfico dual
                fig_tck = go.Figure()
                fig_tck.add_trace(go.Bar(x=df_90['fecha'], y=df_90['CANT_TICKETS_DIARIOS'], name='Cant. Tickets', yaxis='y1'))
                fig_tck.add_trace(go.Scatter(x=df_90['fecha'], y=df_90['TICKET_PROMEDIO_MENSUAL_DATO'], name='Monto Ticket Prom.', yaxis='y2', line=dict(color='red')))
                
                fig_tck.update_layout(
                    yaxis=dict(title='Cantidad', side='left'),
                    yaxis2=dict(title='Monto (Gs)', side='right', overlaying='y', showgrid=False),
                    title="Tickets Emitidos vs Valor del Ticket"
                )
                st.plotly_chart(fig_tck, use_container_width=True)

            # Embudo de Conversión
            st.subheader("Embudo de Conversión (Día Seleccionado)")
            fig_funnel = go.Figure(go.Funnel(
                y = ["Total Visitas", "Tickets Emitidos"],
                x = [visitas, tickets],
                textinfo = "value+percent initial",
                marker = {"color": ["#1F497D", "#2ca02c"]}
            ))
            st.plotly_chart(fig_funnel, use_container_width=True)


        # --- PESTAÑA 4: INVENTARIO ---
        with tabs[3]:
            st.header("Gestión de Inventario (Foto Actual)")
            
            kpi_stock_val = get_kpi_data("Stock Valorizado")
            kpi_stock_qty = get_kpi_data("Cant. Items Stock")
            # Si no tienes SKU en df_kpis, usamos el de cantidad como placeholder o lo dejas en N/A
            
            i1, i2, i3 = st.columns(3)
            
            if kpi_stock_val is not None:
                i1.metric("Inventario Salón Día (Valorizado)", f"₲ {kpi_stock_val['Anio_Actual']:,.0f}", f"{kpi_stock_val['Variacion_Pct']:.2%} vs Año Ant.")
            if kpi_stock_qty is not None:
                i2.metric("Cantidad de Items Físicos", f"{kpi_stock_qty['Anio_Actual']:,.0f}", f"{kpi_stock_qty['Variacion_Pct']:.2%} vs Año Ant.")
            
            # Placeholder para SKUs (Si lo subes desde Python, agregalo a get_kpi_data)
            i3.metric("Cantidad de SKUs Activos", "N/D", "Requiere integración")

            with st.expander("Ver Histórico de Inventario (Si está disponible)"):
                st.info("Aquí puedes cargar una tabla detallada de movimientos si la exportas desde SQL.")


        # --- PESTAÑA 5: MEDIAS 14 DÍAS ---
        with tabs[4]:
            st.header("Análisis de Desviación (Media Móvil 14 Días)")
            st.markdown("Comparación del rendimiento actual vs. el promedio de las últimas dos semanas.")
            
            kpi_m14_v = get_kpi_data("Media Movil 14 Dias (Ventas)")
            kpi_m14_u = get_kpi_data("Media Movil 14 Dias (Utilidad)")
            
            def mostrar_alerta_media(kpi_data, titulo):
                if kpi_data is None: return
                
                # Manejo de anomalías (-100% o valores extremos)
                variacion = kpi_data['Variacion_Pct']
                if variacion <= -0.99: # Cae 99% o 100%
                    st.error(f"⚠️ **Alerta en {titulo}:** Caída anómala del {variacion:.2%}. Posible falta de carga de datos o cierre de sucursal.")
                elif variacion > 0:
                    st.success(f"📈 **{titulo}:** Por encima de la media en {variacion:.2%}.")
                else:
                    st.warning(f"📉 **{titulo}:** Por debajo de la media en {variacion:.2%}.")
                    
                # Gráfico de Delta horizontal
                fig_delta = go.Figure(go.Indicator(
                    mode = "delta",
                    value = kpi_data['Anio_Actual'],
                    delta = {'reference': kpi_data['Anio_Anterior'], 'relative': True, 'position': "right"},
                    title = {'text': f"{titulo} vs Media"}
                ))
                fig_delta.update_layout(height=150)
                st.plotly_chart(fig_delta, use_container_width=True)

            m_col1, m_col2 = st.columns(2)
            with m_col1: mostrar_alerta_media(kpi_m14_v, "Ventas Diarias")
            with m_col2: mostrar_alerta_media(kpi_m14_u, "Utilidad Diaria")


        # --- PESTAÑA 6: GRÁFICOS ORIGINALES (30 Días) ---
        with tabs[5]:
            st.header("Evolución Últimos 30 Días (Vista Clásica)")
            fecha_inicio_30 = fecha_selec - pd.Timedelta(days=30)
            df_30 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > fecha_inicio_30)].sort_values('fecha')

            g_col1, g_col2 = st.columns(2)
            with g_col1:
                fig_v = px.bar(df_30, x='fecha', y='TOTAL_VENTA_DIARIA_GS', title="Evolución de Venta Diaria", text_auto='.2s')
                st.plotly_chart(fig_v, use_container_width=True)
            with g_col2:
                fig_mix = px.line(df_30, x='fecha', y=['CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS'], title="Tráfico vs Compra", markers=True)
                st.plotly_chart(fig_mix, use_container_width=True)

            with st.expander("📂 Ver Tabla de Datos Completa"):
                st.dataframe(df_30.sort_values('fecha', ascending=False).style.format({
                    'TOTAL_VENTA_DIARIA_GS': '₲ {:,.0f}',
                    'UTILIDAD_BRUTA_DIARIA_GS': '₲ {:,.0f}',
                }))

    else:
        st.warning(f"⚠️ No se encontraron datos cargados para la fecha: {fecha_selec.strftime('%d/%m/%Y')}")
