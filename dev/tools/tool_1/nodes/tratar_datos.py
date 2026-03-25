from typing import Any, Dict
import unicodedata
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


def remove_accents(text: str) -> str:
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

def _paquete_desde_flags(velatorio: Any) -> str:
    if velatorio == "false" :
        return "eco"
    return "estandar"

def tratar_datos(state: Dict[str, Any]) -> Dict[str, Any]:
    datos = state.get("datos", {}) or {} 

    cp = str(datos.get("codigo_postal", "")).strip() 
    edad = datos.get("edad", None) 
    raw_destino = (datos.get("destino_final") or "").strip()
    destino_final = remove_accents(raw_destino).lower()
    velatorio = str(datos.get("velatorio")).strip().lower() 
    ceremonia = str(datos.get("ceremonia")).strip().lower()
    
    paquete = _paquete_desde_flags(velatorio)
    
    # extras tipificados 
    extras_in = datos.get("extras") or {} 
    if ceremonia == "true":
        extras_in = {"ceremonia": True}

    extras_tipificados = {k: bool(extras_in.get(k, False)) for k in TIPIFICADOS} 
    msg_post = { 
        "codigo_postal": cp, 
        "paquete": paquete, 
        "destino_final": destino_final, 
        "edad": int(edad) if edad is not None else None, 
        "extras_tipificados": extras_tipificados, 
        "extras_euros": 0, 
        "kilometraje_km": 0, 
        } 
    
    state["msg_post"] = msg_post 
    return state