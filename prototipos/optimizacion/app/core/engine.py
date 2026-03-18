"""
app/core/engine.py  — Orquestador maestro
 
CAMBIO: math_engine ahora devuelve (texto, detalle_ruta, orden_indices).
El DataFrame final incluye columnas de tiempos reales calculados por OR-Tools.
"""
 
import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
 
from app.services.diagnostico_express import parsear_excel, ExcelParserError
from app.services.claude_service import estandarizar_direcciones
from app.services.geo_engine import obtener_coordenadas, obtener_matriz_tiempos, calcular_ruta_trailer
from app.services.math_engine import resolver_ruta_con_horarios
 
logger = logging.getLogger("Orquestador")
 
HORA_BASE = "06:00"
 
 
@dataclass
class PipelineStep:
    nombre:  str
    ok:      bool
    mensaje: str
    detalle: Optional[str] = None
 
 
@dataclass
class OptimizationResult:
    exito:             bool
    error:             Optional[str]           = None
    pasos:             list[PipelineStep]       = field(default_factory=list)
    df_normalizado:    Optional[pd.DataFrame]  = None
    df_con_coords:     Optional[pd.DataFrame]  = None
    df_ordenado:       Optional[pd.DataFrame]  = None   # ← incluye tiempos reales
    ruta_texto:        Optional[str]           = None
    detalle_ruta:      list[dict]              = field(default_factory=list)
    orden_indices:     list[int]               = field(default_factory=list)
    ruta_trailer:      Optional[dict]          = None
    tipo_vehiculo:     Optional[str]           = None
    n_entregas:        int                     = 0
    n_fallidas_geo:    int                     = 0
    advertencias:      list[str]               = field(default_factory=list)
 
 
def _hora_a_minutos(hora_str) -> int:
    try:
        if isinstance(hora_str, float):
            total = int(hora_str * 24 * 60)
        else:
            h, m = map(int, str(hora_str).strip().split(":"))
            total = h * 60 + m
        hb, mb = map(int, HORA_BASE.split(":"))
        return max(0, total - (hb * 60 + mb))
    except Exception:
        return 0
 
 
def ejecutar_pipeline(
    archivo,
    tipo_vehiculo_ui: str,
    peso_toneladas:   float,
    altura_metros:    float,
    depot_direccion:  str,
) -> OptimizationResult:
 
    result = OptimizationResult(exito=False, tipo_vehiculo=tipo_vehiculo_ui)
 
    # ── FASE 0: Pandas ────────────────────────────────────────────────────────
    logger.info("── FASE 0: Pandas ──")
    try:
        df, adv = parsear_excel(archivo, tipo_vehiculo_global=tipo_vehiculo_ui)
        result.advertencias.extend(adv)
    except ExcelParserError as e:
        result.error = str(e)
        result.pasos.append(PipelineStep("Pandas Parser", False, str(e)))
        return result
    except Exception as e:
        msg = f"Error inesperado al leer el Excel: {e}"
        result.error = msg
        result.pasos.append(PipelineStep("Pandas Parser", False, msg))
        return result
 
    result.df_normalizado = df.copy()
    result.n_entregas     = len(df)
    result.pasos.append(PipelineStep(
        "Pandas Parser", True,
        f"{len(df)} pedidos detectados para {tipo_vehiculo_ui}",
        "Columnas mapeadas: id, direccion, cliente, ventana_inicio/fin, tipo_vehiculo"
    ))
 
    if df.empty:
        result.error = "No hay pedidos válidos en el archivo."
        result.pasos.append(PipelineStep("Pandas Parser", False, result.error))
        return result
 
    # ── FASE 1: Claude ────────────────────────────────────────────────────────
    logger.info("── FASE 1: Claude ──")
    dict_dir = {"DEPOT": depot_direccion}
    dict_dir.update(df.set_index("id")["direccion_raw"].astype(str).to_dict())
 
    direcciones_limpias = estandarizar_direcciones(dict_dir)
    if not direcciones_limpias:
        result.error = "Claude no pudo estandarizar las direcciones."
        result.pasos.append(PipelineStep("Claude AI", False, result.error))
        return result
 
    mapa_dir = {d["id_original"]: d["direccion_completa"] for d in direcciones_limpias}
    df["direccion_limpia"] = df["id"].map(mapa_dir)
    depot_limpio = mapa_dir.get("DEPOT", depot_direccion)
 
    revision = [d["id_original"] for d in direcciones_limpias if d.get("requiere_revision_manual")]
    if revision:
        result.advertencias.append(f"Direcciones con baja confianza (revisar): {revision}")
 
    result.pasos.append(PipelineStep(
        "Claude AI", True,
        f"{len(direcciones_limpias)} direcciones estandarizadas",
        f"Requieren revisión: {revision or 'ninguna'}"
    ))
 
    # ── FASE 2: Mapbox Geocoding ──────────────────────────────────────────────
    logger.info("── FASE 2: Geocoding ──")
    coords_depot = obtener_coordenadas(depot_limpio)
    if not coords_depot:
        result.error = f"No se pudo geolocalizar el depósito: '{depot_limpio}'"
        result.pasos.append(PipelineStep("Mapbox Geocoding", False, result.error))
        return result
 
    coordenadas     = [coords_depot]
    nombres         = ["🏢 Base / Depósito"]
    indices_validos = []
    fallos_geo      = []
 
    for idx, row in df.iterrows():
        dir_buscar = row.get("direccion_limpia") or row["direccion_raw"]
        coords = obtener_coordenadas(str(dir_buscar))
        if coords:
            coordenadas.append(coords)
            nombres.append(str(row["cliente"]))
            indices_validos.append(idx)
        else:
            fallos_geo.append(str(row["id"]))
            result.advertencias.append(f"Sin coordenadas para {row['id']} — omitido.")
 
    result.n_fallidas_geo = len(fallos_geo)
 
    if len(coordenadas) < 2:
        result.error = "Menos de 2 puntos geocodificados."
        result.pasos.append(PipelineStep("Mapbox Geocoding", False, result.error))
        return result
 
    df_geo = df.loc[indices_validos].copy()
    df_geo["lat"] = [c["lat"] for c in coordenadas[1:]]
    df_geo["lng"] = [c["lng"] for c in coordenadas[1:]]
    result.df_con_coords = df_geo
 
    result.pasos.append(PipelineStep(
        "Mapbox Geocoding", True,
        f"{len(coordenadas)} puntos geolocalizados ({len(fallos_geo)} omitidos)",
        f"Fallos: {fallos_geo or 'ninguno'}"
    ))
 
    # ── FASE 3: Mapbox Matrix ─────────────────────────────────────────────────
    logger.info("── FASE 3: Matrix ──")
    matriz = obtener_matriz_tiempos(coordenadas)
    if not matriz:
        result.error = "No se pudo calcular la matriz de tiempos de Mapbox."
        result.pasos.append(PipelineStep("Mapbox Matrix", False, result.error))
        return result
 
    result.pasos.append(PipelineStep(
        "Mapbox Matrix", True,
        f"Matriz {len(matriz)}×{len(matriz[0])} con tiempos reales de tráfico"
    ))
 
    if tipo_vehiculo_ui == "Trailer":
        ruta_trailer = calcular_ruta_trailer(coordenadas, peso_toneladas, altura_metros)
        if ruta_trailer:
            result.ruta_trailer = ruta_trailer
            result.pasos.append(PipelineStep(
                "Mapbox Trailer Route", True,
                f"{ruta_trailer['distancia_total_km']} km en {ruta_trailer['tiempo_estimado_minutos']} min",
                ruta_trailer["restricciones_aplicadas"]
            ))
        else:
            result.advertencias.append("Mapbox no calculó ruta con restricciones de Trailer. Se usará ruta estándar.")
 
    # ── FASE 4: OR-Tools ──────────────────────────────────────────────────────
    logger.info("── FASE 4: OR-Tools ──")
 
    ventanas = [(0, 999)]
    for _, row in df_geo.iterrows():
        inicio = _hora_a_minutos(row.get("ventana_inicio", "08:00"))
        fin    = _hora_a_minutos(row.get("ventana_fin",    "18:00"))
        if fin <= inicio:
            fin = inicio + 120
        ventanas.append((inicio, fin))
 
    tiempos_servicio = [0]
    for _, row in df_geo.iterrows():
        peso  = float(row.get("peso_kg", 0) or 0)
        notas = str(row.get("notas", "")).lower()
 
        if tipo_vehiculo_ui == "Carro":
            # Paquetería ligera: siempre 10 min, sin variación
            t = 10
 
        elif tipo_vehiculo_ui == "Camioneta":
            # Carga media: 20 min base + 5 si hay peso significativo
            t = 20
            if peso > 200:
                t += 5
 
        else:  # Trailer
            # Carga pesada: 60 min base
            t = 60
            if peso > 2000:
                t += 15   # descarga más lenta
            if any(kw in notas for kw in ["grúa", "grua", "rampa", "montacargas", "transpaleta"]):
                t += 15   # requiere equipo especial
 
        tiempos_servicio.append(t)
 
    data_ortools = {
        "time_matrix":   matriz,
        "time_windows":  ventanas,
        "service_times": tiempos_servicio,
        "num_vehicles":  1,
        "depot":         0,
    }
 
    # NUEVO: math_engine devuelve (texto, detalle_ruta, orden_indices)
    ruta_texto, detalle_ruta, orden_indices = resolver_ruta_con_horarios(data_ortools, nombres)
 
    if "No se encontró" in str(ruta_texto) or "Error" in str(ruta_texto):
        result.error = ruta_texto
        result.pasos.append(PipelineStep("OR-Tools", False, str(ruta_texto)))
        return result
 
    # Construir DataFrame de resultados con tiempos reales inyectados
    if orden_indices and detalle_ruta:
        df_ordenado = df_geo.iloc[orden_indices].copy().reset_index(drop=True)
        df_ordenado.insert(0, "orden_entrega", range(1, len(df_ordenado) + 1))
 
        # Inyectar columnas calculadas por OR-Tools
        df_ordenado["⏰ llegada_estimada"] = [d["llegada_estimada"]    for d in detalle_ruta]
        df_ordenado["⏱️ traslado_min"]    = [d["⏱️ traslado_min"]     for d in detalle_ruta]
        df_ordenado["⏳ espera_min"]       = [d["⏳ espera_min"]        for d in detalle_ruta]
        df_ordenado["📦 descarga_min"]    = [d["📦 descarga_min"]      for d in detalle_ruta]
        df_ordenado["🚪 salida_estimada"] = [d["salida_estimada"]      for d in detalle_ruta]
        df_ordenado["✅ ventana_ok"]      = [
            "✅" if d["ventana_inicio"] <= d["llegada_estimada"] <= d["ventana_fin"]
            else "⚠️ FUERA"
            for d in detalle_ruta
        ]
    else:
        df_ordenado = df_geo.copy()
 
    result.pasos.append(PipelineStep(
        "OR-Tools VRPTW", True,
        f"Ruta óptima para {len(df_ordenado)} entregas calculada",
        f"Ver columnas ⏰llegada_estimada y 🚪salida_estimada en la tabla"
    ))
 
    result.exito         = True
    result.ruta_texto    = ruta_texto
    result.detalle_ruta  = detalle_ruta
    result.orden_indices = orden_indices
    result.df_ordenado   = df_ordenado
 
    logger.info(f"Pipeline completado — {len(df_ordenado)} entregas optimizadas.")
    return result