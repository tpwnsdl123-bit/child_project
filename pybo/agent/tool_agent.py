import json
import re
from pybo.agent.tool_client import ToolClient

class ToolAgent:
    """도구를 사용하여 자율적으로 사고하고 답변하는 에이전트 엔진"""
    
    def __init__(self, llm_callback, max_iterations: int = 3):
        """
        :param llm_callback: LLM을 호출할 수 있는 콜백 함수 (instruction, input -> response)
        :param max_iterations: 최대 루프 반복 횟수
        """
        self.tool_client = ToolClient()
        self.llm_callback = llm_callback
        self.max_iterations = max_iterations

    def run(self, query: str, instruction: str, history=None) -> str:
        """사용자의 질문에 대해 에이전트 루프를 실행합니다."""
        context = ""
        if history:
            context = "### 대화 기록 (History):\n" + "\n".join(history[-4:]) + "\n\n"
        
        current_chain = f"{context}사용자 질문: {query}\n"
        
        for i in range(self.max_iterations):
            # LLM 호출 - 접두어를 주어 ReAct 유도
            llm_input = f"{current_chain}\nThought: "
            response_text = self.llm_callback(instruction, llm_input) or ""
            
            # 모델이 아무것도 답변하지 않는 경우 (예: Thought: 뒤가 비어있음)
            if not response_text.strip():
                print(f"[Warning] Empty LLM response in loop {i+1}. Nudging...")
                current_chain += f"\nThought: (이곳에 질문에 대한 분석을 적거나 바로 답변하십시오.)"
                continue

            # 모델이 자체적으로 'Thought:'를 포함해서 답하는 경우 처리
            if response_text.lstrip().startswith("Thought:"):
                response = response_text.strip()
            else:
                response = "Thought: " + response_text.strip()
            
            # 할루시네이션 방지: 모델이 Observation: 혹은 다음 질문을 지어내면 잘라냄
            # '### Input:' 등 불필요한 흔적 추가 제거
            for stop_word in ["Observation:", "사용자 질문:", "질문:", "Q:", "A:", "### Input:", "###"]:
                if stop_word in response:
                    response = response.split(stop_word)[0].strip()

            print(f"[ToolAgent Loop {i+1}] LLM Response:\n{response}")
            
            # 1. 최종 답변 확인
            if "Final Answer:" in response:
                ans = response.split("Final Answer:")[1].strip()
                # 임무상황(보고서/정책)이 아닐 때는 짧은 답변도 허용
                is_mission = "지시상황" in query or "임무" in query
                if not is_mission and len(ans) > 0:
                    return ans
                
                # 답변 내용이 너무 부실하거나 빈 경우 (QA 루프 방지)
                if len(ans) < 5:
                    print("[Warning] Final Answer is too short. Requesting substance.")
                    current_chain += f"\n{response}\n시스템: 'Final Answer:' 뒤에 실질적이고 구체적인 답변 내용을 한국어로 작성하십시오."
                    continue
                return ans

            # 2. 일반 QA에 대한 암시적 답변 허용 (Report/Policy 임무가 아닐 때만)
            if "Action:" not in response:
                if "지시상황" not in query and "임무" not in query:
                    clean_ans = response.replace("Thought:", "").strip()
                    # 모델이 '시스템:' 지침을 앵무새처럼 따라하지 않았는지 확인
                    if len(clean_ans) > 2 and "시스템:" not in clean_ans:
                        print("[Info] Detected implicit answer for general QA. Returning...")
                        return clean_ans
            
            # 3. Action 파싱 및 도구 실행
            try:
                if "Action:" in response:
                    tool_name, tool_input = self._parse_action(response)
                    
                    print(f"--- [Agent Action EXEC] {tool_name}({tool_input}) ---")
                    observation = self.tool_client.call_tool(tool_name, tool_input)
                    
                    # 결과를 체인에 추가하고 다음 Thought 유도
                    current_chain += f"\n{response}\nObservation: {observation}\n"
                else:
                    # 루프 마지막인데도 Action/Final Answer가 없으면 본문을 답변으로 간주
                    if i == self.max_iterations - 1:
                        # 인사말 등에서 시스템 지침이 섞여나가지 않게 필터링
                        final_text = response.replace("Thought:", "").strip()
                        if "시스템:" in final_text:
                            final_text = final_text.split("시스템:")[0].strip()
                        return final_text
                    
                    # 형식을 지키도록 재요구 (더 구체적으로 표현)
                    current_chain += f"\n{response}\n시스템: 다음 단계는 'Action: <도구명>'과 'Action Input: {{...}}'를 사용하여 도구를 호출하거나, 'Final Answer: <답변>'으로 마무리하는 것입니다."
            except Exception as e:
                print(f"[ToolAgent Error] {e}")
                current_chain += f"\n{response}\nObservation: 오류 발생({str(e)}). 한 번에 하나의 Action만 JSON 형식으로 제출하십시오.\n"

        return "미안해, 답변을 생성하는 데 실패했어. 다시 한번 물어봐 줄래?"

    def _parse_action(self, response: str) -> tuple:
        """LLM의 응답에서 첫 번째 도구 이름과 인자를 정규표현식으로 정교하게 추출합니다."""
        # Action: 뒤의 도구명 추출
        action_match = re.search(r"Action:\s*(\w+)", response)
        if not action_match:
            raise ValueError("응답에서 Action 도구명을 찾을 수 없습니다.")
        tool_name = action_match.group(1).strip()

        # Action Input: 뒤의 JSON 블록 추출
        # Llama3가 여러 개의 JSON을 출력하는 경우를 대비해 첫 번째 블록만 추출
        if "Action Input:" not in response:
            raise ValueError("Action Input 항목을 찾을 수 없습니다.")
            
        content_after_action = response.split("Action Input:")[1]
        
        # 중괄호 균형을 맞춰서 첫 번째 완결된 JSON 블록 찾기
        brace_count = 0
        json_start = -1
        json_end = -1
        
        for i, char in enumerate(content_after_action):
            if char == '{':
                if brace_count == 0:
                    json_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_start == -1 or json_end == -1:
            raise ValueError("Action Input에서 유효한 JSON 중괄호 블록을 찾을 수 없습니다.")
            
        json_str = content_after_action[json_start:json_end].strip()
        
        try:
            # 큰 따옴표 교체 (Llama3 실수 보정)
            if "'" in json_str and '"' not in json_str:
                json_str = json_str.replace("'", '"')
            return tool_name, json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f"JSON 파싱 실패: {json_str}")
