from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # quita comillas externas si vienen serializadas como string raro
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()

    # elimina prefijos decorativos tipo "** "
    text = re.sub(r"^\*+\s*", "", text).strip()
    return text or None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_list_of_lines(value: Any) -> List[str]:
    """
    Convierte textos tipo:
    "- item 1\n - item 2"
    en ["item 1", "item 2"].
    """
    text = _clean_text(value)
    if not text:
        return []

    parts = []
    for line in text.splitlines():
        item = line.strip()
        item = re.sub(r"^[\-\•\*]\s*", "", item).strip()
        if item:
            parts.append(item)
    return parts


def _normalize_cuotas(value: Any) -> List[Dict[str, Any]]:
    """
    Convierte:
    {
      "1 años": 447.92,
      "2 años": 223.96
    }
    en:
    [
      {"plazo_anos": 1, "cuota_mensual": 447.92, "label": "1 años"},
      {"plazo_anos": 2, "cuota_mensual": 223.96, "label": "2 años"}
    ]
    """
    if not isinstance(value, dict):
        return []

    items: List[Dict[str, Any]] = []
    for k, v in value.items():
        match = re.search(r"(\d+)", str(k))
        plazo = int(match.group(1)) if match else None
        cuota = _to_float(v)
        items.append(
            {
                "plazo_anos": plazo,
                "cuota_mensual": cuota,
                "label": str(k),
            }
        )

    items.sort(key=lambda x: (x["plazo_anos"] is None, x["plazo_anos"]))
    return items


def _normalize_resultado(resultado: Dict[str, Any], idx: int) -> Dict[str, Any]:
    extras_detalle = resultado.get("extras_detalle") or {}
    kilometraje = extras_detalle.get("kilometraje") or {}

    return {
        "id": str(idx),
        "nombre": _clean_text(resultado.get("nombre")),
        "etiqueta": _clean_text(resultado.get("etiqueta")),
        "direccion": _clean_text(resultado.get("direccion")),
        "ciudad": _clean_text(resultado.get("ciudad")),
        "provincia": _clean_text(resultado.get("provincia")),
        "codigo_postal": _clean_text(resultado.get("codigo_postal")),
        #"telefono": _clean_text(resultado.get("telefono")),
        #"email": _clean_text(resultado.get("email")),
        "coordenadas": _clean_text(resultado.get("coordenadas")),
        "tipo_empresa": _clean_text(resultado.get("tipo_empresa")),
        "publico_privado": _clean_text(resultado.get("publico_privado")),
        "distancia_km": _to_float(resultado.get("distancia_km")),
        "precio_base": _to_float(resultado.get("precio_base")),
        "precio_total": _to_float(resultado.get("precio_total")),
        "precio_contado": _to_float(resultado.get("precio_contado")),
        "cuotas_mensuales": _normalize_cuotas(resultado.get("cuotas_mensuales")),
        "servicios_incluidos": _normalize_list_of_lines(resultado.get("servicios_incluidos")),
        "avisos": resultado.get("avisos") if isinstance(resultado.get("avisos"), list) else [],
        "admite_extras": bool(resultado.get("admite_extras")),
        "tipo_restriccion_extras": _clean_text(resultado.get("tipo_restriccion_extras")),
        "extras": {
            "extras_tipificados": extras_detalle.get("extras_tipificados") or [],
            "extras_euros": _to_float(extras_detalle.get("extras_euros")),
            "extras_legacy": _to_float(extras_detalle.get("extras_legacy")),
            "total_extras": _to_float(extras_detalle.get("total_extras")),
            "kilometraje": {
                "kilometros": _to_float(kilometraje.get("kilometros")),
                "precio_por_km": _to_float(kilometraje.get("precio_por_km")),
                "factor_ida_vuelta": _to_float(kilometraje.get("factor_ida_vuelta")),
                "importe_calculado": _to_float(kilometraje.get("importe_calculado")),
                "limite_maximo": _to_float(kilometraje.get("limite_maximo")),
                "importe_final": _to_float(kilometraje.get("importe_final")),
            },
        },
        # para futuro botón
        "cta": {
            "label": "Continuar",
            "url": None,
            "enabled": False,
        },
    }


def _normalize_presupuesto(presupuesto: Dict[str, Any], presupuesto_idx: int) -> Dict[str, Any]:
    resultados = presupuesto.get("resultados") or []
    normalized_results = [
        _normalize_resultado(r, idx=i + 1)
        for i, r in enumerate(resultados)
        if isinstance(r, dict)
    ]

    return {
        "persona_numero": _to_int(presupuesto.get("persona_numero")) or presupuesto_idx,
        "codigo_postal": _clean_text(presupuesto.get("codigo_postal")),
        "cp_servicio": _clean_text(presupuesto.get("cp_servicio")),
        "paquete": _clean_text(presupuesto.get("paquete")),
        "destino_final": _clean_text(presupuesto.get("destino_final")),
        "edad": _to_int(presupuesto.get("edad")),
        "repatriacion": bool(presupuesto.get("repatriacion")),
        "km_traslado_calculados": _to_float(presupuesto.get("km_traslado_calculados")),
        "total_resultados": _to_int(presupuesto.get("total_resultados")) or len(normalized_results),
        "quotes": normalized_results,
        "requiere_contacto_asesor": bool(presupuesto.get("requiere_contacto_asesor")),
    }

def _build_input_personas(datos: Dict[str, Any], api_response: Dict[str, Any] | None = None) -> Dict[str, Any]:
    api_response = api_response or {}
    personas = datos.get("personas")

    if isinstance(personas, list) and personas:
        return {
            "personas": [
                {
                    "persona_numero": i + 1,
                    "codigo_postal": _clean_text(p.get("codigo_postal")),
                    "cp_servicio": _clean_text(p.get("cp_servicio")) or _clean_text(p.get("codigo_postal")),
                    "edad": _to_int(p.get("edad")),
                    "paquete": _clean_text(p.get("paquete")),
                    "destino_final": _clean_text(p.get("tipo_funeral")) or _clean_text(p.get("destino_final")),
                    "velatorio": p.get("velatorio"),
                    "ceremonia": p.get("ceremonia"),
                }
                for i, p in enumerate(personas)
                if isinstance(p, dict)
            ]
        }

    return {
        "personas": [
            {
                "persona_numero": 1,
                "codigo_postal": _clean_text(api_response.get("codigo_postal")) or _clean_text(datos.get("codigo_postal")),
                "cp_servicio": _clean_text(api_response.get("cp_servicio")) or _clean_text(datos.get("cp_servicio")) or _clean_text(api_response.get("codigo_postal")) or _clean_text(datos.get("codigo_postal")),
                "edad": _to_int(api_response.get("edad")) or _to_int(datos.get("edad")),
                "paquete": _clean_text(api_response.get("paquete")) or _clean_text(datos.get("paquete")),
                "destino_final": _clean_text(api_response.get("destino_final")) or _clean_text(datos.get("tipo_funeral")) or _clean_text(datos.get("destino_final")),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
            }
        ]
    }


def normalizar_respuesta_pricing(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nodo LangGraph para normalizar la salida de la API de pricing a un formato
    estable para devolver luego desde pricing_api a GPT/UI.

    Entrada esperada en state:
    - datos
    - api_response
    - api_error
    - api_status

    Salida añadida a state:
    - pricing_normalized
    """
    api_response = state.get("api_response")
    api_error = state.get("api_error")
    api_status = state.get("api_status")
    datos = state.get("datos") or {}

    # error aguas arriba o respuesta inválida
    if api_error or not isinstance(api_response, dict):
        return {
            **state,
            "pricing_normalized": {
                "ok": False,
                "api_status": api_status,
                "error": api_error or "INVALID_API_RESPONSE",
                "message": "No se pudo normalizar la respuesta de pricing.",
                "input": _build_input_personas(datos, api_response if isinstance(api_response, dict) else {}),
                "quotes": [],
                "budgets": [],
                "summary": {
                    "mensaje": None,
                    "total_resultados": 0,
                    "requiere_contacto_asesor": False,
                    "numero_clientes": None,
                    "presupuestos_generados": 0,
                },
            },
        }

    success = bool(api_response.get("success"))

    # Caso A: respuesta simple con resultados
    if isinstance(api_response.get("resultados"), list):
        quotes = [
            _normalize_resultado(r, idx=i + 1)
            for i, r in enumerate(api_response.get("resultados", []))
            if isinstance(r, dict)
        ]

        normalized = {
            "ok": success,
            "api_status": api_status,
            "error": None if success else api_error,
            "message": _clean_text(api_response.get("mensaje")),
            "input": _build_input_personas(datos, api_response),
            "quotes": quotes,
            "budgets": [
                {
                    "persona_numero": 1,
                    "codigo_postal": _clean_text(api_response.get("codigo_postal")) or _clean_text(datos.get("codigo_postal")),
                    "cp_servicio": None,
                    "paquete": _clean_text(api_response.get("paquete")),
                    "destino_final": _clean_text(api_response.get("destino_final")) or _clean_text(datos.get("destino_final")),
                    "edad": _to_int(api_response.get("edad")) or _to_int(datos.get("edad")),
                    "repatriacion": False,
                    "km_traslado_calculados": None,
                    "total_resultados": _to_int(api_response.get("total_resultados")) or len(quotes),
                    "quotes": quotes,
                    "requiere_contacto_asesor": bool(api_response.get("requiere_contacto_asesor")),
                }
            ],
            "summary": {
                "mensaje": _clean_text(api_response.get("mensaje")),
                "total_resultados": _to_int(api_response.get("total_resultados")) or len(quotes),
                "requiere_contacto_asesor": bool(api_response.get("requiere_contacto_asesor")),
                "numero_clientes": 1,
                "presupuestos_generados": 1,
            },
        }

        return {**state, "pricing_normalized": normalized}

    # Caso B: respuesta multi-persona con presupuestos
    if isinstance(api_response.get("presupuestos"), list):
        budgets = [
            _normalize_presupuesto(p, presupuesto_idx=i + 1)
            for i, p in enumerate(api_response.get("presupuestos", []))
            if isinstance(p, dict)
        ]

        all_quotes: List[Dict[str, Any]] = []
        for budget in budgets:
            for quote in budget["quotes"]:
                all_quotes.append(
                    {
                        **quote,
                        "id": f'{budget["persona_numero"]}-{quote["id"]}',
                        "persona_numero": budget["persona_numero"],
                    }
                )

        normalized = {
            "ok": success,
            "api_status": api_status,
            "error": None if success else api_error,
            "message": _clean_text(api_response.get("mensaje")),
            "input": _build_input_personas(datos, api_response),
            "quotes": all_quotes,
            "budgets": budgets,
            "summary": {
                "mensaje": _clean_text(api_response.get("mensaje")),
                "total_resultados": sum(b["total_resultados"] for b in budgets),
                "requiere_contacto_asesor": any(b["requiere_contacto_asesor"] for b in budgets),
                "numero_clientes": _to_int(api_response.get("numero_clientes")),
                "presupuestos_generados": _to_int(api_response.get("presupuestos_generados")) or len(budgets),
            },
        }

        return {**state, "pricing_normalized": normalized}

    # Fallback
    return {
        **state,
        "pricing_normalized": {
            "ok": False,
            "api_status": api_status,
            "error": api_error or "UNRECOGNIZED_API_RESPONSE",
            "message": _build_input_personas(datos, api_response if isinstance(api_response, dict) else {}),
            "quotes": [],
            "budgets": [],
            "summary": {
                "mensaje": _clean_text(api_response.get("mensaje")),
                "total_resultados": 0,
                "requiere_contacto_asesor": False,
                "numero_clientes": None,
                "presupuestos_generados": 0,
            },
        },
    }