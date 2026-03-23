from __future__ import annotations

import re
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from dev.aux_functions import price_field_for_pack, clean_text, to_float, normalize_list_of_lines, to_int, format_money_for_text, map_destino_final, map_pack, map_si_no

def _build_resumen_texto(input_data: Dict[str, Any], resultado: Dict[str, Any]) -> str:
    nombre_plan = clean_text(
        resultado.get("nombre")
        or resultado.get("etiqueta")
        or "Plan funerario"
    )

    precio_total = format_money_for_text(resultado.get("precio_total"))
    precio_contado = format_money_for_text(resultado.get("precio_contado"))

    cuotas = resultado.get("cuotas_mensuales") or []
    cuota_preferida = None

    if isinstance(cuotas, list):
        for cuota in cuotas:
            if not isinstance(cuota, dict):
                continue
            if to_float(cuota.get("plazo_anos")) == 10:
                cuota_preferida = cuota
                break
        if cuota_preferida is None and cuotas:
            cuota_preferida = cuotas[0] if isinstance(cuotas[0], dict) else None

    cuotas_texto = ""
    if cuota_preferida:
        plazo = to_float(cuota_preferida.get("plazo_anos"))
        importe = to_float(cuota_preferida.get("cuota_mensual"))
        if plazo is not None and importe is not None:
            plazo_str = str(int(plazo)) if float(plazo).is_integer() else str(plazo)
            importe_str = format_money_for_text(importe)
            cuotas_texto = f"{plazo_str} años: {importe_str}/mes"

    partes = [nombre_plan]

    if precio_total:
        partes.append(f"precio total: {precio_total}")

    if precio_contado:
        partes.append(f"precio descuento: {precio_contado}")

    if cuotas_texto:
        partes.append(f"cuotas: {cuotas_texto}")

    return " | ".join(partes)


def crear_url(input_data: Dict[str, Any], resultado: Dict[str, Any]) -> str:
    edad = to_float(input_data.get("edad"))
    zip_code = clean_text(input_data.get("codigo_postal"))
    funeral_type = map_destino_final(input_data.get("destino_final"))
    sala_velatorio = map_si_no(input_data.get("velatorio"))
    ceremonia = map_si_no(input_data.get("ceremonia"))
    pack = map_pack(input_data.get("paquete"))

    precio_total = to_float(resultado.get("precio_total"))
    resumen = _build_resumen_texto(input_data, resultado)

    params: Dict[str, Any] = {}

    if edad is not None:
        params["age"] = int(edad) if float(edad).is_integer() else edad

    if zip_code:
        params["zip"] = zip_code

    if funeral_type:
        params["pre_funeral_type"] = funeral_type

    if sala_velatorio:
        params["sala_velatorio"] = sala_velatorio

    if ceremonia:
        params["ceremonia"] = ceremonia

    if pack:
        params["pre_selected_plan"] = pack

    price_field = price_field_for_pack(pack)
    if price_field and precio_total is not None:
        params[price_field] = int(precio_total) if float(precio_total).is_integer() else precio_total

    if resumen:
        params["qu_tipo_de_funeral_deseas"] = resumen

    base_link = os.getenv("BASE_MAGIC_LINK")
    return f"{base_link}?{urlencode(params, doseq=True)}"

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
        cuota = to_float(v)
        items.append(
            {
                "plazo_anos": plazo,
                "cuota_mensual": cuota,
                "label": str(k),
            }
        )

    items.sort(key=lambda x: (x["plazo_anos"] is None, x["plazo_anos"]))
    return items


def _normalize_resultado(resultado: Dict[str, Any], input_data: Dict[str, Any], idx: int) -> Dict[str, Any]:
    extras_detalle = resultado.get("extras_detalle") or {}
    kilometraje = extras_detalle.get("kilometraje") or {}
    magic_link = crear_url(input_data, resultado)

    return {
        "id": str(idx),
        "nombre": clean_text(resultado.get("nombre")),
        "etiqueta": clean_text(resultado.get("etiqueta")),
        "direccion": clean_text(resultado.get("direccion")),
        "ciudad": clean_text(resultado.get("ciudad")),
        "provincia": clean_text(resultado.get("provincia")),
        "codigo_postal": clean_text(resultado.get("codigo_postal")),
        #"telefono": clean_text(resultado.get("telefono")),
        #"email": clean_text(resultado.get("email")),
        "coordenadas": clean_text(resultado.get("coordenadas")),
        "tipo_empresa": clean_text(resultado.get("tipo_empresa")),
        "publico_privado": clean_text(resultado.get("publico_privado")),
        "distancia_km": to_float(resultado.get("distancia_km")),
        "precio_base": to_float(resultado.get("precio_base")),
        "precio_total": to_float(resultado.get("precio_total")),
        "precio_contado": to_float(resultado.get("precio_contado")),
        "cuotas_mensuales": _normalize_cuotas(resultado.get("cuotas_mensuales")),
        "servicios_incluidos": normalize_list_of_lines(resultado.get("servicios_incluidos")),
        "avisos": resultado.get("avisos") if isinstance(resultado.get("avisos"), list) else [],
        "admite_extras": bool(resultado.get("admite_extras")),
        "tipo_restriccion_extras": clean_text(resultado.get("tipo_restriccion_extras")),
        "extras": {
            "extras_tipificados": extras_detalle.get("extras_tipificados") or [],
            "extras_euros": to_float(extras_detalle.get("extras_euros")),
            "extras_legacy": to_float(extras_detalle.get("extras_legacy")),
            "total_extras": to_float(extras_detalle.get("total_extras")),
            "kilometraje": {
                "kilometros": to_float(kilometraje.get("kilometros")),
                "precio_por_km": to_float(kilometraje.get("precio_por_km")),
                "factor_ida_vuelta": to_float(kilometraje.get("factor_ida_vuelta")),
                "importe_calculado": to_float(kilometraje.get("importe_calculado")),
                "limite_maximo": to_float(kilometraje.get("limite_maximo")),
                "importe_final": to_float(kilometraje.get("importe_final")),
            },
        },
        # para futuro botón
        "cta": {
            "label": "Solicita tu plan funerario",
            "url": magic_link,
            "enabled": bool(magic_link),
        },
    }


def _is_label_response(resultado: Dict[str, Any]) -> bool:
    return clean_text(resultado.get("etiqueta")) == "El más barato"

def _is_fav(resultado: Dict[str, Any]) -> bool:
    return clean_text(resultado.get("etiqueta")) == "Nuestro favorito"


def _pick_preferred_resultados(resultados: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not resultados:
        return []

    mas_barato = [r for r in resultados if isinstance(r, dict) and _is_label_response(r)]
    if mas_barato:
        return mas_barato

    favorito = [r for r in resultados if isinstance(r, dict) and _is_fav(r)]
    if favorito:
        return favorito

    return [r for r in resultados if isinstance(r, dict)]


def _normalize_presupuesto(presupuesto: Dict[str, Any], datos, presupuesto_idx: int) -> Dict[str, Any]:
    resultados = presupuesto.get("resultados") or []
    resultados_filtrados = _pick_preferred_resultados(resultados)

    input_data = {
        "edad": datos.get("edad"),
        "codigo_postal": datos.get("codigo_postal"),
        "destino_final": datos.get("destino_final"),
        "velatorio": datos.get("velatorio"),
        "ceremonia": datos.get("ceremonia"),
        "paquete": presupuesto.get("paquete"),
    }

    normalized_results = [
        _normalize_resultado(r, input_data, idx=i + 1 )
        for i, r in enumerate(resultados_filtrados)
    ]

    return {
        "persona_numero": to_int(presupuesto.get("persona_numero")) or presupuesto_idx,
        "codigo_postal": clean_text(presupuesto.get("codigo_postal")),
        "cp_servicio": clean_text(presupuesto.get("cp_servicio")),
        "paquete": clean_text(presupuesto.get("paquete")),
        "destino_final": clean_text(presupuesto.get("destino_final")),
        "edad": to_int(presupuesto.get("edad")),
        "repatriacion": bool(presupuesto.get("repatriacion")),
        "km_traslado_calculados": to_float(presupuesto.get("km_traslado_calculados")),
        "total_resultados": to_int(presupuesto.get("total_resultados")) or len(normalized_results),
        "quotes": normalized_results,
        "requiere_contacto_asesor": bool(presupuesto.get("requiere_contacto_asesor")),
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
                "input": {
                    "codigo_postal": datos.get("codigo_postal"),
                    "edad": datos.get("edad"),
                    "destino_final": datos.get("destino_final"),
                    "velatorio": datos.get("velatorio"),
                    "ceremonia": datos.get("ceremonia"),
                },
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
            if isinstance(r, dict) #and _is_label_response(r)
        ]

        normalized = {
            "ok": success,
            "api_status": api_status,
            "error": None if success else api_error,
            "message": clean_text(api_response.get("mensaje")),
            "input": {
                "codigo_postal": clean_text(api_response.get("codigo_postal")) or clean_text(datos.get("codigo_postal")),
                "edad": to_int(api_response.get("edad")) or to_int(datos.get("edad")),
                "paquete": clean_text(api_response.get("paquete")),
                "destino_final": clean_text(api_response.get("destino_final")) or clean_text(datos.get("destino_final")),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
            },
            "quotes": quotes,
            "budgets": [
                {
                    "persona_numero": 1,
                    "codigo_postal": clean_text(api_response.get("codigo_postal")) or clean_text(datos.get("codigo_postal")),
                    "cp_servicio": None,
                    "paquete": clean_text(api_response.get("paquete")),
                    "destino_final": clean_text(api_response.get("destino_final")) or clean_text(datos.get("destino_final")),
                    "edad": to_int(api_response.get("edad")) or to_int(datos.get("edad")),
                    "repatriacion": False,
                    "km_traslado_calculados": None,
                    "total_resultados": to_int(api_response.get("total_resultados")) or len(quotes),
                    "quotes": quotes,
                    "requiere_contacto_asesor": bool(api_response.get("requiere_contacto_asesor")),
                }
            ],
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": to_int(api_response.get("total_resultados")) or len(quotes),
                "requiere_contacto_asesor": bool(api_response.get("requiere_contacto_asesor")),
                "numero_clientes": 1,
                "presupuestos_generados": 1,
            },
        }

        return {**state, "pricing_normalized": normalized}

    # Caso B: respuesta multi-persona con presupuestos
    if isinstance(api_response.get("presupuestos"), list):
        budgets = [
            _normalize_presupuesto(p, datos, presupuesto_idx=i + 1)
            for i, p in enumerate(api_response.get("presupuestos", []))
            if isinstance(p, dict)
        ]

        all_quotes: List[Dict[str, Any]] = []
        for budget in budgets:
            for quote in budget["quotes"]:
                all_quotes.append(
                    {
                        **quote,
                        "persona_numero": budget["persona_numero"],
                    }
                )

        normalized = {
            "ok": success,
            "api_status": api_status,
            "error": None if success else api_error,
            "message": clean_text(api_response.get("mensaje")),
            "input": {
                "codigo_postal": clean_text(datos.get("codigo_postal")),
                "edad": to_int(datos.get("edad")),
                "paquete": clean_text(datos.get("paquete")),
                "destino_final": clean_text(datos.get("destino_final")),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
            },
            "quotes": all_quotes,
            "budgets": budgets,
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": sum(b["total_resultados"] for b in budgets),
                "requiere_contacto_asesor": any(b["requiere_contacto_asesor"] for b in budgets),
                "numero_clientes": to_int(api_response.get("numero_clientes")),
                "presupuestos_generados": to_int(api_response.get("presupuestos_generados")) or len(budgets),
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
            "message": clean_text(api_response.get("mensaje")),
            "input": {
                "codigo_postal": datos.get("codigo_postal"),
                "edad": datos.get("edad"),
                "destino_final": datos.get("destino_final"),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
            },
            "quotes": [],
            "budgets": [],
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": 0,
                "requiere_contacto_asesor": False,
                "numero_clientes": None,
                "presupuestos_generados": 0,
            },
        },
    }