# 🚚 Motor de Logística & Optimización de Rutas con IA

> **Automatiza en segundos lo que tu despachador tarda 2 horas en hacer a mano.**  
> Sube tu Excel de entregas — sin importar qué tan desordenado esté — y obtén la ruta óptima con tiempos reales de llegada, ventanas de entrega respetadas y restricciones físicas por tipo de vehículo.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Claude AI](https://img.shields.io/badge/Claude_AI-Anthropic-D97706?style=flat)](https://anthropic.com)
[![Mapbox](https://img.shields.io/badge/Mapbox-API-000000?style=flat&logo=mapbox&logoColor=white)](https://mapbox.com)
[![OR-Tools](https://img.shields.io/badge/Google_OR--Tools-VRPTW-4285F4?style=flat&logo=google&logoColor=white)](https://developers.google.com/optimization)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ¿Para quién es esto?

Para **pequeñas y medianas empresas** de distribución, mensajería, reparto de alimentos, productos farmacéuticos, materiales de construcción o cualquier operación que tenga que mover mercancía de punto A a punto B todos los días.

Si tu proceso actual se parece a esto:

> *"El despachador llega, abre el Excel con los pedidos del día, hace cuentas a mano, busca las direcciones en Google Maps una por una y arma la hoja de ruta en 1-2 horas"*

Este motor lo hace **en menos de 60 segundos.**

---

## ¿Qué problema resuelve?

| Sin el motor | Con el motor |
|---|---|
| Rutas armadas a intuición | Ruta matemáticamente óptima |
| Sin considerar horarios de entrega | Ventanas de tiempo respetadas al minuto |
| Google Maps para cada dirección | Geocodificación automática en bloque |
| El chofer se pierde en direcciones mal escritas | Direcciones normalizadas con IA antes de geolocalizar |
| El trailer toma rutas con puentes bajos | Restricciones de peso y altura aplicadas automáticamente |
| Resultado: 2 horas de trabajo manual | Resultado: 60 segundos, Excel descargable listo para el chofer |

---

## Demo en vivo

🔗 **[motor-logistico-ai.streamlit.app](https://motor-logistico-ai.streamlit.app)** ← pruébalo con los Excels de ejemplo

---

## Cómo funciona — El pipeline de 4 pasos

```
Excel caótico de la empresa
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  PASO 1 — PANDAS                                    │
│  Detecta automáticamente las columnas del Excel     │
│  sin importar su estructura, idioma o formato       │
│  "address", "domicilio", "dirección" → todo vale   │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  PASO 2 — CLAUDE AI (Anthropic)                     │
│  Estandariza direcciones caóticas                   │
│  "atras del oxxo de constitucion portón gris mty"  │
│           ↓                                         │
│  "Av. Constitución 1200, Col. Centro, Monterrey"   │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  PASO 3 — MAPBOX API                                │
│  · Geocodifica cada dirección (lat/lng)             │
│  · Calcula matriz de tiempos con TRÁFICO REAL       │
│  · Para Trailers: evita puentes bajos y vías con    │
│    restricción de peso (max_weight / max_height)    │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  PASO 4 — GOOGLE OR-TOOLS (VRPTW)                   │
│  Resuelve el problema matemático de ruteo con       │
│  ventanas de tiempo — encuentra la secuencia que    │
│  minimiza distancia respetando TODOS los horarios   │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
         Ruta óptima con tiempos reales
         de llegada, traslado y descarga
         Lista para darle al chofer
```

---

## Resultado que genera el motor

El Excel de salida incluye por cada parada:

| Campo | Descripción |
|---|---|
| `orden_entrega` | Secuencia óptima calculada por OR-Tools |
| `⏰ llegada_estimada` | Hora real de llegada (HH:MM) con tráfico |
| `⏱️ traslado_min` | Minutos de conducción desde la parada anterior |
| `⏳ espera_min` | Tiempo que espera el chofer si llega antes de que abra |
| `📦 descarga_min` | Tiempo de descarga calculado por peso y tipo de vehículo |
| `🚪 salida_estimada` | Hora de salida hacia la siguiente parada |
| `✅ ventana_ok` | Confirmación de que la ventana de entrega fue respetada |
| `direccion_limpia` | Dirección normalizada por Claude AI |
| `lat / lng` | Coordenadas geocodificadas por Mapbox |

---

## Tiempos de descarga por tipo de vehículo

El motor calcula automáticamente el tiempo de servicio según el vehículo y la carga:

| Vehículo | Tiempo base | Ajuste automático |
|---|---|---|
| 🚗 Carro | 10 min | Fijo — paquetería ligera |
| 🚐 Camioneta | 20 min | +5 min si peso > 200 kg |
| 🚛 Trailer | 60 min | +15 min si peso > 2,000 kg · +15 min si las notas mencionan grúa, rampa o transpaleta |

---

## Estructura del proyecto

```
motor-logistico-ai/
│
├── app_frontend.py              # UI Streamlit — solo presentación
│
├── app/
│   ├── core/
│   │   └── engine.py            # Orquestador maestro del pipeline
│   │
│   └── services/
│       ├── excel_parser.py      # Pandas — detecta cualquier estructura de Excel
│       ├── claude_service.py    # Claude AI — estandarización de direcciones
│       ├── geo_engine.py        # Mapbox — geocoding + matriz de tiempos
│       └── math_engine.py       # OR-Tools — optimización VRPTW
│
├── excels_de_prueba/
│   ├── rutas_CARROS.xlsx        # 12 entregas en carro (columnas en inglés, horas AM/PM)
│   ├── rutas_CAMIONETAS.xlsx    # 12 entregas en camioneta (columnas tipo ERP legacy)
│   └── rutas_TRAILERS_v2.xlsx   # 6 entregas en trailer (sin columna de vehículo)
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Cómo usar el motor

### Opción A — Demo pública (sin instalar nada)
Ve a **[motor-logistico-ai.streamlit.app](https://motor-logistico-ai.streamlit.app)** y sube uno de los Excels de prueba de la carpeta `excels_de_prueba/`.

### Opción B — Instalación local

**1. Clona el repositorio**
```bash
git clone https://github.com/srcacahuate619/motor_logistico_ai.git
cd motor_logistico_ai
```

**2. Crea el entorno virtual e instala dependencias**
```bash
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

**3. Configura tus API keys**

Crea el archivo `.env` en la raíz:
```env
ANTHROPIC_API_KEY=sk-ant-...
MAPBOX_API_KEY=pk.eyJ...
```

Necesitas:
- API key de [Anthropic Console](https://console.anthropic.com) (Claude)
- Token de [Mapbox](https://account.mapbox.com) (geocoding + matrix + directions)

**4. Corre la aplicación**
```bash
streamlit run app_frontend.py
```

---

## Formato del Excel de entrada

**Columna obligatoria:**

| Columna | Nombres aceptados |
|---|---|
| Dirección | `direccion`, `domicilio`, `address`, `calle`, `destino`, `ubicacion` |

**Columnas opcionales** — el motor las detecta automáticamente:

| Columna | Nombres aceptados | Default |
|---|---|---|
| ID | `id`, `folio`, `pedido`, `orden`, `referencia`, `order` | Auto-generado |
| Cliente | `cliente`, `nombre`, `destinatario`, `customer`, `name` | Usa el ID |
| Ventana inicio | `ventana_inicio`, `inicio`, `apertura`, `time_from`, `desde` | 08:00 |
| Ventana fin | `ventana_fin`, `fin`, `cierre`, `time_to`, `hasta` | 18:00 |
| Tipo vehículo | `tipo_vehiculo`, `vehiculo`, `unidad`, `vehicle` | El del sidebar |
| Peso (kg) | `peso_kg`, `peso`, `kg`, `carga_kg`, `weight` | 0 |
| Notas | `notas`, `observaciones`, `instrucciones_especiales` | vacío |

> **Regla importante:** sube **un Excel por tipo de vehículo**. El motor optimiza una flota a la vez — así funciona la logística real.

---

## Limitaciones del MVP

| Límite | Valor | Motivo |
|---|---|---|
| Paradas por corrida | 23 máx | Límite de la Matrix API de Mapbox |
| Filas por Excel (demo) | 50 máx | Protección de créditos de API |
| Vehículos simultáneos | 1 por corrida | Diseño para MVP — CVRP multi-vehículo en roadmap |
| Cobertura geográfica | México | `country=mx` en Mapbox Geocoding |

---

## Roadmap

- [ ] Soporte multi-vehículo en una sola corrida (CVRP)
- [ ] Mapa visual interactivo de la ruta en Streamlit
- [ ] Integración directa con WhatsApp para enviar ruta al chofer
- [ ] Panel de historial de rutas por empresa
- [ ] API REST para integración con sistemas ERP/WMS existentes
- [ ] Soporte para rutas de varios días

---

## Stack tecnológico

| Componente | Tecnología | Rol |
|---|---|---|
| Frontend | Streamlit | Interfaz web sin código |
| Limpieza de datos | Pandas | Normalización de cualquier Excel |
| IA semántica | Claude Sonnet (Anthropic) | Estandarización de direcciones caóticas |
| Geocodificación | Mapbox Geocoding API | Texto → coordenadas |
| Tráfico real | Mapbox Matrix API | Tiempos de viaje entre todos los puntos |
| Rutas por vehículo | Mapbox Directions API | Restricciones físicas de peso y altura |
| Optimización | Google OR-Tools VRPTW | Secuencia óptima con ventanas de tiempo |
| Validación | Pydantic v2 | Integridad de datos de Claude |

---

## Autor

**Johan Amezcua** — [@srcacahuate619](https://github.com/srcacahuate619)

Si este proyecto te parece útil o tienes una empresa que quiere implementarlo, contáctame en [LinkedIn](https://www.linkedin.com/in/johan-amezcua-11816b1bb/).

---

<p align="center">
  Construido con 🧠 Claude AI · 📍 Mapbox · 🔢 Google OR-Tools · 🐍 Python
</p>
