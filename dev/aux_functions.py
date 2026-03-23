from mcp.server.fastmcp import Context
from typing import Any, Dict, Optional, List
import re

CONFIG_PATH = "./dev/.config"

def cfg(key: str, default=None):
    return CONFIG.get(key, default)

def load_config_kv(path: str = CONFIG_PATH) -> Dict[str, str]:
        cfg: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
        return cfg

CONFIG = load_config_kv(CONFIG_PATH)



def clean_text(value: Any) -> Optional[str]:
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

def map_destino_final(value: Any) -> str:
    v = (clean_text(value) or "").lower()
    if v == "incineracion":
        return "cremation"
    if v == "entierro" or v == "inhumacion":
        return "burial"
    return ""


def map_si_no(value: Any) -> str:
    if value is True:
        return "si"
    if value is False:
        return "no"

    v = (clean_text(value) or "").lower()
    if v in {"si", "sí", "true", "1"}:
        return "si"
    if v in {"no", "false", "0"}:
        return "no"
    return ""


def map_pack(value: Any) -> str:
    v = (clean_text(value) or "").lower()
    if v == "eco":
        return "eco"
    if v == "estandar" or v == "estándar" or v == "standard":
        return "standard"
    if v == "premium":
        return "premium"
    return ""


def price_field_for_pack(pack_value: str) -> Optional[str]:
    if pack_value == "eco":
        return "pre_price_eco"
    if pack_value == "standard":
        return "pre_price_standard"
    if pack_value == "premium":
        return "pre_price_premium"
    return None


def format_money_for_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    if float(number).is_integer():
        return f"{int(number)} €"
    return f"{number:.2f} €"


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_list_of_lines(value: Any) -> List[str]:
    """
    Convierte textos tipo:
    "- item 1\n - item 2"
    en ["item 1", "item 2"].
    """
    text = clean_text(value)
    if not text:
        return []

    parts = []
    for line in text.splitlines():
        item = line.strip()
        item = re.sub(r"^[\-\•\*]\s*", "", item).strip()
        if item:
            parts.append(item)
    return parts