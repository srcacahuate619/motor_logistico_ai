"""
app/services/excel_parser.py
 
FIX: Detección automática de la fila de headers.
Algunos Excels tienen un título en la fila 1 y los headers reales en la fila 2.
El parser ahora escanea las primeras 5 filas para encontrar dónde están los headers.
"""
 
import re
import logging
import pandas as pd
from typing import Optional
 
logger = logging.getLogger("ExcelParser")
 
MAX_PARADAS = 23
 
SINONIMOS: dict[str, list[str]] = {
    "id": [
        "id", "id_pedido", "folio", "pedido", "orden", "order",
        "numero", "num", "clave", "code", "referencia", "ref", "no.", "no", "#"
    ],
    "direccion_raw": [
        "direccion", "dirección", "direccion_original", "dirección_original",
        "domicilio", "address", "calle", "entrega", "destino", "ubicacion",
        "lugar_entrega", "lugar de entrega", "dir", "ubicación"
    ],
    "cliente": [
        "cliente", "nombre_cliente", "destinatario", "receptor", "nombre",
        "customer", "name", "razon_social", "razón social", "empresa",
        "negocio", "contacto"
    ],
    "ventana_inicio": [
        "ventana_inicio", "inicio", "apertura", "hora_inicio", "hora inicio",
        "desde", "open", "time_from", "ventana inicio", "horario_inicio", "de"
    ],
    "ventana_fin": [
        "ventana_fin", "fin", "cierre", "hora_fin", "hora fin", "hasta",
        "close", "time_to", "ventana fin", "horario_fin", "a", "limite",
        "límite", "limite_entrega"
    ],
    "tipo_vehiculo": [
        "tipo_vehiculo", "tipo vehiculo", "vehiculo", "vehículo", "tipo",
        "vehicle", "unidad", "transport", "transporte"
    ],
    "peso_kg": [
        "peso_kg", "peso", "weight", "kg", "kilos", "kilogramos",
        "peso_total", "carga", "carga_kg"
    ],
    "volumen_m3": [
        "volumen_m3", "volumen", "volume", "m3", "metros_cubicos", "vol", "vol_m3"
    ],
    "notas": [
        "notas", "observaciones", "comentarios", "notes", "remarks",
        "instrucciones", "indicaciones", "instrucciones_especiales"
    ],
}
 
# Todos los sinónimos en un set plano para búsqueda rápida
TODOS_SINONIMOS = {_s for sins in SINONIMOS.values() for _s in sins}
 
 
class ExcelParserError(Exception):
    pass
 
 
def _limpiar_col(col: str) -> str:
    col = str(col).strip().lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ü","u"),("ñ","n")]:
        col = col.replace(a, b)
    return re.sub(r"\s+", "_", col)
 
 
def _detectar_fila_header(archivo) -> int:
    """
    Escanea las primeras 5 filas del Excel y devuelve el índice (0-based)
    de la fila que contiene la mayor cantidad de nombres de columnas conocidos.
    Esto permite leer Excels con títulos decorativos en las primeras filas.
    """
    df_scan = pd.read_excel(archivo, header=None, nrows=5)
    archivo.seek(0)  # reset para lectura posterior
 
    mejor_fila  = 0
    mejor_score = 0
 
    for fila_idx in range(len(df_scan)):
        fila_vals = df_scan.iloc[fila_idx].dropna().astype(str).tolist()
        score = sum(
            1 for v in fila_vals
            if _limpiar_col(v) in {_limpiar_col(s) for s in TODOS_SINONIMOS}
        )
        if score > mejor_score:
            mejor_score = score
            mejor_fila  = fila_idx
 
    if mejor_score == 0:
        logger.warning("No se detectaron headers conocidos en las primeras 5 filas. Usando fila 0.")
 
    logger.info(f"Header detectado en fila {mejor_fila} (score={mejor_score})")
    return mejor_fila
 
 
def _detectar_columna(df_cols: list[str], candidatos: list[str]) -> Optional[str]:
    cols_limpias = {_limpiar_col(c): c for c in df_cols}
    for cand in candidatos:
        if _limpiar_col(cand) in cols_limpias:
            return cols_limpias[_limpiar_col(cand)]
    return None
 
 
def _normalizar_hora(valor) -> str:
    if pd.isna(valor):
        return "08:00"
    if isinstance(valor, float) and valor < 1:
        total = int(round(valor * 24 * 60))
        return f"{total // 60:02d}:{total % 60:02d}"
    if hasattr(valor, "hour"):
        return f"{valor.hour:02d}:{valor.minute:02d}"
    s  = str(valor).strip().upper()
    pm = "PM" in s
    s  = s.replace("AM","").replace("PM","").strip()
    try:
        partes = s.split(":")
        h = int(partes[0])
        m = int(partes[1]) if len(partes) > 1 else 0
        if pm and h != 12:
            h += 12
        return f"{h:02d}:{m:02d}"
    except Exception:
        return "08:00"
 
 
def _normalizar_vehiculo(valor) -> str:
    if pd.isna(valor):
        return "Camioneta"
    s = str(valor).strip().lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")]:
        s = s.replace(a, b)
    if any(t in s for t in ["trailer","truck","pesado","tractor"]):
        return "Trailer"
    if any(t in s for t in ["camioneta","van","pickup","pick up","suv"]):
        return "Camioneta"
    if any(t in s for t in ["carro","car","auto","sedan","ligero"]):
        return "Carro"
    return "Camioneta"
 
 
def parsear_excel(
    archivo,
    tipo_vehiculo_global: str = "Camioneta"
) -> tuple[pd.DataFrame, list[str]]:
    """
    Lee un Excel de cualquier estructura y devuelve (df_normalizado, advertencias).
 
    Detecta automáticamente:
      - En qué fila están los headers reales (ignora títulos decorativos)
      - Qué columna es la dirección, cliente, ventanas, etc.
      - El tipo de vehículo (o usa el del sidebar si no existe)
    """
    advertencias: list[str] = []
 
    # 1. Detectar fila de headers
    try:
        fila_header = _detectar_fila_header(archivo)
        df_raw = pd.read_excel(archivo, header=fila_header)
        archivo.seek(0)
    except Exception as e:
        raise ExcelParserError(f"No se pudo leer el Excel: {e}")
 
    if df_raw.empty:
        raise ExcelParserError("El archivo Excel está vacío.")
 
    # Limpiar columnas Unnamed que genera pandas cuando hay celdas vacías
    df_raw = df_raw.loc[:, ~df_raw.columns.str.startswith("Unnamed")]
    df_raw = df_raw.dropna(how="all")  # quitar filas completamente vacías
 
    cols = df_raw.columns.tolist()
    mapa = {campo: _detectar_columna(cols, sins) for campo, sins in SINONIMOS.items()}
 
    logger.info(f"Columnas detectadas: { {k: v for k, v in mapa.items() if v} }")
 
    # 2. Columna de dirección obligatoria
    if not mapa["direccion_raw"]:
        raise ExcelParserError(
            "No se encontró columna de dirección. "
            f"Nombres aceptados: {SINONIMOS['direccion_raw'][:6]}..."
        )
 
    # 3. Límite de paradas
    n_filas = len(df_raw.dropna(subset=[mapa["direccion_raw"]]))
    if n_filas > MAX_PARADAS:
        partes   = -(-n_filas // MAX_PARADAS)
        por_parte = -(-n_filas // partes)
        raise ExcelParserError(
            f"El Excel tiene {n_filas} paradas pero el máximo por corrida es {MAX_PARADAS} "
            f"(límite de la API de tráfico). "
            f"Divide el archivo en {partes} partes de ~{por_parte} filas "
            f"y ejecuta una corrida por cada parte."
        )
 
    # 4. Construcción del DataFrame normalizado
    df = pd.DataFrame()
 
    df["id"] = (
        df_raw[mapa["id"]].astype(str).str.strip()
        if mapa["id"]
        else [f"PED-{i+1:03d}" for i in range(len(df_raw))]
    )
    df["direccion_raw"] = df_raw[mapa["direccion_raw"]].astype(str).str.strip()
    df["cliente"] = (
        df_raw[mapa["cliente"]].astype(str).str.strip()
        if mapa["cliente"] else df["id"]
    )
    df["ventana_inicio"] = (
        df_raw[mapa["ventana_inicio"]].apply(_normalizar_hora)
        if mapa["ventana_inicio"] else "08:00"
    )
    df["ventana_fin"] = (
        df_raw[mapa["ventana_fin"]].apply(_normalizar_hora)
        if mapa["ventana_fin"] else "18:00"
    )
 
    # Tipo de vehículo
    if mapa["tipo_vehiculo"]:
        df["tipo_vehiculo"] = df_raw[mapa["tipo_vehiculo"]].apply(_normalizar_vehiculo)
        tipos_unicos = df["tipo_vehiculo"].unique().tolist()
        if len(tipos_unicos) > 1:
            advertencias.append(
                f"⚠️ El Excel mezcla tipos de vehículo: {tipos_unicos}. "
                f"Se recomienda un Excel por tipo. "
                f"Se procesará todo como '{tipo_vehiculo_global}'."
            )
            df["tipo_vehiculo"] = tipo_vehiculo_global
        elif tipos_unicos[0] != tipo_vehiculo_global:
            advertencias.append(
                f"ℹ️ El Excel indica '{tipos_unicos[0]}' pero seleccionaste "
                f"'{tipo_vehiculo_global}'. Se usará '{tipo_vehiculo_global}'."
            )
            df["tipo_vehiculo"] = tipo_vehiculo_global
    else:
        df["tipo_vehiculo"] = tipo_vehiculo_global
 
    df["peso_kg"] = (
        pd.to_numeric(df_raw[mapa["peso_kg"]], errors="coerce").fillna(0.0)
        if mapa["peso_kg"] else 0.0
    )
    df["volumen_m3"] = (
        pd.to_numeric(df_raw[mapa["volumen_m3"]], errors="coerce").fillna(0.0)
        if mapa["volumen_m3"] else 0.0
    )
    df["notas"] = (
        df_raw[mapa["notas"]].astype(str).str.strip()
        if mapa["notas"] else ""
    )
 
    df = df[df["direccion_raw"].str.lower() != "nan"].reset_index(drop=True)
    logger.info(f"Parser: {len(df)} pedidos — tipo '{tipo_vehiculo_global}' — header en fila {fila_header}.")
    return df, advertencias