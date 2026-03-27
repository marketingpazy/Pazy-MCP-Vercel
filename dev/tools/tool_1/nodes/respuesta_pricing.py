from __future__ import annotations

import re
import os
from typing import Any, Dict, List
from urllib.parse import urlencode

from dev.aux_functions import (
    price_field_for_pack,
    clean_text,
    to_float,
    normalize_list_of_lines,
    to_int,
    format_money_for_text,
    map_destino_final,
    map_pack,
    map_si_no,
)


def _build_resumen_texto(input_data: Dict[str, Any], resultado: Dict[str, Any]) -> str:
    nombre_plan = clean_text(
        resultado.get("nombre")
        or resultado.get("etiqueta")
        or "Plan funerario"
    )

    precio_total = format_money_for_text(resultado.get("precio_total"))
    precio_contado = format_money_for_text(resultado.get("precio_contado"))

    cuotas = resultado.get("cuotas_mensuales") or {}
    cuota_preferida = None
    cuotas_texto = ""

    # Caso 1

    if isinstance(cuotas, list):
        for cuota in cuotas:
            if not isinstance(cuota, dict):
                continue
            if to_float(cuota.get("plazo_anos")) == 10:
                cuota_preferida = cuota
                break
                
        if cuota_preferida is None and cuotas:
            cuota_preferida = cuotas[0] if isinstance(cuotas[0], dict) else None
        if isinstance(cuota_preferida, dict):
            plazo = to_float(cuota_preferida.get("plazo_anos"))
            importe = to_float(cuota_preferida.get("cuota_mensual"))
            if plazo is not None and importe is not None:
                plazo_str = str(int(plazo)) if float(plazo).is_integer() else str(plazo)
                importe_str = format_money_for_text(importe)
                cuotas_texto = f"{plazo_str} años: {importe_str}/mes"

    # Caso 2
    elif isinstance(cuotas, dict):
         importe_10 = cuotas.get("10 años")
        if importe_10 is None:
            importe_10 = cuotas.get("10 anos")
        if importe_10 is None:
            importe_10 = cuotas.get("10")

        if importe_10 is not None:
            importe_str = format_money_for_text(importe_10)
            cuotas_texto = f"10 años: {importe_str}/mes"
        elif cuotas:
            primera_clave, primer_valor = next(iter(cuotas.items()))
            importe_str = format_money_for_text(primer_valor)
            cuotas_texto = f"{primera_clave}: {importe_str}/mes"
            
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
    magic_link = crear_url(input_data, resultado)
    cuotas = _normalize_cuotas(resultado.get("cuotas_mensuales"))

    edad = to_int(input_data.get("edad"))
    if edad is not None and edad > 80:
        cuotas = cuotas[:5]

    return {
        "id": str(idx),
        "precio_total": to_float(resultado.get("precio_total")),
        "precio_contado": to_float(resultado.get("precio_contado")),
        "cuotas_mensuales": cuotas,
        "servicios_incluidos": normalize_list_of_lines(resultado.get("servicios_incluidos")),
        "avisos": resultado.get("avisos") if isinstance(resultado.get("avisos"), list) else [],
        "cta": {
            "label": "Solicita tu plan funerario",
            "action": magic_link,
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


def normalizar_respuesta_pricing(state: Dict[str, Any]) -> Dict[str, Any]:
    api_response = state.get("api_response")
    api_error = state.get("api_error")
    api_status = state.get("api_status")
    datos = state.get("datos") or {}

    if api_error or not isinstance(api_response, dict):
        return {
            **state,
            "pricing_normalized": {
                "ok": False,
                "api_status": api_status,
                "error": api_error or "INVALID_API_RESPONSE",
                "message": "No se pudo normalizar la respuesta de pricing.",
                "input": {
                    "codigo_postal": clean_text(datos.get("codigo_postal")),
                    "edad": to_int(datos.get("edad")),
                    "paquete": clean_text(datos.get("paquete")),
                    "destino_final": clean_text(datos.get("destino_final")),
                    "velatorio": datos.get("velatorio"),
                    "ceremonia": datos.get("ceremonia"),
                },
                "quotes": [],
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

    if isinstance(api_response.get("resultados"), list):
        raw_results = [
            r for r in api_response.get("resultados", [])
            if isinstance(r, dict)
        ]

        preferred_results = _pick_preferred_resultados(raw_results)

        input_data = {
            "edad": to_int(api_response.get("edad")) or to_int(datos.get("edad")),
            "codigo_postal": clean_text(api_response.get("codigo_postal")) or clean_text(datos.get("codigo_postal")),
            "destino_final": clean_text(api_response.get("destino_final")) or clean_text(datos.get("destino_final")),
            "velatorio": datos.get("velatorio"),
            "ceremonia": datos.get("ceremonia"),
            "paquete": clean_text(api_response.get("paquete")),
        }

        quotes = [
            _normalize_resultado(r, input_data, idx=i + 1)
            for i, r in enumerate(preferred_results)
        ]

        normalized = {
            "ok": success,
            "api_status": api_status,
            "error": None if success else api_error,
            "message": clean_text(api_response.get("mensaje")),
            "input": {
                "codigo_postal": input_data["codigo_postal"],
                "edad": input_data["edad"],
                "paquete": input_data["paquete"],
                "destino_final": input_data["destino_final"],
                "velatorio": input_data["velatorio"],
                "ceremonia": input_data["ceremonia"],
            },
            "quotes": quotes,
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": len(quotes),
                "requiere_contacto_asesor": bool(api_response.get("requiere_contacto_asesor")),
                "numero_clientes": 1,
                "presupuestos_generados": 1,
            },
        }

        return {**state, "pricing_normalized": normalized}

    if isinstance(api_response.get("presupuestos"), list):
        all_quotes: List[Dict[str, Any]] = []

        for presupuesto_idx, presupuesto in enumerate(api_response.get("presupuestos", []), start=1):
            if not isinstance(presupuesto, dict):
                continue

            resultados = presupuesto.get("resultados") or []
            resultados_filtrados = _pick_preferred_resultados(resultados)

            input_data = {
                "edad": to_int(presupuesto.get("edad")) or to_int(datos.get("edad")),
                "codigo_postal": clean_text(presupuesto.get("codigo_postal")) or clean_text(datos.get("codigo_postal")),
                "destino_final": clean_text(presupuesto.get("destino_final")) or clean_text(datos.get("destino_final")),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
                "paquete": clean_text(presupuesto.get("paquete")),
            }

            quotes = [
                {
                    **_normalize_resultado(r, input_data, idx=i + 1),
                    "persona_numero": to_int(presupuesto.get("persona_numero")) or presupuesto_idx,
                }
                for i, r in enumerate(resultados_filtrados)
                if isinstance(r, dict)
            ]

            all_quotes.extend(quotes)

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
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": len(all_quotes),
                "requiere_contacto_asesor": any(
                    bool(p.get("requiere_contacto_asesor"))
                    for p in api_response.get("presupuestos", [])
                    if isinstance(p, dict)
                ),
                "numero_clientes": to_int(api_response.get("numero_clientes")),
                "presupuestos_generados": to_int(api_response.get("presupuestos_generados")) or len(api_response.get("presupuestos", [])),
            },
        }

        return {**state, "pricing_normalized": normalized}

    return {
        **state,
        "pricing_normalized": {
            "ok": False,
            "api_status": api_status,
            "error": api_error or "UNRECOGNIZED_API_RESPONSE",
            "message": clean_text(api_response.get("mensaje")),
            "input": {
                "codigo_postal": clean_text(datos.get("codigo_postal")),
                "edad": to_int(datos.get("edad")),
                "paquete": clean_text(datos.get("paquete")),
                "destino_final": clean_text(datos.get("destino_final")),
                "velatorio": datos.get("velatorio"),
                "ceremonia": datos.get("ceremonia"),
            },
            "quotes": [],
            "summary": {
                "mensaje": clean_text(api_response.get("mensaje")),
                "total_resultados": 0,
                "requiere_contacto_asesor": False,
                "numero_clientes": None,
                "presupuestos_generados": 0,
            },
        },
    }

