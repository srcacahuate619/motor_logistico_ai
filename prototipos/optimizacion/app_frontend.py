"""
app_frontend.py — Frontend Streamlit
 
CAMBIOS:
  - Dirección de base: sin valor predeterminado, el usuario debe ingresarla
    O se detecta automáticamente del Excel si tiene columna 'base'/'depot'
  - Tipo de vehículo: se muestra como 3 botones, sin selección predeterminada
    O se detecta automáticamente del Excel (si todos los pedidos son del mismo tipo)
"""
 
import io
import re
import logging
import streamlit as st
import pandas as pd
 
from app.core.engine import ejecutar_pipeline, OptimizationResult
 
logging.basicConfig(level=logging.INFO)
 
LIMITE_FILAS = 50
 
# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Motor Logístico AI",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
h1, h2, h3, h4 { font-family: 'IBM Plex Mono', monospace; letter-spacing: -0.5px; }
.stApp { background-color: #0f1117; color: #e2e8f0; }
.block-container { padding-top: 1.5rem; }
[data-testid="metric-container"] {
    background: #1e2433; border: 1px solid #2d3748;
    border-radius: 8px; padding: 12px;
}
hr { border: none; height: 1px;
     background: linear-gradient(90deg, #3b82f6, #60a5fa, transparent);
     margin: 1.2rem 0; }
 
/* Botones de vehículo */
div[data-testid="column"] button {
    width: 100%;
    border-radius: 8px;
    font-weight: 600;
    font-size: 15px;
    padding: 0.6rem 0;
}
</style>
""", unsafe_allow_html=True)
 
 
# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
 
def _limpiar(col: str) -> str:
    col = str(col).strip().lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        col = col.replace(a, b)
    return re.sub(r"\s+", "_", col)
 
 
def _detectar_vehiculo_del_excel(df_raw: pd.DataFrame) -> str | None:
    """
    Si el Excel tiene columna de tipo_vehiculo y todos los valores
    son el mismo tipo, lo devuelve. Si hay mezcla o no existe, devuelve None.
    """
    sinonimos_veh = [
        "tipo_vehiculo", "tipo vehiculo", "vehiculo", "vehículo",
        "tipo", "vehicle", "unidad", "transport", "transporte"
    ]
    cols_limpias = {_limpiar(c): c for c in df_raw.columns}
    col_encontrada = next(
        (cols_limpias[_limpiar(s)] for s in sinonimos_veh if _limpiar(s) in cols_limpias),
        None
    )
    if not col_encontrada:
        return None
 
    def normalizar(v):
        s = str(v).strip().lower()
        for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")]:
            s = s.replace(a, b)
        if any(t in s for t in ["trailer","truck","pesado","tractor"]):
            return "Trailer"
        if any(t in s for t in ["camioneta","van","pickup","suv"]):
            return "Camioneta"
        if any(t in s for t in ["carro","car","auto","sedan"]):
            return "Carro"
        return None
 
    tipos = df_raw[col_encontrada].dropna().apply(normalizar).dropna().unique().tolist()
    return tipos[0] if len(tipos) == 1 else None   # solo si son todos iguales
 
 
def _detectar_depot_del_excel(df_raw: pd.DataFrame) -> str | None:
    """
    Busca una columna 'base', 'depot', 'origen', 'almacen' con un valor único
    que podría ser la dirección de salida del vehículo.
    """
    sinonimos_depot = ["base", "depot", "deposito", "depósito", "origen", "almacen", "almacén", "bodega"]
    cols_limpias = {_limpiar(c): c for c in df_raw.columns}
    col_encontrada = next(
        (cols_limpias[_limpiar(s)] for s in sinonimos_depot if _limpiar(s) in cols_limpias),
        None
    )
    if not col_encontrada:
        return None
 
    valores = df_raw[col_encontrada].dropna().astype(str).str.strip().unique().tolist()
    return valores[0] if len(valores) == 1 else None
 
 
# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
st.title("🚚  Motor de Logística & Optimización de Rutas")
st.caption(
    "Sube un Excel con pedidos — sin importar su estructura. "
    "El motor detecta las columnas, limpia direcciones con IA y calcula la ruta óptima."
)
st.markdown("<hr>", unsafe_allow_html=True)
 
with st.expander("📋 ¿Cómo preparar tu Excel?"):
    st.markdown("""
**Columna obligatoria:**
| Columna | Nombres aceptados |
|---|---|
| Dirección | `direccion`, `domicilio`, `address`, `calle`, `destino`, `ubicacion` |
 
**Columnas opcionales** (el motor las detecta automáticamente):
| Columna | Nombres aceptados | Default si no existe |
|---|---|---|
| ID | `id`, `folio`, `pedido`, `orden`, `referencia` | Se genera automático |
| Cliente | `cliente`, `nombre`, `destinatario`, `empresa` | Usa el ID |
| Ventana inicio | `ventana_inicio`, `inicio`, `apertura`, `time_from` | 08:00 |
| Ventana fin | `ventana_fin`, `fin`, `cierre`, `time_to` | 18:00 |
| Tipo vehículo | `tipo_vehiculo`, `vehiculo`, `unidad` | El que selecciones abajo |
| Peso (kg) | `peso_kg`, `peso`, `kg`, `carga_kg` | 0 |
| Base/Depósito | `base`, `depot`, `origen`, `almacen` | El que ingreses abajo |
| Notas | `notas`, `observaciones`, `instrucciones_especiales` | vacío |
    """)
 
with st.expander("⚙️ Pipeline del motor"):
    cols = st.columns(4)
    for col, (num, titulo, desc) in zip(cols, [
        ("1️⃣", "Pandas",    "Detecta columnas de cualquier Excel automáticamente"),
        ("2️⃣", "Claude AI", "Estandariza direcciones caóticas a formato geocodificable"),
        ("3️⃣", "Mapbox",    "Geocodifica, matriz de tiempos con tráfico real, restricciones físicas"),
        ("4️⃣", "OR-Tools",  "Resuelve VRPTW: ruta más corta respetando todos los horarios"),
    ]):
        col.markdown(f"**{num} {titulo}**")
        col.caption(desc)
 
st.markdown("<hr>", unsafe_allow_html=True)
 
# ─────────────────────────────────────────────────────────────
# CARGA DE ARCHIVO  (primero, antes del sidebar)
# ─────────────────────────────────────────────────────────────
archivo = st.file_uploader(
    "📂  Sube tu Excel de entregas (.xlsx)",
    type=["xlsx"],
    help=f"Máximo {LIMITE_FILAS} filas en esta demo."
)
 
# Leer preview del Excel para autodetección
df_preview        = None
vehiculo_detectado = None
depot_detectado    = None
 
if archivo is not None:
    try:
        # Escanear primeras filas para detectar la fila de headers
        df_scan = pd.read_excel(archivo, header=None, nrows=5)
        archivo.seek(0)
 
        # Detectar fila de headers (la que tiene más columnas conocidas)
        TODOS_SIN = {
            "id","folio","pedido","order","referencia","direccion","dirección",
            "domicilio","address","calle","destino","cliente","nombre","customer",
            "ventana_inicio","inicio","apertura","time_from","ventana_fin","fin",
            "cierre","time_to","tipo_vehiculo","vehiculo","vehicle","peso","kg",
            "notas","observaciones","base","depot","origen","almacen"
        }
        mejor_fila, mejor_score = 0, 0
        for i in range(len(df_scan)):
            vals  = df_scan.iloc[i].dropna().astype(str).tolist()
            score = sum(1 for v in vals if _limpiar(v) in {_limpiar(s) for s in TODOS_SIN})
            if score > mejor_score:
                mejor_score, mejor_fila = score, i
 
        df_preview = pd.read_excel(archivo, header=mejor_fila)
        archivo.seek(0)
        df_preview = df_preview.loc[:, ~df_preview.columns.str.startswith("Unnamed")]
 
        vehiculo_detectado = _detectar_vehiculo_del_excel(df_preview)
        depot_detectado    = _detectar_depot_del_excel(df_preview)
 
    except Exception:
        pass   # errores de lectura se manejan después
 
# ─────────────────────────────────────────────────────────────
# SIDEBAR — configuración
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    st.markdown("---")
 
    # ── Dirección de base ────────────────────────────────────
    st.markdown("### 📍 Base / Depósito")
 
    if depot_detectado:
        st.success(f"✅ Detectado del Excel: `{depot_detectado[:50]}...`" if len(depot_detectado) > 50 else f"✅ Detectado del Excel: `{depot_detectado}`")
        depot_dir = st.text_input(
            "Confirmar o modificar dirección base",
            value=depot_detectado,
            help="Punto de partida y regreso del vehículo"
        )
    else:
        depot_dir = st.text_input(
            "Dirección de tu base / depósito",
            value="",
            placeholder="Ej: Av. Constitución 100, Centro, Monterrey, NL",
            help="Punto de partida y regreso. Si tu Excel tiene columna 'base' o 'depot', se detecta automáticamente."
        )
 
    if not depot_dir or not depot_dir.strip():
        st.warning("⚠️ Ingresa la dirección de tu base para continuar.")
 
    st.markdown("---")
 
    # ── Tipo de vehículo ─────────────────────────────────────
    st.markdown("### 🚛 Tipo de vehículo")
 
    if vehiculo_detectado:
        st.success(f"✅ Detectado del Excel: **{vehiculo_detectado}**")
        st.caption("Puedes cambiarlo si lo necesitas:")
 
    # Inicializar session_state si no existe
    if "tipo_vehiculo" not in st.session_state:
        st.session_state.tipo_vehiculo = vehiculo_detectado  # puede ser None
 
    # Autodetección cambia el valor si el usuario aún no eligió manualmente
    if vehiculo_detectado and st.session_state.tipo_vehiculo is None:
        st.session_state.tipo_vehiculo = vehiculo_detectado
 
    # 3 botones — uno por tipo
    iconos = {"Carro": "🚗", "Camioneta": "🚐", "Trailer": "🚛"}
    col_c, col_v, col_t = st.columns(3)
    for col_btn, tipo in zip([col_c, col_v, col_t], ["Carro", "Camioneta", "Trailer"]):
        seleccionado = st.session_state.tipo_vehiculo == tipo
        label = f"{iconos[tipo]}\n**{tipo}**" if seleccionado else f"{iconos[tipo]}\n{tipo}"
        btn_type = "primary" if seleccionado else "secondary"
        if col_btn.button(label, key=f"btn_{tipo}", type=btn_type, use_container_width=True):
            st.session_state.tipo_vehiculo = tipo
            st.rerun()
 
    tipo_vehiculo = st.session_state.tipo_vehiculo
 
    if tipo_vehiculo is None:
        st.warning("⚠️ Selecciona el tipo de vehículo.")
 
    # Restricciones físicas solo para Trailer
    peso_ton = 0.0
    altura_m = 0.0
    if tipo_vehiculo == "Trailer":
        st.markdown("#### Restricciones físicas")
        peso_ton = st.number_input(
            "Peso máximo (toneladas)", min_value=0.5, max_value=50.0,
            value=15.0, step=0.5,
            help="Mapbox evitará vías con restricción de peso menor a este valor"
        )
        altura_m = st.number_input(
            "Altura máxima (metros)", min_value=2.0, max_value=6.0,
            value=4.2, step=0.1,
            help="Mapbox evitará puentes con altura libre menor a este valor"
        )
 
    st.markdown("---")
    st.caption("**Stack:** Pandas · Claude AI · Mapbox · OR-Tools")
 
# ─────────────────────────────────────────────────────────────
# ESTADO DEL ARCHIVO
# ─────────────────────────────────────────────────────────────
if archivo is None:
    st.info("⬆️  Sube un archivo Excel para comenzar.")
    st.stop()
 
if df_preview is not None and len(df_preview) > LIMITE_FILAS:
    st.error(
        f"⚠️ El archivo tiene **{len(df_preview)} filas**. "
        f"El límite de esta demo es **{LIMITE_FILAS}**."
    )
    st.stop()
 
if df_preview is not None:
    st.success(f"✅ Archivo cargado: **{len(df_preview)} filas · {len(df_preview.columns)} columnas**")
    with st.expander("👁️ Vista previa del Excel original"):
        st.dataframe(df_preview.astype(str), use_container_width=True)
 
# ─────────────────────────────────────────────────────────────
# VALIDACIONES ANTES DE EJECUTAR
# ─────────────────────────────────────────────────────────────
listo = True
 
if not depot_dir or not depot_dir.strip():
    st.error("❌ Ingresa la dirección de tu base en el panel izquierdo.")
    listo = False
 
if tipo_vehiculo is None:
    st.error("❌ Selecciona el tipo de vehículo en el panel izquierdo.")
    listo = False
 
if not listo:
    st.stop()
 
# ─────────────────────────────────────────────────────────────
# BOTÓN DE EJECUCIÓN
# ─────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
if not st.button(
    f"🚀  Optimizar ruta — {iconos.get(tipo_vehiculo,'')} {tipo_vehiculo}",
    type="primary",
    use_container_width=True
):
    st.stop()
 
# ─────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────
archivo.seek(0)
progress = st.progress(0, text="Iniciando...")
 
with st.status("⚙️  Ejecutando pipeline logístico...", expanded=True) as status:
 
    st.write(f"**Paso 1/4** 🧹 Pandas — Detectando estructura del Excel...")
    progress.progress(5, "Pandas: leyendo Excel...")
 
    result: OptimizationResult = ejecutar_pipeline(
        archivo          = archivo,
        tipo_vehiculo_ui = tipo_vehiculo,
        peso_toneladas   = peso_ton,
        altura_metros    = altura_m,
        depot_direccion  = depot_dir.strip(),
    )
 
    for i, paso in enumerate(result.pasos):
        pct   = min(95, int(((i + 1) / max(len(result.pasos), 1)) * 90) + 5)
        icono = "✅" if paso.ok else "❌"
        st.write(f"**{icono} {paso.nombre}** — {paso.mensaje}")
        if paso.detalle:
            st.caption(f"   ↳ {paso.detalle}")
        progress.progress(pct, paso.nombre)
 
    if result.exito:
        status.update(label="✅ Optimización completada", state="complete", expanded=False)
        progress.progress(100, "¡Listo!")
    else:
        status.update(label=f"❌ {result.error}", state="error", expanded=True)
 
# ─────────────────────────────────────────────────────────────
# ERROR
# ─────────────────────────────────────────────────────────────
if not result.exito:
    st.error(f"**Error:** {result.error}")
    for w in result.advertencias:
        st.warning(w)
    st.stop()
 
# ─────────────────────────────────────────────────────────────
# ADVERTENCIAS NO CRÍTICAS
# ─────────────────────────────────────────────────────────────
for w in result.advertencias:
    st.warning(w)
 
# ─────────────────────────────────────────────────────────────
# RESULTADOS
# ─────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("📊 Resumen ejecutivo")
 
col1, col2, col3, col4 = st.columns(4)
col1.metric("Entregas optimizadas",  result.n_entregas)
col2.metric("Omitidas (geocoding)",  result.n_fallidas_geo)
col3.metric("Vehículo",              f"{iconos.get(tipo_vehiculo,'')} {tipo_vehiculo}")
if result.ruta_trailer:
    col4.metric("Distancia total", f"{result.ruta_trailer['distancia_total_km']} km")
else:
    col4.metric("Pasos completados", len(result.pasos))
 
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("📍 Ruta óptima calculada")
st.code(result.ruta_texto, language="text")
 
st.subheader("📋 Orden de entrega con tiempos reales")
if result.df_ordenado is not None:
    st.dataframe(result.df_ordenado.astype(str), use_container_width=True)
 
if result.df_con_coords is not None:
    with st.expander("🗺️ Datos completos con coordenadas"):
        st.dataframe(result.df_con_coords.astype(str), use_container_width=True)
 
# ─────────────────────────────────────────────────────────────
# DESCARGA
# ─────────────────────────────────────────────────────────────
st.markdown("<hr>", unsafe_allow_html=True)
 
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    if result.df_ordenado is not None:
        result.df_ordenado.to_excel(writer, index=False, sheet_name="Ruta_Optimizada")
    if result.df_con_coords is not None:
        result.df_con_coords.to_excel(writer, index=False, sheet_name="Con_Coordenadas")
    if result.df_normalizado is not None:
        result.df_normalizado.to_excel(writer, index=False, sheet_name="Datos_Normalizados")
 
st.download_button(
    label       = f"📥  Descargar resultados — {tipo_vehiculo} (.xlsx)",
    data        = buffer.getvalue(),
    file_name   = f"ruta_{tipo_vehiculo.lower()}_optimizada.xlsx",
    mime        = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width = True,
)