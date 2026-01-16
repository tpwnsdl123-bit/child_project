import os
import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")

class QAState(TypedDict):
    question: str
    pdf_context: str
    answer: str

def _is_greeting(q: str) -> bool:
    greetings = ["안녕", "반가워", "하이", "hello", "hi", "누구"]
    q_low = (q or "").lower()
    return any(g in q_low for g in greetings) and len((q or "").strip()) < 15

async def _call_tool(tool_name: str, args: dict) -> str:
    async with streamable_http_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool_name, arguments=args)
            return res.content[0].text if res.content else ""

async def node_rag(state: QAState) -> QAState:
    state["pdf_context"] = await _call_tool("rag_search", {"question": state["question"]})
    return state

async def node_answer(state: QAState) -> QAState:
    q = state["question"]

    if _is_greeting(q):
        instruction = (
            "너는 서울시 아동복지 정책 전문가이자 친절한 상담사야. "
            "사용자의 인사에 반갑게 화답하고 무엇을 도와줄지 짧고 친절하게 물어봐."
        )
        input_text = f"사용자 질문: {q}"
    else:
        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답변해라. "
            "반드시 제공된 '참조 자료'에 근거해서만 답해라. "
            "참조 자료에 없는 내용은 추측하지 말고 '자료에 없음'이라고 말해라. "
            "질문과 직접 관련 없는 법령/지침은 생략해라. "
            "상담사처럼 친절한 말투(~해요, ~입니다)를 사용해라."
        )
        input_text = f"참조 자료:\n{state['pdf_context']}\n\n질문: {q}"

    state["answer"] = await _call_tool(
        "llama_generate",
        {
            "instruction": instruction,
            "input_text": input_text,
            "model_version": "final",
            "temperature": 0.3,
            "max_new_tokens": 512,
        },
    )
    return state

def build_graph():
    g = StateGraph(QAState)
    g.add_node("rag", node_rag)
    g.add_node("answer", node_answer)
    g.set_entry_point("rag")
    g.add_edge("rag", "answer")
    g.add_edge("answer", END)
    return g.compile()

# Flask에서 동기 함수로 쓰기 쉽게 래핑
_graph = build_graph()

def run_qa(question: str) -> str:
    state = {"question": question, "pdf_context": "", "answer": ""}
    final_state = asyncio.run(_graph.ainvoke(state))
    return final_state["answer"]
