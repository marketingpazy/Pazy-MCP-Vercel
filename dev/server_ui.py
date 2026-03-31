from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict


from fastmcp import FastMCP, Context
from fastmcp.server.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from starlette.routing import Mount, Route
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse

from dev.tools.tool_1.subgraph_tool_1 import create_pricing_subgraph
from dev.tools.tool_2_3.rag_store import (
    RagSettings,
    build_or_load_vectorstore,
    retrieve_faq_rag,
    retrieve_brand_rag,
)
from dev.aux_functions import cfg, normalize_tipo_funeral, is_valid_postal_code, resolve_widget_domain
from dev.users_control import (
    can_user_call_pricing,
    consume_pricing_call,
    get_user_limit_info,
)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8080"))

RAG_SETTINGS = RagSettings()
subgraph_pricing = create_pricing_subgraph()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

WIDGET_URI = cfg("WIDGET_URI", "ui://widget/pricing-widget-v1.html")

# Resolve widget path — try multiple locations for compatibility
_widget_candidates = [
    BASE_DIR / "pricing-widget.html",                    # dev/pricing-widget.html (Vercel)
    PROJECT_ROOT / "public" / "pricing-widget.html",     # public/ (local dev)
]
_widget_cfg = cfg("WIDGET_HTML_PATH")
if _widget_cfg:
    _candidate = Path(_widget_cfg)
    if not _candidate.is_absolute():
        _widget_candidates.insert(0, (PROJECT_ROOT / _candidate).resolve())
    else:
        _widget_candidates.insert(0, _candidate)

WIDGET_HTML_PATH = next(
    (p for p in _widget_candidates if p.exists()),
    _widget_candidates[0],  # fallback
)

WIDGET_DOMAIN = resolve_widget_domain()

WIDGET_CONNECT_DOMAINS = [
    # Añadir APIs externas solo si el widget hace fetch directamente.
]

WIDGET_RESOURCE_DOMAINS = [
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
]

EDAD_MIN = cfg("EDAD_MIN", 50)

mcp = FastMCP("pazy-context")

async def health(request):
    return JSONResponse({"ok": True})

async def openai_apps_challenge(request):
    token = os.getenv("OPENAI_APPS_CHALLENGE_TOKEN", "").strip()

    if not token:
        return PlainTextResponse(
            "OPENAI_APPS_CHALLENGE_TOKEN not configured",
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )

    return PlainTextResponse(
        token,
        status_code=200,
        headers={"Cache-Control": "no-store"},
    )

# Streamable HTTP transport — works reliably on Vercel serverless
# ChatGPT and Claude both support this transport
mcp_app = mcp.http_app(path="/")

app = Starlette(
    routes=[
        Route("/healthz", health),
        Route("/.well-known/openai-apps-challenge", openai_apps_challenge, methods=["GET"]),
        Mount("/mcp", app=mcp_app),
    ],
    lifespan=mcp_app.lifespan,
)


@mcp.resource(
    WIDGET_URI,
    app=AppConfig(
        domain=WIDGET_DOMAIN,
        prefers_border=True,
        csp=ResourceCSP(
            connect_domains=WIDGET_CONNECT_DOMAINS,
            resource_domains=WIDGET_RESOURCE_DOMAINS,
            # frame_domains=[]  # solo si usas iframes
        ),
    ),
)
def pricing_widget() -> str:
    return WIDGET_HTML_PATH.read_text(encoding="utf-8")


###################################### TOOLS ###########################################
################## TOOL 1 LLAMADA API ###########################
@mcp.tool(
    app=AppConfig(resource_uri=WIDGET_URI),
    name="pricing_api",
    description=(
        """Obtiene una cotización real de un plan funerario de Pazy mediante su API oficial.

        Esta herramienta se utiliza cuando el usuario solicita una cotización personalizada
        basada en sus preferencias y datos básicos.

        FUNCIONALIDAD:
        Devuelve opciones de planes funerarios con precios y condiciones en función de:
        - edad
        - código postal
        - tipo de funeral ('incineración' o 'inhumación')
        - velatorio
        - ceremonia

        LÍMITE DE USO:
        - Cada usuario dispone de hasta 10 consultas de cotización en un periodo de 24 horas.
        - Si se alcanza el límite, la herramienta devolverá el estado "LIMIT_TRIES_REACHED".
        - En ese caso, se debe informar al usuario de que no es posible generar más cotizaciones
        en ese momento y ofrecer alternativas (por ejemplo, contacto con un asesor).

        REQUISITOS DE DATOS:
        La herramienta requiere que los siguientes datos estén disponibles y confirmados:
        - edad (≥ 50 años; el usuario tendrá la opción de ponerse en contacto con un operador o asesor)
        - código postal en España
        - tipo de funeral
        - preferencia de velatorio
        - preferencia de ceremonia

        CONSIDERACIONES:
        - El servicio solamente está disponible para personas residentes en España.
        - Cada ejecución corresponde a una única persona.
        - Si los datos cambian, se puede generar una nueva cotización (respetando el límite de uso).

        COMPORTAMIENTO:
        - Los precios mostrados provienen exclusivamente de esta herramienta.
        - No realiza contratación ni solicita datos personales o de pago.
        - No modifica datos externos; únicamente consulta información.

        RESULTADO:
        Devuelve una respuesta estructurada con:
        - listado de cotizaciones
        - resumen de resultados
        - información necesaria para representar la UI asociada
        - No inventar datos.
        """
    ),
    annotations={
        "readOnlyHint": True,
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

    tipo_funeral_normalizado = normalize_tipo_funeral(tipo_funeral)
    if tipo_funeral_normalizado is None:
        return ToolResult(
            content=(
                "El tipo de funeral indicado no es válido. "
                "Debe ser 'incineración' o 'inhumación'."
            ),
            structured_content={
                "ok": False,
                "error": "INVALID_FUNERAL_TYPE",
                "message": (
                    "El campo tipo_funeral debe ser 'incineración' o 'inhumación'."
                ),
                "summary": {
                    "total_resultados": 0,
                    "mensaje": "Tipo de funeral no válido.",
                },
                "quotes": [],
                "usage": {
                    "maxCalls": limit_info["max_calls"],
                    "used": limit_info["count"],
                    "remaining": limit_info["remaining"],
                    "limitReached": limit_info["limit_reached"],
                },
            },
            meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "quoteReady": False,
            },
        )

    if not can_user_call_pricing(ctx):
        return ToolResult(
            content=(
                "Has agotado el máximo de 10 consultas permitidas en las últimas 24 horas. "
                "Ya no puedo generar una nueva cotización aquí por ahora. "
                "Si lo deseas, puedo indicarte cómo continuar con un asesor."
            ),
            structured_content={
                "ok": False,
                "error": "LIMIT_TRIES_REACHED",
                "message": "El usuario ha alcanzado el máximo de 10 consultas en 24 horas.",
                "summary": {
                    "total_resultados": 0,
                    "mensaje": "Límite de consultas alcanzado.",
                },
                "quotes": [],
                "limitReached": True,
                "usage": {
                    "maxCalls": limit_info["max_calls"],
                    "used": limit_info["count"],
                    "remaining": 0,
                    "resetAt": limit_info["reset_at_iso"],
                    "limitReached": True,
                },
            },
            meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "quoteReady": False,
            },
        )

    if int(edad) < int(EDAD_MIN):
        return ToolResult(
            content=(
                f"El usuario debe ser mayor de {EDAD_MIN} años. "
                f"Si es menor de esa edad deberá ponerse en contacto con un operador "
                f"en el teléfono 900 900 516. Se le pasará con un operador de su "
                f"código postal {codigo_postal}."
            ),
            structured_content={
                "ok": False,
                "error": "MIN_AGE_NOT_REACHED",
                "message": (
                    f"El usuario es menor de {EDAD_MIN} años. "
                    "Debe ponerse en contacto con un operador en el teléfono 900 900 516."
                ),
                "summary": {
                    "total_resultados": 0,
                    "mensaje": "Edad mínima no alcanzada.",
                },
                "quotes": [],
                "usage": {
                    "maxCalls": limit_info["max_calls"],
                    "used": limit_info["count"],
                    "remaining": limit_info["remaining"],
                    "resetAt": limit_info["reset_at_iso"],
                    "limitReached": limit_info["limit_reached"],
                },
            },
            meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "quoteReady": False,
            },
        )

    if not is_valid_postal_code(codigo_postal):
        return ToolResult(
            content=(
                "El código postal indicado no es válido en España. "
                "Debe contener 5 dígitos y corresponder a una provincia española."
            ),
            structured_content={
                "ok": False,
                "error": "INVALID_POSTAL_CODE",
                "message": (
                    "El código postal debe tener 5 dígitos y un prefijo entre 01 y 52."
                ),
                "summary": {
                    "total_resultados": 0,
                    "mensaje": "Código postal no válido.",
                },
                "quotes": [],
                "usage": {
                    "maxCalls": limit_info["max_calls"],
                    "used": limit_info["count"],
                    "remaining": limit_info["remaining"],
                    "resetAt": limit_info["reset_at_iso"],
                    "limitReached": limit_info["limit_reached"],
                },
            },
            meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "quoteReady": False,
            },
        )

    state = {
        "datos": {
            "codigo_postal": codigo_postal,
            "edad": edad,
            "destino_final": tipo_funeral_normalizado,
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
    quote_count = len(quotes)

    # La consulta válida consume intento
    limit_info = consume_pricing_call(ctx)

    usage_payload = {
        "maxCalls": limit_info["max_calls"],
        "used": limit_info["count"],
        "remaining": limit_info["remaining"],
        "limitReached": limit_info["limit_reached"],
    }

    if ok and isinstance(api_status, int) and 200 <= api_status < 300:
        if quote_count == 0:
            text = "He procesado tu solicitud, pero no he encontrado cotizaciones disponibles."
        else:
            text = "Aquí tienes tu cotización."

        compat_payload = {
            **normalized,
            "summary": {
                **(normalized.get("summary") or {}),
                "total_resultados": quote_count,
            },
            "quoteCount": quote_count,
            "ui": {
                "resourceUri": WIDGET_URI,
            },
            "openai/outputTemplate": WIDGET_URI,
            "usage": usage_payload,
        }

        return ToolResult(
            content=text,
            structured_content=compat_payload,
            meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "quoteReady": True,
                "quoteCount": quote_count,
                "usage": usage_payload,
            },
        )

    error_code = normalized.get("error") or api_error or "API_CALL_FAILED"

    if error_code == "LIMIT_TRIES_REACHED":
        user_text = (
            "Has agotado el máximo de 10 consultas permitidas en las últimas 24 horas. "
            "Ya no puedo generar una nueva cotización aquí."
        )
        usage_payload = {
            **usage_payload,
            "remaining": 0,
            "limitReached": True,
        }
        limit_reached = True
    else:
        user_text = (
            "No he podido obtener la cotización en este momento. "
            "Si quieres, puedes revisar los datos o probar más tarde."
        )
        limit_reached = usage_payload["limitReached"]

    return ToolResult(
        content=user_text,
        structured_content={
            **normalized,
            "ok": False,
            "error": error_code,
            "summary": {
                **(normalized.get("summary") or {}),
                "total_resultados": quote_count,
            },
            "quoteCount": quote_count,
            "ui": {
                "resourceUri": WIDGET_URI,
            },
            "openai/outputTemplate": WIDGET_URI,
            "usage": usage_payload,
            "limitReached": limit_reached,
        },
        meta={
            "ui": {"resourceUri": WIDGET_URI},
            "openai/outputTemplate": WIDGET_URI,
            "quoteReady": False,
            "quoteCount": quote_count,
            "usage": usage_payload,
        },
    )


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
    vectorstore = build_or_load_vectorstore(RAG_SETTINGS)
    results = retrieve_faq_rag(vectorstore, query=query, k=3)

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=host, port=port, proxy_headers=True)
