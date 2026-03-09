import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dotenv import load_dotenv

SERVER_URL = "http://localhost:8000/mcp"
SERVER_URL_2 = "https://rochester-array-cork-salvation.trycloudflare.com/mcp"

async def main():
    async with streamable_http_client(SERVER_URL) as transport:
        read_stream, write_stream, *_ = transport

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            # Datos de ejemplo (ajusta si tu API requiere valores concretos)
            payload = {
                "codigo_postal": "28001",
                "edad": 55,
                "tipo_funeral": "inhumacion", 
                "velatorio": True,
                "ceremonia": False,
            }

            # 4 intentos para verificar el límite (3 éxitos máximo)
            for i in range(1, 2):
                print(f"\n--- CALL #{i} ---")
                result = await session.call_tool("pricing_api", payload)
                print(result.content)

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())