"""
app/services/math_engine.py
 
FIX: resolver_ruta_con_horarios ahora devuelve:
  - texto legible con horas reales HH:MM
  - lista de dicts con llegada_estimada, salida_estimada, tiempo_descarga por parada
  - orden_indices para reordenar el DataFrame
"""
 
import logging
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
 
logger = logging.getLogger("OR-Tools-Engine")
 
HORA_BASE = "06:00"   # debe coincidir con el valor en engine.py
 
 
def _minutos_a_hhmm(minutos: int, hora_base: str = HORA_BASE) -> str:
    """Convierte minutos desde hora_base a string HH:MM legible."""
    hb, mb = map(int, hora_base.split(":"))
    total  = hb * 60 + mb + minutos
    total  = max(0, total)
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"
 
 
def crear_modelo_de_datos() -> dict:
    """Estructura vacía para tests unitarios."""
    return {
        "time_matrix":   [],
        "time_windows":  [],
        "service_times": [],
        "num_vehicles":  1,
        "depot":         0,
    }
 
 
def resolver_ruta_con_horarios(
    data: dict,
    nombres_paradas: list[str],
) -> tuple[str, list[dict], list[int]]:
    """
    Resuelve el problema VRPTW y devuelve tiempos REALES de llegada.
 
    Returns:
        texto_ruta   : str  — resumen legible para mostrar en pantalla
        detalle_ruta : list[dict] — una entrada por parada con:
                          nombre, llegada_hhmm, salida_hhmm,
                          tiempo_descarga_min, ventana_inicio_hhmm, ventana_fin_hhmm
        orden_indices: list[int] — índices 0-based en df_trabajo (sin depósito)
    """
    n = len(data.get("time_matrix", []))
    if n < 2:
        return "Error: matriz de tiempos vacía.", [], []
 
    if len(data.get("time_windows", [])) != n:
        return f"Error: time_windows tiene {len(data['time_windows'])} entradas pero la matriz tiene {n}.", [], []
 
    if len(data.get("service_times", [])) != n:
        data["service_times"] = [0] + [15] * (n - 1)
        logger.warning("service_times rellenado con 15 min por defecto.")
 
    logger.info(f"OR-Tools: {n} nodos, {data['num_vehicles']} vehículo(s)...")
 
    manager = pywrapcp.RoutingIndexManager(n, data["num_vehicles"], data["depot"])
    routing = pywrapcp.RoutingModel(manager)
 
    def time_callback(from_idx, to_idx):
        fn = manager.IndexToNode(from_idx)
        tn = manager.IndexToNode(to_idx)
        return data["time_matrix"][fn][tn] + data["service_times"][fn]
 
    cb_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cb_index)
 
    routing.AddDimension(cb_index, 60, 1440, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
 
    for node_idx, (open_t, close_t) in enumerate(data["time_windows"]):
        if node_idx == data["depot"]:
            continue
        idx = manager.NodeToIndex(node_idx)
        time_dim.CumulVar(idx).SetRange(open_t, close_t)
 
    depot_idx = manager.NodeToIndex(data["depot"])
    dw_open, dw_close = data["time_windows"][data["depot"]]
    time_dim.CumulVar(depot_idx).SetRange(dw_open, dw_close)
    routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.Start(0)))
    routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(0)))
 
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = 10
 
    solution = routing.SolveWithParameters(params)
    if not solution:
        return "No se encontró solución: imposible cumplir todos los horarios.", [], []
 
    return _formatear_solucion(data, manager, routing, solution, time_dim, nombres_paradas)
 
 
def _formatear_solucion(
    data, manager, routing, solution, time_dim, nombres_paradas
) -> tuple[str, list[dict], list[int]]:
    """
    Extrae tiempos reales de OR-Tools y los convierte a HH:MM.
    Calcula llegada, tiempo de descarga y salida por cada parada.
    """
    index        = routing.Start(0)
    texto        = "📍 RUTA ÓPTIMA — TIEMPOS REALES DE LLEGADA\n" + "─" * 50 + "\n"
    detalle      = []
    orden        = []
    parada_num   = 1
 
    prev_salida_min = solution.Min(time_dim.CumulVar(routing.Start(0)))
 
    while not routing.IsEnd(index):
        node         = manager.IndexToNode(index)
        t_var        = time_dim.CumulVar(index)
        llegada_min  = solution.Min(t_var)
        descarga_min = data["service_times"][node]
        salida_min   = llegada_min + descarga_min
 
        llegada_hhmm = _minutos_a_hhmm(llegada_min)
        salida_hhmm  = _minutos_a_hhmm(salida_min)
 
        ventana  = data["time_windows"][node]
        v_inicio = _minutos_a_hhmm(ventana[0])
        v_fin    = _minutos_a_hhmm(ventana[1])
 
        nombre = nombres_paradas[node] if node < len(nombres_paradas) else f"Nodo {node}"
 
        if node == data["depot"]:
            texto += f"🏢 SALIDA BASE        → {llegada_hhmm}\n"
            texto += "─" * 50 + "\n"
            prev_salida_min = salida_min
        else:
            # OR-Tools incluye la espera dentro de llegada_min.
            # traslado_puro = tiempo real de conducción (llegada - salida anterior)
            # espera_min    = tiempo que el chofer espera si llega antes de que abra
            traslado_puro = max(0, llegada_min - prev_salida_min)
            espera_min    = max(0, ventana[0] - (prev_salida_min + traslado_puro))
 
            texto += (
                f"  {parada_num:>2}. {nombre}\n"
                f"      Llega:    {llegada_hhmm}  "
                f"(ventana: {v_inicio} – {v_fin})\n"
                f"      Traslado: {traslado_puro}min"
                + (f"  |  Espera: {espera_min}min" if espera_min > 0 else "")
                + f"  |  Descarga: {descarga_min}min  →  Sale: {salida_hhmm}\n\n"
            )
            detalle.append({
                "parada":              parada_num,
                "nombre":              nombre,
                "llegada_estimada":    llegada_hhmm,
                "salida_estimada":     salida_hhmm,
                "⏱️ traslado_min":     traslado_puro,
                "⏳ espera_min":       espera_min,
                "📦 descarga_min":     descarga_min,
                "ventana_inicio":      v_inicio,
                "ventana_fin":         v_fin,
            })
            orden.append(node - 1)
            parada_num      += 1
            prev_salida_min  = salida_min
 
        index = solution.Value(routing.NextVar(index))
 
    # Nodo final — regreso al depósito
    end_var      = time_dim.CumulVar(index)
    regreso_min  = solution.Min(end_var)
    regreso_hhmm = _minutos_a_hhmm(regreso_min)
    texto += "─" * 50 + "\n"
    texto += f"🏁 REGRESO A BASE     → {regreso_hhmm}\n"
 
    duracion_total = regreso_min - solution.Min(time_dim.CumulVar(routing.Start(0)))
    texto += f"⏱️  Duración total de la ruta: {duracion_total} min ({duracion_total/60:.1f} h)\n"
 
    return texto, detalle, orden
 