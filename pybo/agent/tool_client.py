import asyncio
import os
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

class ToolClient:
    """MCP 서버와 통신하며 도구를 호출하는 전담 클라이언트"""
    
    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")

    async def call_tool_async(self, tool_name: str, arguments: dict) -> str:
        """비동기 방식으로 MCP 도구를 호출합니다."""
        try:
            async with streamable_http_client(self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return result.content[0].text if result.content else "결과 없음"
        except Exception as e:
            return f"MCP 도구 호출 오류 ({tool_name}): {str(e)}"

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """동기 방식으로 MCP 도구를 호출합니다. (GenAIService 등에서 사용)"""
        return asyncio.run(self.call_tool_async(tool_name, arguments))
