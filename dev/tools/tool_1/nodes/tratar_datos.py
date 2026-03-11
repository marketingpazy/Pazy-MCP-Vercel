from typing import Any, Dict

from typing import Any, Dict, List


TIPIFICADOS = [
    "ceremonia",
    "urna_biodegradable",
    "pieza_floral",
    "piezas_florales_adicionales",
    "catering",
    "recordatorios",
    "repatriación",
]


def _bool_to_api(value: Any) -> str:
    return "true" if bool(value) else "false"


def _paquete_desde_flags(velatorio: Any, ceremonia: Any) -> str:
    velatorio_bool = bool(velatorio)
    ceremonia_bool = bool(ceremonia)

    if not velatorio_bool:
        return "eco"
    if velatorio_bool and not ceremonia_bool:
        return "estandar"
    return "premium"


def _normalize_persona(persona: Dict[str, Any]) -> Dict[str, Any]:
    codigo_postal = str(persona.get("codigo_postal", "")).strip()
    cp_servicio = str(persona.get("cp_servicio", codigo_postal) or codigo_postal).strip()
    edad = int(persona["edad"])
    destino_final = str(persona.get("tipo_funeral", "")).strip().lower()

    velatorio = bool(persona.get("velatorio", False))
    ceremonia = bool(persona.get("ceremonia", False))

    extras_in = persona.get("extras") or {}

    extras_tipificados = {
        k: bool(extras_in.get(k, False))
        for k in TIPIFICADOS
    }

    # ceremonia puede venir de flag principal o de extras
    if "ceremonia" not in extras_in:
        extras_tipificados["ceremonia"] = ceremonia

    paquete = str(persona.get("paquete") or _paquete_desde_flags(velatorio, ceremonia)).strip().lower()

    return {
        "codigo_postal": codigo_postal,
        "cp_servicio": cp_servicio,
        "paquete": paquete,
        "destino_final": destino_final,
        "edad": edad,
        "velatorio": velatorio,
        "ceremonia": ceremonia,
        "extras_tipificados": extras_tipificados,
    }


def _build_pricing_payload(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    personas_norm = [_normalize_persona(p) for p in personas]

    return {
        "codigo_postal": ",".join(p["codigo_postal"] for p in personas_norm),
        "cp_servicio": ",".join(p["cp_servicio"] for p in personas_norm),
        "paquete": ",".join(p["paquete"] for p in personas_norm),
        "destino_final": ",".join(p["destino_final"] for p in personas_norm),
        "edad": ",".join(str(p["edad"]) for p in personas_norm),
        "extras_tipificados": {
            "ceremonia": ",".join(_bool_to_api(p["extras_tipificados"]["ceremonia"]) for p in personas_norm),
            "urna_biodegradable": ",".join(_bool_to_api(p["extras_tipificados"]["urna_biodegradable"]) for p in personas_norm),
            "pieza_floral": ",".join(_bool_to_api(p["extras_tipificados"]["pieza_floral"]) for p in personas_norm),
            "piezas_florales_adicionales": ",".join(_bool_to_api(p["extras_tipificados"]["piezas_florales_adicionales"]) for p in personas_norm),
            "catering": ",".join(_bool_to_api(p["extras_tipificados"]["catering"]) for p in personas_norm),
            "recordatorios": ",".join(_bool_to_api(p["extras_tipificados"]["recordatorios"]) for p in personas_norm),
            "repatriación": ",".join(_bool_to_api(p["extras_tipificados"]["repatriación"]) for p in personas_norm),
        },
        "extras_euros": 0,
        "kilometraje_km": 0,
        "inmediata": False,
    }

def tratar_datos(state: Dict[str, Any]) -> Dict[str, Any]:
    datos = state.get("datos", {}) or {}

    personas = datos.get("personas")
    
    # Compatibilidad hacia atrás: si todavía llega una sola persona en formato antiguo
    if not personas:
        cp = str(datos.get("codigo_postal", "")).strip()
        edad = datos.get("edad", None)
        destino_final = (datos.get("tipo_funeral") or "").strip().lower()
        velatorio = bool(datos.get("velatorio", False))
        ceremonia = bool(datos.get("ceremonia", False))

        personas = [
            {
                "codigo_postal": cp,
                "cp_servicio": cp,
                "edad": int(edad) if edad is not None else None,
                "destino_final": destino_final,
                "velatorio": velatorio,
                "ceremonia": ceremonia,
                "extras": datos.get("extras") or {},
            }
        ]

    # Validación mínima
    personas_filtradas = []
    for idx, p in enumerate(personas, start=1):
        try:
            if p.get("edad") is None:
                raise ValueError(f"Falta edad en persona {idx}")
            if not str(p.get("codigo_postal", "")).strip():
                raise ValueError(f"Falta codigo_postal en persona {idx}")
            if not str(p.get("tipo_funeral", "")).strip():
                raise ValueError(f"Falta tipo_funeral en persona {idx}")

            personas_filtradas.append(p)
        except Exception as e:
            state["api_error"] = str(e)
            return state

    msg_post = _build_pricing_payload(personas_filtradas)
    state["msg_post"] = msg_post

    return state