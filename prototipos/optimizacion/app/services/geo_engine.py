import os
import math
import time
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
 
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path, override=True)
 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MapboxEngine")
 
# Soporta tanto Streamlit Cloud (st.secrets) como local (.env)
try:
    import streamlit as st
    MAPBOX_TOKEN = st.secrets.get("MAPBOX_API_KEY") or os.getenv("MAPBOX_API_KEY")
except Exception:
    MAPBOX_TOKEN = os.getenv("MAPBOX_API_KEY")
 
if not MAPBOX_TOKEN:
    logger.error("CRÍTICO: No se encontró MAPBOX_API_KEY en st.secrets ni en .env")
 
# Límite real de la Matrix API de Mapbox (plan gratuito y estándar)
MAPBOX_MATRIX_LIMIT = 10
 
# Bounding box de México — cubre todos los estados del país
# Evita que Mapbox devuelva una colonia homónima en otro país
MEXICO_BBOX = {
    "lat_min": 14.5,    # Chiapas sur
    "lat_max": 32.7,    # Baja California norte
    "lng_min": -118.4,  # Baja California oeste
    "lng_max": -86.7,   # Quintana Roo este
}
 
 
def _dentro_de_mexico(lat: float, lng: float) -> bool:
    return (
        MEXICO_BBOX["lat_min"] <= lat <= MEXICO_BBOX["lat_max"] and
        MEXICO_BBOX["lng_min"] <= lng <= MEXICO_BBOX["lng_max"]
    )
 
 
# ─────────────────────────────────────────────────────────────
# GEOCODING
# ─────────────────────────────────────────────────────────────
 
def obtener_coordenadas(direccion: str) -> Optional[Dict[str, float]]:
    """
    Convierte una dirección de texto a coordenadas usando Mapbox.
    Funciona para cualquier dirección dentro de México (todos los estados).
    Rechaza resultados fuera del bounding box del país.
    """
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.quote(direccion)}.json"
    params = {
        "access_token": MAPBOX_TOKEN,
        "country":      "mx",   # Restringe a México — cualquier estado
        "language":     "es",   # Respuestas en español
        "limit":        1,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
 
        if not data.get("features"):
            logger.warning(f"Sin resultados para: {direccion}")
            return None
 
        coords = data["features"][0]["geometry"]["coordinates"]
        lng, lat = coords[0], coords[1]
 
        if not _dentro_de_mexico(lat, lng):
            logger.warning(
                f"Coordenadas fuera de México para '{direccion}': "
                f"lat={lat:.4f}, lng={lng:.4f} — descartado."
            )
            return None
 
        return {"lng": lng, "lat": lat}
 
    except Exception as e:
        logger.error(f"Error Mapbox Geocoding: {e}")
        return None
 
 
# ─────────────────────────────────────────────────────────────
# MATRIX API  —  con partición en bloques de 10
# ─────────────────────────────────────────────────────────────
 
def _request_matrix(
    coordenadas: List[Dict[str, float]],
    sources: List[int],
    destinations: List[int],
    perfil: str = "driving-traffic",
) -> Optional[List[List[float]]]:
    """
    Hace un único request a la Matrix API de Mapbox.
    Garantiza mínimo 2 puntos únicos añadiendo un vecino si es necesario.
    El caller garantiza que len(set(sources)|set(destinations)) <= MAPBOX_MATRIX_LIMIT.
    """
    indices_unicos = sorted(set(sources) | set(destinations))
 
    # Garantía: Mapbox necesita mínimo 2 coordenadas en el array
    if len(indices_unicos) < 2:
        vecino = next((i for i in range(len(coordenadas)) if i not in set(indices_unicos)), None)
        if vecino is None:
            logger.error("No hay puntos suficientes para construir submatriz.")
            return None
        indices_unicos = sorted(set(indices_unicos) | {vecino})
 
    puntos_usados = [coordenadas[i] for i in indices_unicos]
    remap         = {orig: nuevo for nuevo, orig in enumerate(indices_unicos)}
    src_remap     = [remap[s] for s in sources]
    dst_remap     = [remap[d] for d in destinations]
 
    coords_str = ";".join([f"{c['lng']},{c['lat']}" for c in puntos_usados])
    url    = f"https://api.mapbox.com/directions-matrix/v1/mapbox/{perfil}/{coords_str}"
    params = {
        "access_token": MAPBOX_TOKEN,
        "annotations":  "duration",
        "sources":      ";".join(map(str, src_remap)),
        "destinations": ";".join(map(str, dst_remap)),
    }
 
    try:
        response = requests.get(url, params=params, timeout=15)
        data     = response.json()
        if data.get("code") == "Ok":
            return data["durations"]
        logger.error(f"Mapbox Matrix error: {data.get('code')} — {data.get('message')}")
        return None
    except Exception as e:
        logger.error(f"Error de red en Matrix Mapbox: {e}")
        return None
 
 
def obtener_matriz_tiempos(
    coordenadas: List[Dict[str, float]],
    perfil: str = "driving-traffic",
) -> Optional[List[List[int]]]:
    """
    Devuelve la matriz completa N×N de tiempos en MINUTOS considerando tráfico.
 
    Límite de Mapbox: máximo 10 puntos ÚNICOS (set(sources) | set(destinations)).
    Estrategia: chunk = LIMIT // 2 = 5. Bloques de 5 sources × 5 destinations.
    Máximo posible de únicos por request = 5 + 5 = 10 exacto.
    Si src y dst comparten elementos, los únicos son MENOS — siempre seguro.
    Bloques de tamaño 1 (último bloque impar) se manejan con vecino de relleno en _request_matrix.
    Validado para n = 3, 5, 10, 11, 12, 15, 16, 21, 23.
    """
    n = len(coordenadas)
    if n < 2:
        logger.error("Se necesitan al menos 2 coordenadas.")
        return None
 
    logger.info(f"Calculando matriz {n}×{n} de tiempos de tráfico...")
 
    chunk       = MAPBOX_MATRIX_LIMIT // 2   # 5
    bloques_src = [list(range(i, min(i + chunk, n))) for i in range(0, n, chunk)]
    bloques_dst = [list(range(j, min(j + chunk, n))) for j in range(0, n, chunk)]
 
    # Caso simple: n <= 10, cabe en un solo request
    if n <= MAPBOX_MATRIX_LIMIT:
        resultado = _request_matrix(coordenadas, list(range(n)), list(range(n)), perfil)
        if resultado is None:
            return None
        return [[round(s / 60) for s in fila] for fila in resultado]
 
    # Caso con más de 10 puntos: bloques 5×5
    total = len(bloques_src) * len(bloques_dst)
    logger.info(f"{n} puntos — {total} sub-requests ({len(bloques_src)}×{len(bloques_dst)} bloques de ≤5)")
    matriz = [[0] * n for _ in range(n)]
 
    for src_block in bloques_src:
        for dst_block in bloques_dst:
            unicos = set(src_block) | set(dst_block)
 
            # Si src y dst son idénticos y tienen 1 solo elemento,
            # es la diagonal (distancia de un punto a sí mismo = 0).
            # No necesita consultarse — Mapbox lo rechazaría igual.
            if len(unicos) < 2:
                for i_global in src_block:
                    for j_global in dst_block:
                        matriz[i_global][j_global] = 0
                continue
 
            submatriz = _request_matrix(coordenadas, src_block, dst_block, perfil)
 
            if submatriz is None:
                logger.error(f"Falló sub-request sources={src_block} destinations={dst_block}")
                return None
 
            for i_local, i_global in enumerate(src_block):
                for j_local, j_global in enumerate(dst_block):
                    matriz[i_global][j_global] = round(submatriz[i_local][j_local] / 60)
 
            time.sleep(0.15)
 
    logger.info("Matriz completa reconstruida.")
    return matriz
 
 
# ─────────────────────────────────────────────────────────────
# RUTA CON RESTRICCIONES FÍSICAS PARA TRÁILER
# ─────────────────────────────────────────────────────────────
 
def calcular_ruta_trailer(
    coordenadas: List[Dict[str, float]],
    peso_toneladas: float,
    altura_metros: float,
) -> Optional[Dict[str, Any]]:
    """
    Calcula la ruta para un tráiler evitando puentes bajos y vías con
    restricción de peso. Usa el perfil driving-traffic de Mapbox.
    """
    logger.info(f"Calculando ruta tráiler ({peso_toneladas}T / {altura_metros}m) — {len(coordenadas)} puntos")
 
    # Mapbox Directions acepta máximo 25 waypoints
    if len(coordenadas) > 25:
        logger.warning("Más de 25 puntos — Mapbox Directions solo acepta 25. Se usarán los primeros 25.")
        coordenadas = coordenadas[:25]
 
    coords_str = ";".join([f"{c['lng']},{c['lat']}" for c in coordenadas])
    url    = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords_str}"
    params = {
        "access_token": MAPBOX_TOKEN,
        "geometries":   "geojson",
        "max_weight":   peso_toneladas,
        "max_height":   altura_metros,
    }
 
    try:
        response = requests.get(url, params=params, timeout=15)
        data     = response.json()
 
        if data.get("code") != "Ok":
            logger.error(f"Mapbox Directions error: {data.get('message')}")
            return None
 
        ruta = data["routes"][0]
        return {
            "distancia_total_km":       round(ruta["distance"] / 1000, 2),
            "tiempo_estimado_minutos":  round(ruta["duration"] / 60, 2),
            "restricciones_aplicadas":  f"Tráiler {peso_toneladas}T / {altura_metros}m altura",
        }
    except Exception as e:
        logger.error(f"Error crítico en ruta tráiler: {e}")
        return None
 