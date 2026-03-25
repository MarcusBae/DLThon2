# narrative_agent.py
"""LangGraph implementation for narrative node generation following the router-centric design."""

import os
from typing import TypedDict, List, Annotated, Dict, Any, Optional, Literal, Union
import operator
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
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
    messages: Annotated[List[AnyMessage], add_messages] 
    
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
    
    # 1) 데이터 로드 (실제 파일 경로 기반)
    data_dir = "./data"
    master_data = {
        "worldview": load_worldview(os.path.join(data_dir, "created_worldview.json")),
        "characters": load_characters(os.path.join(data_dir, "created_character.json")),
        "plot_nodes": load_plot(os.path.join(data_dir, "created_plot.json"))
    }
    idea_note = load_json(os.path.join(data_dir, "idea_note.json"))
    
    # 2) 워크플로우 로드 (예시로 S1-Step1로 설정)
    workflow_data = load_json(os.path.join(data_dir, "workflow_data.json"))
    try:
        current_section = f"{workflow_data['sections'][0].get('section_id', '')}의 step_num:1"
    except (KeyError, IndexError):
        current_section = "unknown section"
    
    return {
        "master_data": master_data,
        "idea_note": idea_note if isinstance(idea_note, list) else [],
        "current_section": current_section,
        "is_section_complete": False,
        "next_node": "router" # 기본적으로 라우터로 전달
    }

def generator_node(state: NarrativeGraphState):
    """
    LLM을 사용하여 응답을 생성하는 노드.
    design.md의 4번 단계에 해당합니다.
    """
    print("--- [generator_node] Researching and generating response ---")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    # 워크플로우 로드하여 현재 섹션 정보 찾기
    data_dir = "./data"
    workflow_data = load_json(os.path.join(data_dir, "workflow_data.json"))
    if isinstance(workflow_data, dict):
        persona = workflow_data.get("agent_persona", {"identity": "스토리 작가", "core_role": "창작 보조"})
    else:
        persona = {"identity": "스토리 작가", "core_role": "창작 보조"}
    
    instr = f"현재 진행 단계: {state.get('current_section', '알 수 없음')}"
    
    worldview_id = getattr(state.get('master_data', {}).get('worldview'), 'world_id', '미정')
    characters = getattr(state.get('master_data', {}).get('characters'), 'characters', [])
    char_names = [c.name for c in characters] if characters else []

    user_context = f"현재 세계관: {worldview_id}, " \
                   f"참여 캐릭터: {char_names}"
    
    system_msg = SystemMessage(content=f"""
    당신의 정체성: {persona.get('identity', '기본 정체성')}
    역할: {persona.get('core_role', '기본 역할')}
    
    현재 지침: {instr}
    현재 창작 맥락: {user_context}
    
    사용자의 요청에 따라 창작을 진행하세요. 
    인터뷰 스타일(한 번에 하나씩 질문)을 유지하며, 사용자의 답변을 구조화하여 제안하세요.
    """)
    
    response = llm.invoke([system_msg] + state.get("messages", []))
    
    return {
        "messages": [response],
        "next_node": "response_check"
    }

def update_node(state: NarrativeGraphState):
    """
    사용자의 요청에 따라 JSON 데이터를 업데이트하는 노드.
    design.md의 6번 단계에 해당합니다.
    """
    print("--- [update_node] Updating user data ---")
    # 예시: 젠(Generator)에서 특정 캐릭터 정보가 확정되었다고 판단되면 파일로 저장
    # 여기서는 간단히 로직의 존재만 기술 (실제 구현 시 LLM이 추출한 entity를 parsing하여 save_ 함수 호출)
    
    return {"next_node": "router"}

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
    생성된 답변이 요구사항을 충족하는지 검증하는 노드.
    design.md의 7번 단계에 해당합니다.
    """
    print("--- [response_check_node] Validating generated response ---")
    
    # 간단한 키워드 기반 검증 (실제로는 LLM 검증기 사용 추천)
    is_valid = True
    feedback = ""
            
    return {
        "validation_status": {"is_valid": is_valid, "violation_rate": 0.0, "errors": [feedback] if feedback else []},
        "next_node": "END" if is_valid else "router"
    }

# ==========================================
# 3. 라우팅 로직 (Routing Logic)
# ==========================================

def router_logic(state: NarrativeGraphState):
    """
    어떤 노드로 분기할지 결정하는 조건부 엣지 함수.
    """
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
    
    builder.add_edge("generator", "response_check")
    
    builder.add_conditional_edges(
        "response_check",
        lambda x: "END" if x.get("validation_status", {}).get("is_valid", False) else "generator",
        {
            "END": END,
            "generator": "generator"
        }
    )
    
    builder.add_edge("update", "generator") # 업데이트 후 다시 생성/응답
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
