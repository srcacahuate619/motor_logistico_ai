"""
SERVICIO: Generador de Reportes Financieros y ROI
PROPÓSITO: Calcular la diferencia (Delta) de tiempo y diésel entre la ruta humana 
y la ruta IA para crear el reporte PDF de consultoría para Don Alfredo.
"""
#he aquí el "contador" de la fabrica: compara realidad humana vs optimizacion IA 
#captura 2 datos JSON, data historica (lo que hizo el chofer hoy) y data IA (lo que el motor calculó como ruta perfecta)
#diferencia de distancia (km IA - km humano x costo/km)
#diferencia de tiempo (horas IA - horas humano x costo/hora)
#probabilidad de multa usando la ruta humana vs ruta IA
#genera 2 metricas: el ahorro proyectado mensual (ahorro del día x 30) y el puntaje de eficiencia del chofer (para el bono o penalización)
