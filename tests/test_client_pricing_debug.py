import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_URL = "http://localhost:8080/mcp"
TOOL_NAME = "pricing_api"
OUTPUT_PATH = Path("public/pricing-widget.sample.json")

PAYLOAD = {
    "personas": [
        {
            "codigo_postal": "15005",
            "cp_servicio": "15005",
            "edad": 60,
            "tipo_funeral": "incineracion",
            "velatorio": True,
            "ceremonia": False,
        },
        {
            "codigo_postal": "15005",
            "cp_servicio": "15005",
            "edad": 75,
            "tipo_funeral": "inhumacion",
            "velatorio": True,
            "ceremonia": False,
        }
    ]
}


def stringify_content_items(items) -> list[str]:
    output = []
    for item in items or []:
        item_type = getattr(item, "type", None)
        if item_type == "text":
            output.append(getattr(item, "text", ""))
        else:
            output.append(repr(item))
    return output


async def main() -> None:
    load_dotenv()

    async with streamable_http_client(SERVER_URL) as transport:
        read_stream, write_stream, *_ = transport
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            print(f"\n--- CALL {TOOL_NAME} ---")
            print("Payload:")
            print(json.dumps(PAYLOAD, ensure_ascii=False, indent=2))

            result = await session.call_tool(TOOL_NAME, PAYLOAD)

            structured = getattr(result, "structuredContent", None)
            if structured is None and isinstance(result, dict):
                structured = result.get("structuredContent")

            print("\nTexto devuelto por la tool:")
            for chunk in stringify_content_items(getattr(result, "content", None)):
                print(chunk)

            if structured is None:
                print("\nNo se encontró structuredContent en la respuesta.")
                print("Representación completa del resultado:")
                print(repr(result))
                return

            normalized = structured
            if isinstance(structured, dict):
                normalized = (
                    structured.get("result", {}).get("structuredContent")
                    or structured
                )

            wrapper = {
                "structuredContent": normalized,
                "_debug": {
                    "server_url": SERVER_URL,
                    "tool_name": TOOL_NAME,
                    "payload": PAYLOAD,
                },
            }

            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(
                json.dumps(wrapper, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print("\nstructuredContent exportado a:")
            print(OUTPUT_PATH.resolve())
            print("\nAbre el widget local así:")
            print("python -m http.server 9000")
            print("http://localhost:9000/public/pricing-widget.html?debug=1")


if __name__ == "__main__":
    asyncio.run(main())
