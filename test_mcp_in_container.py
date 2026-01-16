import os
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = os.getenv("MCP_URL", "http://host.docker.internal:8000/mcp")

async def main():
    print("MCP_URL:", MCP_URL)

    async with streamable_http_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            res = await session.call_tool("rag_search", {"question": "운영비 지원 기준 알려줘"})
            text = res.content[0].text if res.content else "(empty)"
            print("RAG:", text[:300])

asyncio.run(main())
