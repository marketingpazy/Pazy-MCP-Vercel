from typing import Dict, Any

TIPIFICADOS = [
    "ceremonia",
    "urna_biodegradable",
    "pieza_floral",
    "piezas_florales_adicionales",
    "catering",
    "recordatorios",
]

def tratar_datos(state: Dict[str, Any]) -> Dict[str, Any]:
    datos = state.get("datos", {}) or {}

    cp = str(datos.get("codigo_postal", "")).strip()
    edad = datos.get("edad", None)
    destino_final = (datos.get("destino_final") or "").strip().lower()

    velatorio = str(datos.get("velatorio")).strip().lower()
    ceremonia = str(datos.get("ceremonia")).strip().lower()

    if velatorio == "false":
        paquete = "eco"
    elif velatorio == "true" and ceremonia == "false":
        paquete = "estandar"
    else:
        paquete = "premium"

    # extras tipificados (si no los tienes aún, todos false)
    extras_in = datos.get("extras") or {}
    extras_tipificados = {k: bool(extras_in.get(k, False)) for k in TIPIFICADOS}

    msg_post = {
        "codigo_postal": cp,
        "paquete": paquete,  # eco/estandar
        "destino_final": destino_final,  # incineracion/inhumacion
        "edad": int(edad) if edad is not None else None,
        "extras_tipificados": extras_tipificados,
        "extras_euros": 0,
        "kilometraje_km": 0,
    }

    state["msg_post"] = msg_post
    return state