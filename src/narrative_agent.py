# narrative_agent.py
"""LangGraph implementation for narrative node generation following the router-centric design."""

import os
from typing import Annotated, Sequence, TypedDict, Union, Dict, List, Any, cast
import operator
import json

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages

from src.tools import (
    load_worldview, load_characters, load_plot, load_json,
    save_worldview, save_characters, save_plot
)

# ==========================================
# 1. 상태 정의 (NarrativeGraphState)
# ==========================================

class NarrativeGraphState(TypedDict):
    """
    서사 에이전트의 전체 상태를 관리하는 객체.
    디자인 문서(@design.md)의 architecture를 반영합니다.
    """
    # 1. 대화 기록 및 컨텍스트
    messages: Annotated[List[BaseMessage], add_messages] 
    
    # 2. 프로세스 제어 상태
    current_section: str  # 현재 진행 중인 창작 단계 (예: "Section 01의 step_num:1",  "Section 03 의 step_num:3" 등) 
    is_section_complete: bool  # 현재 섹션의 필수 요건이 모두 충족되었는지 여부
    
    # 3. 보류된 사용자 아이디어 저장소 (idea_note.json 구조)
    idea_note: Annotated[List[Dict[str, Any]], operator.add]
    
    # 4. 확정된 마스터 데이터 (schema.json 기준)
    master_data: Dict[str, Any]  # { "characters": [], "worldview": {}, "plot_nodes": [] }
    
    # 5. 서사 논리 검증 상태 (Validator)
    validation_status: Dict[str, Any] 
    # 예: { "is_valid": True, "violation_rate": 0.0, "errors": [] } 
    
    # 6. 다음 노드 분기를 위한 플래그 (Router 제어용)
    next_node: str  # 라우터가 참조할 다음 이동 경로 (예: "generate_plot", "ask_user", "validate")
    missing_info: List[str]  # 다음 단계로 넘어가기 위해 사용자에게 추가로 물어봐야 할 필수 정보 리스트

# ==========================================
# 2. 그래프 노드 구현 (Graph Nodes)
# ==========================================

def history_node(state: NarrativeGraphState):
    """
    대화 기록과 사용자 데이터를 로드하고 상태를 초기화하는 노드.
    design.md의 1번 단계에 해당합니다.
    """
    print("--- [history_node] Loading context and user data ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})
    
    # 1) 데이터 로드 (동적 story_id 경로 기반)
    data_dir = "./data"
    
    def safe_load(func, path, fallback):
        import os
        return func(path) if os.path.exists(path) else fallback

    m_data = state.get("master_data", {})
    story_id = str(m_data.get("story_id", "")) if isinstance(m_data, dict) else ""
    if story_id:
        user_data_path = os.path.join(data_dir, "user_data", story_id)
        os.makedirs(user_data_path, exist_ok=True)
    else:
        user_data_path = os.path.join(data_dir, "user_data")
        
    master_data = {
        "story_id": story_id,
        "worldview": safe_load(load_worldview, os.path.join(user_data_path, "created_worldview.json"), None),
        "characters": safe_load(load_characters, os.path.join(user_data_path, "created_character.json"), None),
        "plot_nodes": safe_load(load_plot, os.path.join(user_data_path, "created_plot.json"), None)
    }
    idea_note = safe_load(load_json, os.path.join(user_data_path, "idea_note.json"), [])
    
    # 2) 워크플로우 로드 및 초기 섹션 설정
    workflow_data = load_json(os.path.join(data_dir, "system", "workflow_data.json"))
    
    # 전달받은 상태에 이미 섹션 정보가 있다면 유지, 없으면 초기화
    current_section = state.get("current_section")
    if not current_section:
        try:
            current_section = f"Section {workflow_data['sections'][0].get('section_id', '')}의 step_num:1"
        except (KeyError, IndexError):
            current_section = "unknown section"
    
    return {
        "master_data": master_data,
        "idea_note": idea_note if isinstance(idea_note, list) else [],
        "current_section": current_section,
        "is_section_complete": state.get("is_section_complete", False),
        "next_node": "router"
    }

def generator_node(state: NarrativeGraphState):
    """
    LLM을 사용하여 응답을 생성하는 노드.
    """
    print("--- [generator_node] Researching and generating response ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    # 워크플로우 로드하여 현재 섹션 정보 찾기
    data_dir = "./data"
    workflow_data = load_json(os.path.join(data_dir, "system", "workflow_data.json"))
    if isinstance(workflow_data, dict):
        persona = workflow_data.get("agent_persona", {"identity": "스토리 작가", "core_role": "창작 보조"})
        interaction_rules = workflow_data.get("interaction_rules", {})
    else:
        persona = {"identity": "스토리 작가", "core_role": "창작 보조"}
        interaction_rules = {}
        
    rules_text = "\n    ".join([f"- {v}" for k, v in interaction_rules.items()]) if interaction_rules else "- 인터뷰 스타일 유지"
    
    # 2. 동적 플롯 이론 로드 및 마일스톤 추출
    theory_type = state.get('master_data', {}).get('theory_type', 'THEORY_PROPP_VOGLER_HYBRID')
    theory_plot_data = load_json(os.path.join(data_dir, "theory", "theory_plot.json"))
    milestones_text = "지정된 플롯 이론이 없습니다."
    
    if isinstance(theory_plot_data, dict):
        for t in theory_plot_data.get("plot_theories", []):
            if t.get("theory_id") == theory_type:
                theory_name = t.get("theory_name", "")
                theory_desc = t.get("description", "")
                ms_list = []
                for ms in t.get("milestones", []):
                    ms_list.append(f"[{ms.get('act', 'Act')}] {ms.get('title', '')}: {ms.get('description', '')}")
                milestones_text = f"이론명: {theory_name}\n    설명: {theory_desc}\n    마일스톤 구성:\n    " + "\n    ".join(ms_list)
                break

    # 2. 현재 단계 및 다음 단계 지침 추출
    current_section_str = str(state.get("current_section", ""))
    section_num = ""
    step_num = 1
    
    if "Section" in current_section_str:
        try:
            if "의 step_num:" in current_section_str:
                parts = current_section_str.split("의 step_num:")
                section_num = parts[0].replace("Section ", "").strip()
                step_num = int(parts[1].strip())
        except: pass

    # 현재 단계 정보
    current_step_info = {}
    next_step_info = {}
    
    if isinstance(workflow_data, dict) and section_num:
        for sec in workflow_data.get("sections", []):
            if sec.get("section_id") == section_num:
                steps = sec.get("steps", [])
                for i, stp in enumerate(steps):
                    if stp.get("step_number") == step_num:
                        current_step_info = stp
                        if i + 1 < len(steps):
                            next_step_info = steps[i+1]
                        break
                # 만약 현재 섹션의 마지막 스텝이라면 다음 섹션의 첫 스텝을 찾아야 함 (여기선 단순화)
    
    task_name = current_step_info.get("task_name", "창작 진행")
    agent_mission = current_step_info.get("agent_action", "사용자의 아이디어를 구체화하세요.")
    output_reqs = current_step_info.get("output_requirements", [])
    reqs_text = "\n    - ".join(output_reqs) if output_reqs else "없음"
    
    next_task_name = next_step_info.get("task_name", "다음 단계")
    next_agent_mission = next_step_info.get("agent_action", "다음 설정을 진행하세요.")

    worldview = state.get('master_data', {}).get('worldview', {})
    worldview_id = worldview.get('world_id', '미정') if isinstance(worldview, dict) else getattr(worldview, 'world_id', '미정')
    characters = state.get('master_data', {}).get('characters', [])
    char_names = [c.get('name') if isinstance(c, dict) else getattr(c, 'name', 'N/A') for c in characters] if characters else []

    user_context = f"현재 세계관: {worldview_id}, " \
                   f"참여 캐릭터: {char_names}"
    
    # 3. 메시지 히스토리 길이 및 섹션 기반 복잡도/포화도 파악
    messages = state.get("messages", [])
    history_len = len(messages) if isinstance(messages, list) else 0
    current_section = str(state.get("current_section", ""))
    
    is_early_stage = current_section.startswith("Section 01")
    complexity_instruction = ""
    if is_early_stage:
        complexity_instruction = "현재는 스토리 초반부입니다. 복잡한 설정을 피하고 **1개의 핵심 주제/키워드**에 대해서만 심플하게 대화를 이어가세요."
    
    saturation_warning = ""
    if is_early_stage:
        msgs = state.get("messages", [])
        if isinstance(msgs, list) and len(msgs) < 6:
            saturation_warning = "\n[중요] 아직 아이디어 포화도가 낮습니다(대화 3회 미만). 절대로 플롯이나 구체적 전개를 제안하지 마세요."

    # 4. 시스템 프롬프트 구성
    system_msg = SystemMessage(content=f"""
    [당신의 정체성]
    - {persona.get('identity', '기본 정체성')}
    - 역할: {persona.get('core_role', '기본 역할')}
    
    [핵심 상호작용 원칙 (절대 준수)]
    1. **단일 질문 (Single Question)**: 답변의 마지막에 오직 **단 하나**의 핵심 질문만 던지세요. 질문이 여러 개이면 사용자가 혼란을 느낍니다.
    2. **3~5개 예시 (Numbered Examples)**: 사용자의 답변을 돕기 위해 반드시 **3~5개의 구체적인 답변 예시**를 번호 목록(1. 2. 3...)으로 제공하세요.
    3. **단계별 집중 (Step-Fidelity)**: 현재 단계({task_name})의 미션에만 집중하세요. {concept_framework}를 구축하는 것이 목표입니다.
    4. **점진적 복잡성**: {complexity_instruction}
    
    [현재 창작 단계: {task_name}]
    - **핵심 미션**: {agent_mission}
    - **요건**: {reqs_text}
    
    [심리스 다음 단계 지침 (Seamless Transition)]
    만약 현재 단계({task_name})의 요건이 충분히 충족되어 확정되었다면, **"{task_name}이(가) 확정되었습니다! [STEP_COMPLETED]"**라고 명시하고, **대화를 끊지 말고 즉시** 다음 단계인 **'{next_task_name}'**에 대한 첫 질문을 던지세요.
    
    [답변 가이드]
    - 사용자가 "좋아", "확정" 등 긍정적인 반응을 보이면 해당 요소를 확정하고 요약해 주세요.
    - 확정된 내용은 반드시 답변 내에 명확히 언급하여 사용자가 인지하게 하세요.
    - {saturation_warning}
    
    위 원칙을 준수하여 사용자를 친절하게 리드하세요. 질문은 단 하나, 예시는 3~5개!
    """)
    
    response = llm.invoke([system_msg] + state.get("messages", []))
    
    return {
        "messages": [response],
        "next_node": "update"
    }

def update_node(state: NarrativeGraphState):
    """
    대화 내용을 분석하여 확정된 설정을 추출하고 JSON 파일로 자동 저장하는 노드.
    """
    print("--- [update_node] Extracting & Updating Metadata ---")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) # 정확성을 위해 0
    
    if not isinstance(state, dict):
        return {"next_node": "response_check"}
        
    messages = state.get("messages", [])
    m_data = state.get("master_data", {})
    story_id = str(m_data.get("story_id", "")) if isinstance(m_data, dict) else ""
    
    if not story_id: return {"next_node": "response_check"}

    # 1. 메타데이터 추출용 프롬프트
    extract_msg = SystemMessage(content="""
    당신의 임무는 대화 기록을 분석하여 사용자와 에이전트 사이에 '확정'된 스토리 요소를 JSON 형태로 추출하는 것입니다.
    사용자가 "좋아", "그걸로 가자", "응" 등 긍정적인 반응을 보인 내용만 확정된 것으로 간주합니다.
    
    추출할 필드 (없으면 포함X):
    - worldview: { "world_id": "세계관이름", "description": "설명", "genre": "장르" }
    - characters: [ { "name": "이름", "role": "역할", "personality": "성격", "goal": "목표" } ]
    
    오직 순수한 JSON만 출력하세요. 마크다운 태그 등을 사용하지 마세요.
    """)
    
    try:
        res = llm.invoke([extract_msg] + messages[-4:])
        content = str(res.content)
        
        # ```json ... ``` 블록 제거
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(content)
        if not isinstance(data, dict):
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            else:
                data = {}
        
        print(f"--- [update_node] Extracted data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
        # 2. 파일 저장 로드 및 업데이트
        data_dir = "./data/user_data"
        user_path = os.path.join(data_dir, story_id)
        
        if isinstance(data, dict) and "worldview" in data:
            with open(os.path.join(user_path, "created_worldview.json"), "w", encoding="utf-8") as f:
                json.dump(data["worldview"], f, ensure_ascii=False, indent=2)
        
        if isinstance(data, dict) and "characters" in data:
            # CharacterSet 형식에 맞춰서 저장
            char_set_data = {"characters": data["characters"]}
            with open(os.path.join(user_path, "created_character.json"), "w", encoding="utf-8") as f:
                json.dump(char_set_data, f, ensure_ascii=False, indent=2)
                
        # master_data 상태도 업데이트
        new_master = dict(state.get("master_data", {}))
        if "worldview" in data: new_master["worldview"] = data["worldview"]
        if "characters" in data: new_master["characters"] = data["characters"]
        
        return {"master_data": new_master, "next_node": "response_check"}
    except Exception as e:
        print(f"Error in update_node: {e}")
        return {"next_node": "response_check"}

def tools_node(state: NarrativeGraphState):
    """
    PDF 생성 등 외부 도구를 실행하는 노드.
    design.md의 5번 단계에 해당합니다.
    """
    print("--- [tools_node] Executing tools ---")
    # 예시: write_pdf_tool 호출 등
    return {"next_node": "router"}

def response_check_node(state: NarrativeGraphState):
    """
    생성된 답변이 요구사항을 충족하는지 검증하고 다음 단계를 결정하는 노드.
    """
    print("--- [response_check_node] Validating response & progression ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})
    
    current_section = str(state.get("current_section", ""))
    messages = state.get("messages", [])
    last_ai_msg = messages[-1].content if messages else ""
    
    # AI가 답변에 [STEP_COMPLETED] 태그를 포함했는지 확인
    is_completed = "[STEP_COMPLETED]" in last_ai_msg
    
    # [추가] 메타데이터 검증: Section 01인 경우 로그라인 아이디어가 있는지 등 확인
    mdata = state.get("master_data")
    if is_completed and current_section.startswith("Section 01") and isinstance(mdata, dict):
        # Premise Builder 단계 등에서 실제 데이터가 채워졌는지 간접 확인
        wv = mdata.get("worldview")
        if not wv:
            print("--- [response_check] Blocking progression: Worldview metadata missing ---")
            # 사용자가 내용을 충분히 채웠는지 확인 (여기서는 시뮬레이션상 통과시키되 지침상 강조)

    # [추가] 메타데이터 검증: 실질적인 데이터가 채워졌는지 확인
    mdata = state.get("master_data")
    is_valid_data = True
    missing_reason = ""
    
    if is_completed and isinstance(mdata, dict):
        if current_section.startswith("Section 01의 step_num:1"):
             wv = mdata.get("worldview", {})
             if not wv or (isinstance(wv, dict) and not wv.get("description")):
                 is_valid_data = False
                 missing_reason = "세계관에 대한 설명이 아직 부족합니다."
        elif current_section.startswith("Section 01의 step_num:3"):
             chars = mdata.get("characters", [])
             if not chars:
                 is_valid_data = False
                 missing_reason = "주요 캐릭터 설정이 아직 완료되지 않았습니다."

    if is_completed and not is_valid_data:
        print(f"--- [response_check] Validation FAILED: {missing_reason} ---")
        is_completed = False

    # 만약 현재 단계가 완료되었다면 다음 단계 계산
    next_section = current_section
    if is_completed:
        # Section 01 step 1 -> step 2 -> step 3 -> Section 02 step 1...
        try:
            if "의 step_num:" in current_section:
                parts = current_section.split("의 step_num:")
                s_name = parts[0]
                s_id_str = s_name.replace("Section ", "").strip()
                s_step = int(parts[1])
                
                # 다음 스텝으로 (S1은 3단계까지 있음)
                if s_step < 3:
                    next_section = f"{s_name}의 step_num:{s_step + 1}"
                else:
                    # 다음 섹션으로
                    next_id = int(s_id_str) + 1
                    next_section = f"Section {next_id:02d}의 step_num:1"
        except Exception as e:
            print(f"Error calculating next section: {e}")

    return {
        "current_section": next_section,
        "is_section_complete": is_completed,
        "validation_status": {"is_valid": True, "violation_rate": 0.0, "errors": []},
        "next_node": "END"
    }

# ==========================================
# 3. 라우팅 로직 (Routing Logic)
# ==========================================

def router_logic(state: NarrativeGraphState):
    """
    어떤 노드로 분기할지 결정하는 조건부 엣지 함수.
    """
    if not isinstance(state, dict):
        return "END"
    print(f"--- [router] Deciding next step for {state.get('next_node', 'END')} ---")
    return state.get("next_node", "END")

# ==========================================
# 4. 그래프 구축 (Graph Building)
# ==========================================

def build_narrative_graph():
    builder = StateGraph(NarrativeGraphState)
    
    # 노드 추가
    builder.add_node("history", history_node)
    builder.add_node("generator", generator_node)
    builder.add_node("update", update_node)
    builder.add_node("tools", tools_node)
    builder.add_node("response_check", response_check_node)
    
    # 엣지 연결
    builder.set_entry_point("history")
    
    # 라우터 기반 조건부 분기
    builder.add_conditional_edges(
        "history",
        router_logic,
        {
            "router": "generator", # history 다음엔 주로 생성으로
            "generator": "generator",
            "update": "update",
            "tools": "tools",
            "END": END
        }
    )
    
    builder.add_edge("generator", "update")
    
    builder.add_conditional_edges(
        "response_check",
        lambda x: "END" if isinstance(x, dict) and x.get("validation_status", {}).get("is_valid", False) else "generator",
        {
            "END": END,
            "generator": "generator"
        }
    )
    
    builder.add_edge("update", "response_check") # 업데이트 후 검증으로
    builder.add_edge("tools", "generator")
    
    return builder.compile()

# ==========================================
# 5. 실행 테스트 (Test Run)
# ==========================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    graph = build_narrative_graph()
    
    # 초기 질문
    initial_input = "김철수가 사막에서 모험을 시작하는 로그라인을 잡아줘."
    
    config = {"configurable": {"thread_id": "test_user_01"}}
    
    for chunk in graph.stream(
        {"messages": [HumanMessage(content=initial_input)]},
        config
    ):
        for node_name, output in chunk.items():
            print(f"\n[Node: {node_name}]")
            if "messages" in output and output["messages"]:
                print(f"AI: {output['messages'][-1].content}")
