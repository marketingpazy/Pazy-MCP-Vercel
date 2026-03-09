from mcp.server.fastmcp import Context
from typing import Any, Dict, Optional

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


