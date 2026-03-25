import os
import json
import requests
from typing import Dict, Any



def llamada_api(state: Dict[str, Any]) -> Dict[str, Any]:
    msg_post = state.get("msg_post")
    if not msg_post:
        state["api_error"] = "Falta msg_post en state"
        return state

    api_url = os.getenv("API_PAZY_URL")
    api_key = os.getenv("PAZY_API_KEY")

    if not api_key:
        state["api_error"] = "Falta PAZY_API_KEY en variables de entorno"
        return state

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.post(api_url, headers=headers, json=msg_post, timeout=30)
        print(f"[llamada_api] status={resp.status_code}")

        state["api_status"] = resp.status_code
        # intenta parsear json si procede
        try:
            state["api_response"] = resp.json()
        except Exception:
            state["api_response"] = resp.text

    except Exception as e:
        state["api_error"] = repr(e)

    return state