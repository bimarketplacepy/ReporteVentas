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
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
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
                      'TICKET_PROM_MENSUAL_DATO', 'VENTA_ACUM_ANUAL', 'UTILIDAD_ACUM_ANUAL',
                      'VENTA_ACUM_MENSUAL', 'UTILIDAD_ACUM_MENSUAL', 'VISITAS_ACUM_MENSUAL']
    
    for col in cols_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
    df['fecha'] = pd.to_datetime(df['fecha'])
    df['anio'] = df['fecha'].dt.year
    df['mes'] = df['fecha'].dt.month
    df['dia_num'] = df['fecha'].dt.day

    # 3.2 Leer KPIs Complejos (Para inventario foto)
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
        # 1. LA VISTA BASE ORIGINAL (TARJETAS GRANDES DEL DÍA)
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
        
        # =====================================================================
        # FUNCIONES MATEMÁTICAS DINÁMICAS (Usando TD_Anual_Data)
        # =====================================================================
        def obtener_yoy(columna):
            """Calcula el valor actual, año anterior, % y diferencia para una columna acumulada"""
            val_actual = df_dia[columna].sum()
            df_ant = df[(df['anio'] == fecha_selec.year - 1) & (df['mes'] == fecha_selec.month) & (df['dia_num'] == fecha_selec.day)]
            val_ant = df_ant[columna].sum() if not df_ant.empty else 0
            var = (val_actual / val_ant - 1) if val_ant > 0 else 0
            diff = val_actual - val_ant
            return val_actual, val_ant, var, diff

        def get_visitas_ytd(year, target_date):
            """Calcula visitas acumuladas del año hasta una fecha exacta (para no depender de mensuales)"""
            mask = (df['anio'] == year) & (
                (df['mes'] < target_date.month) | 
                ((df['mes'] == target_date.month) & (df['dia_num'] <= target_date.day))
            )
            return df[mask]['NRO_VISITAS_DIARIAS'].sum()


        # =====================================================================
        # 2. SISTEMA DE PESTAÑAS
        # =====================================================================
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📈 Ventas Diarias",           
            "👥 Ticket vs Visitas",        
            "1️⃣ Resumen (KPIs)",           
            "2️⃣ Ventas y Rentabilidad",    
            "3️⃣ Operaciones y Clientes",   
            "4️⃣ Inventario",               
            "5️⃣ Medias (14 Días)"          
        ])

        df_30 = df[(df['fecha'] <= fecha_selec) & (df['fecha'] > (fecha_selec - pd.Timedelta(days=30)))].sort_values('fecha')

        # --- PESTAÑAS ORIGINALES (30 días) ---
        with tab1:
            fig_v = px.bar(df_30, x='fecha', y='TOTAL_VENTA_DIARIA_GS', title="Evolución de Venta Diaria (Últimos 30 días)", text_auto='.2s')
            fig_v.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False, marker_color='#1F497D')
            st.plotly_chart(fig_v, use_container_width=True)
            
        with tab2:
            fig_mix = px.line(df_30, x='fecha', y=['CANT_TICKETS_DIARIOS', 'NRO_VISITAS_DIARIAS'], title="Comparativo Tráfico vs Compra", markers=True)
            st.plotly_chart(fig_mix, use_container_width=True)

        # --- NUEVA PESTAÑA 1: RESUMEN EJECUTIVO (ANUAL Y MENSUAL) ---
        with tab3:
            st.subheader("Indicadores Acumulados ANUAL")
            
            v_anual_act, v_anual_ant, var_v_anual, diff_v_anual = obtener_yoy('VENTA_ACUM_ANUAL')
            u_anual_act, u_anual_ant, var_u_anual, diff_u_anual = obtener_yoy('UTILIDAD_ACUM_ANUAL')
            
            # MDR Anual se calcula dividiendo la utilidad anual entre la venta anual
            mdr_anual_act = (u_anual_act / v_anual_act) if v_anual_act > 0 else 0
            mdr_anual_ant = (u_anual_ant / v_anual_ant) if v_anual_ant > 0 else 0
            
            vis_anual_act = get_visitas_ytd(fecha_selec.year, fecha_selec)
            vis_anual_ant = get_visitas_ytd(fecha_selec.year - 1, fecha_selec)
            var_vis_anual = (vis_anual_act / vis_anual_ant - 1) if vis_anual_ant > 0 else 0
            diff_vis_anual = vis_anual_act - vis_anual_ant

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Ventas Anuales", f"₲ {v_anual_act:,.0f}", f"{var_v_anual:.2%} (₲ {diff_v_anual:,.0f})")
            c2.metric("Utilidad Bruta Anual", f"₲ {u_anual_act:,.0f}", f"{var_u_anual:.2%} (₲ {diff_u_anual:,.0f})")
            c3.metric("Visitas Acumuladas", f"{vis_anual_act:,.0f}", f"{var_vis_anual:.2%} ({diff_vis_anual:,.0f})")

            # Gráfico Gauge para MDR
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=mdr_anual_act * 100,
                title={'text': "Margen de Rentabilidad (MDR)"},
                delta={'reference': mdr_anual_ant * 100, 'position': "top"},
                gauge={
                    'axis': {'range': [None, 50]},
                    'bar': {'color': "#1F497D"},
                    'steps': [{'range': [0, 25], 'color': "lightgray"}, {'range': [25, 35], 'color': "gray"}],
                    'threshold': {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': 36}
                }
            ))
            fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
            c4.plotly_chart(fig_gauge, use_container_width=True)

            st.divider()
            
            st.subheader("Indicadores Acumulados MENSUAL")
            v_mes_act, v_mes_ant, var_v_mes, diff_v_mes = obtener_yoy('VENTA_ACUM_MENSUAL')
            u_mes_act, u_mes_ant, var_u_mes, diff_u_mes = obtener_yoy('UTILIDAD_ACUM_MENSUAL')
            vis_mes_act, vis_mes_ant, var_vis_mes, diff_vis_mes = obtener_yoy('VISITAS_ACUM_MENSUAL')
            
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("Ventas del Mes", f"₲ {v_mes_act:,.0f}", f"{var_v_mes:.2%} (₲ {diff_v_mes:,.0f})")
            cm2.metric("Utilidad del Mes", f"₲ {u_mes_act:,.0f}", f"{var_u_mes:.2%} (₲ {diff_u_mes:,.0f})")
            cm3.metric("Visitas del Mes", f"{vis_mes_act:,.0f}", f"{var_vis_mes:.2%} ({diff_vis_mes:,.0f})")

        # --- NUEVA PESTAÑA 2: VENTAS Y RENTABILIDAD ---
        with tab4:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.subheader("Comparativo Multianual Exacto (Mismo Día/Mes)")
                # Filtramos la base de datos exactamente para el mismo día y mes de todos los años
                df_multianual = df[(df['mes'] == fecha_selec.month) & (df['dia_num'] == fecha_selec.day)]
                fig_multi = px.bar(df_multianual, x='anio', y=['VENTA_ACUM_ANUAL', 'UTILIDAD_ACUM_ANUAL'], 
                                   barmode='group', labels={'value': 'Guaraníes', 'variable': 'Métrica'},
                                   color_discrete_sequence=['#1F497D', '#2ca02c'])
                st.plotly_chart(fig_multi, use_container_width=True)

            with col_v2:
                st.subheader("Relación Mensual (Año Actual)")
                df_meses = df[df['anio'] == fecha_selec.year].groupby('mes').agg({'TOTAL_VENTA_DIARIA_GS':'sum', 'UTILIDAD_BRUTA_DIARIA_GS':'sum'}).reset_index()
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
                fig_tck.add_trace(go.Scatter(x=df_90['fecha'], y=df_90['TICKET_PROM_MENSUAL_DATO'], name='Monto Ticket', yaxis='y2', line=dict(color='red')))
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
            
            def get_kpi_stock(nombre):
                if not df_kpis.empty:
                    fila = df_kpis[df_kpis['KPI'] == nombre]
                    if not fila.empty:
                        return fila.iloc[0]
                return None

            k_val = get_kpi_stock("Stock Valorizado")
            k_qty = get_kpi_stock("Cant. Items Stock")
            k_sku = get_kpi_stock("Cant. SKU Stock") # <--- AHORA LEERÁ LA LÍNEA NUEVA QUE AGREGASTE
            
            i1, i2, i3 = st.columns(3)
            if k_val is not None:
                i1.metric("Valorizado de Salón", f"₲ {k_val['Anio_Actual']:,.0f}", f"{k_val['Variacion_Pct']:.2%} vs Año Ant.")
            if k_qty is not None:
                i2.metric("Unidades Físicas", f"{k_qty['Anio_Actual']:,.0f}", f"{k_qty['Variacion_Pct']:.2%} vs Año Ant.")
            if k_sku is not None:
                i3.metric("SKUs Activos", f"{k_sku['Anio_Actual']:,.0f}", f"{k_sku['Variacion_Pct']:.2%} vs Año Ant.")
            else:
                i3.metric("SKUs Activos", "N/D", "Falta agregar a script local")

        # --- NUEVA PESTAÑA 5: MEDIAS (14 DÍAS) ---
        with tab7:
            st.subheader("Desviación contra Media Móvil (14 días)")
            st.info("💡 Compara el resultado de HOY con el rendimiento promedio de los últimos 14 días.")
            
            # Calculamos las medias directamente aquí
            df_14 = df[(df['fecha'] > (fecha_selec - pd.Timedelta(days=14))) & (df['fecha'] <= fecha_selec)]
            
            def calc_14dias(columna):
                media = df_14[columna].mean()
                actual = df_dia[columna].sum()
                var = (actual / media - 1) if media > 0 else 0
                return actual, media, var

            def render_alerta(titulo, columna, es_porcentaje=False):
                actual, media, var = calc_14dias(columna)
                
                # Formato de visualización
                val_txt = f"{actual:.2%}" if es_porcentaje else f"₲ {actual:,.0f}" if actual > 1000 else f"{actual:,.0f}"
                media_txt = f"{media:.2%}" if es_porcentaje else f"₲ {media:,.0f}" if media > 1000 else f"{media:,.0f}"
                
                if var <= -0.99:
                    st.error(f"🚨 **{titulo}:** Caída del {var:.2%}. Actual {val_txt} vs Media {media_txt}.")
                else:
                    color = "normal" if var > 0 else "inverse"
                    st.metric(f"{titulo} (Actual vs Media)", f"{val_txt}", f"{var:.2%}", delta_color=color)

            # Mostramos los 6 indicadores que pediste en 3 columnas y 2 filas
            m1, m2, m3 = st.columns(3)
            with m1: render_alerta("Ventas Diarias", "TOTAL_VENTA_DIARIA_GS")
            with m2: render_alerta("Utilidad Diaria", "UTILIDAD_BRUTA_DIARIA_GS")
            with m3: render_alerta("MDR Diario", "MDR_DIARIO", es_porcentaje=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            m4, m5, m6 = st.columns(3)
            with m4: render_alerta("Visitas Diarias", "NRO_VISITAS_DIARIAS")
            with m5: render_alerta("Tickets Diarios", "CANT_TICKETS_DIARIOS")
            with m6: render_alerta("Ticket Promedio", "TICKET_PROM_MENSUAL_DATO")

        # =====================================================================
        # 3. TABLA DE DATOS ORIGINAL AL FINAL
        # =====================================================================
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📂 Ver Tabla de Datos Completa (30 Días)"):
            st.dataframe(df_30.sort_values('fecha', ascending=False).style.format({
                'TOTAL_VENTA_DIARIA_GS': '₲ {:,.0f}',
                'UTILIDAD_BRUTA_DIARIA_GS': '₲ {:,.0f}',
                'TICKET_PROM_MENSUAL_DATO': '₲ {:,.0f}'
            }))

    else:
        st.warning(f"⚠️ No se encontraron datos cargados para la fecha: {fecha_selec.strftime('%d/%m/%Y')}")
