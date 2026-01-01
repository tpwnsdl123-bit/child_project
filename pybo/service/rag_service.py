import os
import json
from typing import Dict, Any, Optional
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

class RagService:
    def __init__(self):
        self.persist_directory = "data/chroma_db"
        self.jsonl_path = "data/jsonl/rag_data.jsonl"

        self.embeddings = HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
            model_kwargs={'device': 'cpu'}
        )

        self.vector_db = self._prepare_vector_db()

    def _prepare_vector_db(self):
        if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
            return Chroma(persist_directory=self.persist_directory, embedding_function=self.embeddings)

        if not os.path.exists(self.jsonl_path):
            return None

        documents = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)
                doc_name = data.get('doc', '')

                doc_type = "etc"
                if "복지법" in doc_name:
                    doc_type = "law"
                elif "지원사업" in doc_name:
                    doc_type = "support"
                elif "인건비" in doc_name:
                    doc_type = "salary"

                combined_text = (
                    f"문서: {doc_name}\n"
                    f"항목: {data.get('section', '')}\n"
                    f"규칙: {data.get('rule', '')}\n"
                    f"수치: {data.get('numeric', '')}\n"
                    f"근거: {data.get('basis', '')}"
                )

                doc = Document(
                    page_content=combined_text,
                    metadata={
                        "doc_type": doc_type,
                        "doc": doc_name,
                        "basis": data.get("basis", "")
                    }
                )
                documents.append(doc)

        # 문서가 하나도 없을 경우 에러 방지 처리
        if not documents:
            return None

        return Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )

    # 인스턴스 변수를 사용하지 않으므로 정적 메서드로 전환하여 린터 경고 해결
    @staticmethod
    def _route_doc_type(question: str) -> Optional[str]:
        q = (question or "").lower()
        if any(k in q for k in ["인건비", "급여", "호봉", "수당", "보수", "연봉", "돈", "월급"]):
            return "salary"
        if any(k in q for k in ["지원", "보조금", "운영비", "배치기준", "정원", "시설장", "생활복지사"]):
            return "support"
        if any(k in q for k in ["법", "조문", "시행령", "시행규칙", "아동복지법"]):
            return "law"
        return None

    def get_relevant_context(self, question: str) -> str:
        if not self.vector_db:
            return "참조할 수 있는 운영 지침 데이터가 없습니다."

        doc_type = self._route_doc_type(question)

        # MMR 대신 속도가 빠른 similarity 검색 사용
        search_kwargs: Dict[str, Any] = {"k": 3}  # 검색 결과 개수를 3개로 최적화

        if doc_type:
            search_kwargs["filter"] = {"doc_type": doc_type}

        # search_type을 similarity로 변경하여 연산 속도 향상
        retriever = self.vector_db.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs
        )

        # 랭체인 invoke 메서드 사용
        docs = retriever.invoke(question)

        lines = []
        for d in docs:
            src = d.metadata.get("doc", "알 수 없음")
            lines.append(f"[출처: {src}]\n{d.page_content}")

        return "\n\n---\n\n".join(lines)