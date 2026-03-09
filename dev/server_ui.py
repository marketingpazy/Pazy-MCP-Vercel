from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from collections import defaultdict
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
from dotenv import load_dotenv
import contextlib
import uvicorn
import json
from starlette.routing import Mount
from starlette.applications import Starlette
from tools.tool_1.subgraph_tool_1 import create_pricing_subgraph
from tools.tool_2_3.rag_store import (
    RagSettings,
    build_or_load_vectorstore,
    retrieve_faq_rag,
    retrieve_brand_rag,
)
from aux_functions import cfg
from users_control import (
    can_user_call_pricing,
    consume_pricing_call,
    get_user_limit_info,
)

load_dotenv()
port = int(cfg("PORT", 8000))

RAG_SETTINGS = RagSettings()
VECTORSTORE = build_or_load_vectorstore(RAG_SETTINGS)
subgraph_pricing = create_pricing_subgraph()

BASE_DIR = Path(__file__).resolve().parent
WIDGET_URI = cfg("WIDGET_URI", "ui://widget/pricing-widget-v1.html")
WIDGET_MIME_TYPE = cfg("WIDGET_MIME_TYPE", "text/html;profile=mcp-app")
WIDGET_HTML_PATH = Path(
    cfg("WIDGET_HTML_PATH", str(BASE_DIR.parent / "public" / "pricing-widget.html"))
)

MAX_PRICING_CALLS = 3

# SDK para despliegues: stateless_http + json_response
mcp = FastMCP(
    "pazy-context",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,  # solo para pruebas con Cloudflare
    ),
)
mcp.settings.streamable_http_path = "/"


@mcp.resource(WIDGET_URI)
def pricing_widget() -> str:
    """Plantilla UI del widget de cotización de pricing."""
    return WIDGET_HTML_PATH.read_text(encoding="utf-8")

###################################### TOOLS ###########################################
################## TOOL 1 LLAMADA API ###########################
@mcp.tool(
    name="pricing_api",
    description=(
        """Obtiene una cotización real del plan funerario de Pazy usando la API oficial.

        Usa esta herramienta únicamente cuando el usuario quiera obtener una cotización
        del plan funerario de Pazy.

        IMPORTANTE SOBRE EL LÍMITE DE USO:
        - El usuario solo dispone de 3 consultas de cotización por usuario cada 24h.
        - Debes informar al usuario de este límite de forma clara y amable.
        - Si el usuario alcanza el límite, no debes intentar llamar repetidamente a la herramienta.
        - Si la herramienta devuelve LIMIT_TRIES_REACHED, informa al usuario de que ha agotado
          sus 3 consultas disponibles y ofrece derivarlo a un operador o asesor.

        Antes de llamar a esta herramienta debes guiar al usuario paso a paso y confirmar
        los datos necesarios para la cotización.

        REGLAS DE RECOGIDA DE DATOS:
        - Haz solo UNA pregunta cada vez.
        - No pidas varios datos en el mismo mensaje.
        - Espera siempre la respuesta del usuario antes de preguntar lo siguiente.
        - No inventes ni asumas valores que el usuario no haya confirmado.

        FLUJO MÍNIMO QUE DEBES RESPETAR ANTES DE LLAMAR:
        1. Pregunta si el plan es para la propia persona o para otra persona.
        2. Pregunta si la persona beneficiaria reside en España.
           - Si NO reside en España, informa amablemente de que Pazy solo ofrece servicio
             a personas residentes en España y no llames a esta herramienta.
        3. Recoge la edad de la persona beneficiaria.
           - Puedes aceptar fecha de nacimiento si el usuario la da y convertirla a edad.
           - Si la persona es menor de 50 años, informa amablemente de que el servicio
             está disponible a partir de los 50 años y no llames a esta herramienta.
        4. Recoge el código postal.
        5. Recoge el tipo de funeral: incineracion o inhumacion.
        6. Pregunta si quiere velatorio.
        7. Solo si velatorio es true, pregunta si quiere ceremonia.
           - Si velatorio es false, ceremonia debe ser false automáticamente.
           - Nunca puede haber ceremonia si no hay velatorio.

        REQUISITOS PARA LLAMAR A LA HERRAMIENTA:
        - Solo debes llamar a esta herramienta cuando el usuario haya confirmado
          explícitamente los datos y estén completos.
        - Después de enseñar los datos, pregunta SIEMPRE al usuario si son correctos.
        - Los datos obligatorios para llamar son:
          - edad
          - codigo_postal
          - tipo_funeral
          - velatorio
          - ceremonia

        REGLAS DE USO:
        - Nunca muestres ni inventes precios si no vienen de esta herramienta en este turno.
        - Si el usuario cambia cualquier dato después de una cotización, debes volver
          a llamar a esta herramienta para generar una nueva, pero solo si todavía
          no ha agotado sus 3 consultas.
        - No inventes pasos de contratación adicionales.

        SCOPE OF THE ASSISTANT:
        Este asistente únicamente guía al usuario para obtener una cotización.

        Después de mostrar la cotización:
        - NO solicites datos personales (nombre, teléfono, email, DNI).
        - NO solicites datos de pago.
        - NO intentes completar una contratación.

        Si el usuario desea continuar con la contratación,
        indícale que el siguiente paso se realiza a través del proceso
        oficial de Pazy o con un asesor humano."""
    ),
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
    meta={
        "ui": {
            "resourceUri": WIDGET_URI,
        },
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Preparando cotización…",
        "openai/toolInvocation/invoked": "Cotización lista.",
    },
)
def pricing_api(
    codigo_postal: str,
    edad: int,
    tipo_funeral: str,
    velatorio: bool,
    ceremonia: bool,
    ctx: Context,
) -> Dict[str, Any]:
    limit_info = get_user_limit_info(ctx)

    base_meta = {
        "ui": {
            "resourceUri": WIDGET_URI,
        },
        "openai/outputTemplate": WIDGET_URI,
        "widgetMimeType": WIDGET_MIME_TYPE,
        "maxAllowedCalls": limit_info["max_calls"],
        "callsUsed": limit_info["count"],
        "callsRemaining": limit_info["remaining"],
        "limitResetAt": limit_info["reset_at_iso"],
    }

    if not can_user_call_pricing(ctx):
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Has agotado el máximo de 3 consultas permitidas en las últimas 24 horas. "
                        "Ya no puedo generar una nueva cotización aquí por ahora. "
                        "Si lo deseas, puedo indicarte cómo continuar con un asesor."
                    ),
                }
            ],
            "structuredContent": {
                "ok": False,
                "error": "LIMIT_TRIES_REACHED",
                "message": "El usuario ha alcanzado el máximo de 3 consultas en 24 horas.",
                "summary": {
                    "total_resultados": 0,
                    "mensaje": "Límite de consultas alcanzado.",
                },
                "quotes": [],
            },
            "_meta": {
                **base_meta,
                "quoteReady": False,
                "quoteCount": 0,
                "apiStatus": None,
            },
        }

    state = {
        "datos": {
            "codigo_postal": codigo_postal,
            "edad": edad,
            "destino_final": tipo_funeral,
            "velatorio": velatorio,
            "ceremonia": ceremonia,
        },
        "api_response": None,
        "api_error": None,
        "api_status": None,
        "msg_post": None,
        "pricing_normalized": None,
    }

    out = subgraph_pricing.invoke(state)

    api_error = out.get("api_error")
    api_status = out.get("api_status")
    normalized = out.get("pricing_normalized") or {}

    ok = bool(normalized.get("ok"))
    quotes = normalized.get("quotes") or []
    summary = normalized.get("summary") or {}
    total_resultados = summary.get("total_resultados", 0)

    # Consumimos intento solo cuando la tool realmente se ha ejecutado
    limit_info = consume_pricing_call(ctx)

    base_meta = {
        **base_meta,
        "apiStatus": api_status,
        "callsUsed": limit_info["count"],
        "callsRemaining": limit_info["remaining"],
        "limitResetAt": limit_info["reset_at_iso"],
    }

    if ok and isinstance(api_status, int) and 200 <= api_status < 300:
        if total_resultados == 0:
            text = "He procesado tu solicitud, pero no he encontrado cotizaciones disponibles."
        elif total_resultados == 1:
            text = "He encontrado 1 cotización para ti."
        else:
            text = f"He encontrado {total_resultados} cotizaciones para ti."

        return {
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "structuredContent": normalized,
            "_meta": {
                **base_meta,
                "quoteReady": True,
                "quoteCount": len(quotes),
            },
        }

    error_code = normalized.get("error") or api_error or "API_CALL_FAILED"

    if error_code == "LIMIT_TRIES_REACHED":
        user_text = (
            "Has agotado el máximo de 3 consultas permitidas en las últimas 24 horas. "
            "Ya no puedo generar una nueva cotización aquí."
        )
    else:
        user_text = (
            "No he podido obtener la cotización en este momento. "
            "Si quieres, puedes revisar los datos o probar más tarde."
        )

    return {
        "content": [
            {
                "type": "text",
                "text": user_text,
            }
        ],
        "structuredContent": {
            **normalized,
            "ok": False,
            "error": error_code,
        },
        "_meta": {
            **base_meta,
            "quoteReady": False,
            "quoteCount": 0,
        },
    }


################## TOOL 2 CONTEXTO RAG ###########################
@mcp.tool(
    name="get_context",
    description=(
        """Consulta la base de conocimiento interna de Pazy para responder preguntas sobre
        el servicio, funcionamiento y preguntas frecuentes.
        Usa esta herramienta para dudas informativas sobre Pazy.
        No la uses para recuperar tono de marca ni para calcular precios."""
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def get_context(query: str) -> dict:
    results = retrieve_faq_rag(VECTORSTORE, query=query, k=3)

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "success": True,
                        "query": query,
                        "count": len(results),
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        ],
        "structuredContent": {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        },
    }


################## TOOL 3 BRAND CONTEXT ###########################
@mcp.tool(
    name="brand_context",
    description=(
        """Recupera contexto del manual de marca de Pazy para ayudar a responder con el tono,
        enfoque y estilo adecuados.
        Usa esta herramienta cuando necesites adaptar la respuesta a la voz de marca de Pazy,
        por ejemplo en saludos, acompañamiento, explicaciones delicadas o mensajes comerciales.
        No devuelve precios ni información transaccional."""
    ),
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def brand_context(query: str) -> dict:
    results = retrieve_brand_rag(VECTORSTORE, query=query, k=3)

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "success": True,
                        "query": query,
                        "count": len(results),
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        ],
        "structuredContent": {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        },
    }


################################## Main y /mcp #######################################
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Mount("/mcp", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port)