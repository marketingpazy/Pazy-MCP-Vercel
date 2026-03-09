import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SERVER_URL = "http://127.0.0.1:8000/mcp"

async def main():
    async with streamable_http_client(SERVER_URL) as transport:
        # streamable_http_client devuelve 3 cosas (read, write, get_session_id)
        read_stream, write_stream, *_ = transport

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "get_context",
                {"query": "Qué cubre el seguro y cómo funciona?", "k": 3},
            )
            print("\nRESULT:")
            print(result.content)

if __name__ == "__main__":
    asyncio.run(main())