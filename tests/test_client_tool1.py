import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from dotenv import load_dotenv

SERVER_URL = "http://localhost:8080/mcp"

async def main():
    async with streamable_http_client(SERVER_URL) as transport:
        read_stream, write_stream, *_ = transport

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            # ---------- TEST 1: UNA PERSONA ----------
            payload_single = {
                "personas": [
                    {
                        "codigo_postal": "28001",
                        "edad": 55,
                        "tipo_funeral": "inhumacion",
                        "velatorio": True,
                        "ceremonia": False
                    }
                ]
            }

            print("\n--- CALL SINGLE PERSON ---")
            result = await session.call_tool("pricing_api", payload_single)
            print(result.content)


            # ---------- TEST 2: VARIAS PERSONAS ----------
            payload_multi = {
                "personas": [
                    {
                        "codigo_postal": "08005",
                        "edad": 55,
                        "tipo_funeral": "incineracion",
                        "velatorio": True,
                        "ceremonia": False
                    },
                    {
                        "codigo_postal": "08005",
                        "cp_servicio": "08005",
                        "edad": 65,
                        "tipo_funeral": "inhumacion",
                        "velatorio": False,
                        "ceremonia": False
                    }
                ]
            }

            print("\n--- CALL MULTI PERSON ---")
            result = await session.call_tool("pricing_api", payload_multi)
            print(result.content)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())