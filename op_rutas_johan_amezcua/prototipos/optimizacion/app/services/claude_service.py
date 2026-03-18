import os
import json
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
import anthropic
from pydantic import BaseModel, ValidationError
#CONFIGURACIÓN DE LOGGING PARA PRODUCCIÓN
# En producción no usamos print(). Usamos logs que guardan la hora y el nivel de gravedad.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ClaudeService")
# Soporta Streamlit Cloud (st.secrets) y local (.env)
try:
    import streamlit as st
    API_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not API_KEY:
    logger.error("CRÍTICO: No se encontró ANTHROPIC_API_KEY.")
    raise ValueError("Falta ANTHROPIC_API_KEY en st.secrets o en .env")

client = anthropic.Anthropic(api_key=API_KEY)
#CARGA DE VARIABLES DE ENTORNO
#Esto lee el archivo .env de forma segura
load_dotenv()
API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    logger.error("CRÍTICO: No se encontró ANTHROPIC_API_KEY en las variables de entorno.")
    raise ValueError("Falta ANTHROPIC_API_KEY en el archivo .env")
# Instancia global del cliente
client = anthropic.Anthropic(api_key=API_KEY)
#VALIDACIÓN ESTRICTA CON PYDANTIC (El escudo de seguridad)
# Obligamos a que la respuesta tenga EXACTAMENTE esta forma. 
# Si Claude omite un dato, Pydantic lanza una alarma estructurada.
class DireccionLimpia(BaseModel):
    id_original: str
    calle_y_numero: str
    colonia: str
    municipio: str
    estado: str
    codigo_postal: str
    direccion_completa: str
    requiere_revision_manual: bool
class RespuestaClaude(BaseModel):
    direcciones: List[DireccionLimpia]
#LA LÓGICA DE NEGOCIO
def estandarizar_direcciones(direcciones_sucias: Dict[str, str]) -> List[Dict]:
    """
    Toma un diccionario de {id: direccion_sucia} y devuelve direcciones validadas.
    Usa Pydantic para garantizar la integridad de los datos de salida.
    """
    logger.info(f"Iniciando procesamiento de {len(direcciones_sucias)} direcciones con Claude AI.")
    
    prompt_sistema = """
    Eres un motor logístico estricto. Recibes un JSON con IDs y direcciones caóticas de México.
    Debes estructurarlas y devolver ÚNICAMENTE un objeto JSON con el siguiente formato exacto:
    {
      "direcciones": [
        {
          "id_original": "el ID que recibiste",
          "calle_y_numero": "Calle y número exterior/interior",
          "colonia": "Nombre de la colonia",
          "municipio": "Municipio o delegación",
          "estado": "Estado de la república",
          "codigo_postal": "CP a 5 dígitos si existe, o vacío",
          "direccion_completa": "La concatenación limpia de todo lo anterior para dársela a Mapbox",
          "requiere_revision_manual": false // Pon true SOLO si la dirección original es jerga incomprensible (ej. 'donde el perro ladra')
        }
      ]
    }
    No agregues texto en formato Markdown, no saludes. Responde estrictamente con el JSON.
    """

    mensaje_usuario = json.dumps(direcciones_sucias, ensure_ascii=False)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            temperature=0.0, # 0.0 absoluto para máxima precisión determinista
            system=prompt_sistema,
            messages=[
                {"role": "user", "content": f"Estandariza:\n{mensaje_usuario}"}
            ]
        )
        
        texto_crudo = response.content[0].text.strip()
        #Sanitización defensiva contra Markdown
        if texto_crudo.startswith("```"):
            texto_crudo = texto_crudo.replace("```json", "", 1).replace("```", "").strip()
        #Parseo de JSON
        datos_json = json.loads(texto_crudo) 
        #EL PASO DE ORO: Validación con Pydantic
        # Si Claude se equivocó en el formato, esto fallará limpiamente antes de dañar la base de datos
        datos_validados = RespuestaClaude(**datos_json)
        logger.info("Procesamiento y validación estructural completados con éxito.")     
        # Retornamos los datos como diccionarios de Python listos para Pandas
        return [direccion.model_dump() for direccion in datos_validados.direcciones]
    except json.JSONDecodeError as e:
        logger.error(f"Fallo al decodificar JSON de Claude. Respuesta cruda: {texto_crudo[:100]}...")
        return []
    except ValidationError as e:
        logger.error(f"Claude devolvió un JSON inválido estructuralmente (Pydantic falló):\n{e}")
        return []
    except Exception as e:
        logger.error(f"Error de red o API con Anthropic: {str(e)}")
        return []
# ==========================================
# TEST UNITARIO LOCAL
# ==========================================
if __name__ == "__main__":
    # Simulamos el diccionario que tu script de Pandas le enviará
    payload_prueba = {
        "F001": "calle morelos num 123 col centro mty n.l.",
        "F002": "Atras del oxxo de av constitucion porton gris monterrey",
        "F003": "Paseo de los leones #3456 cumbres 2do sector nl"
    }
    
    resultados = estandarizar_direcciones(payload_prueba)
    
    print("\n--- OUTPUT FINAL PARA PANDAS/MAPBOX ---")
    print(json.dumps(resultados, indent=4, ensure_ascii=False))
