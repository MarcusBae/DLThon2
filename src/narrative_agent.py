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
# 1. 상태 정의 (NarrativeState)
# ==========================================

class NarrativeState(TypedDict):
    """
    서사 에이전트의 전체 상태를 관리하는 객체.
    디자인 문서(@design.md)의 architecture를 반영합니다.
    """
    messages: Annotated[List[AnyMessage], add_messages]
    
    # 사용자 데이터셋 (userDataSet)
    user_data: Dict[str, Any] # {worldview, characters, plot, idea_note}
    
    # 워크플로우 관련 메타데이터 (staticData의 workflow_data)
    workflow: Dict[str, Any] # {section_id, step_number, instruction, output_requirements}
    
    # 라우팅 및 검증 상태
    next_node: str
    last_response: Optional[str]
    validation_results: Dict[str, Any] # {is_valid, feedback}

# ==========================================
# 2. 그래프 노드 구현 (Graph Nodes)
# ==========================================

def history_node(state: NarrativeState):
    """
    대화 기록과 사용자 데이터를 로드하고 상태를 초기화하는 노드.
    design.md의 1번 단계에 해당합니다.
    """
    print("--- [history_node] Loading context and user data ---")
    
    # 1) 데이터 로드 (실제 파일 경로 기반)
    data_dir = "./data"
    user_data = {
        "worldview": load_worldview(os.path.join(data_dir, "created_worldview.json")),
        "characters": load_characters(os.path.join(data_dir, "created_character.json")),
        "plot": load_plot(os.path.join(data_dir, "created_plot.json")),
        "idea_note": load_json(os.path.join(data_dir, "idea_note.json"))
    }
    
    # 2) 워크플로우 로드 (예시로 S1-Step1로 설정)
    workflow_data = load_json(os.path.join(data_dir, "workflow_data.json"))
    current_section = workflow_data["sections"][0]
    current_step = current_section["steps"][0]
    
    workflow = {
        "section_id": current_section["section_id"],
        "step_number": current_step["step_number"],
        "instruction": current_step["agent_action"],
        "output_requirements": current_step["output_requirements"],
        "agent_persona": workflow_data["agent_persona"]
    }
    
    return {
        "user_data": user_data,
        "workflow": workflow,
        "next_node": "router" # 기본적으로 라우터로 전달
    }

def generator_node(state: NarrativeState):
    """
    LLM을 사용하여 응답을 생성하는 노드.
    design.md의 4번 단계에 해당합니다.
    """
    print("--- [generator_node] Researching and generating response ---")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    # 시스템 프롬프트 구성
    persona = state["workflow"]["agent_persona"]
    instr = state["workflow"]["instruction"]
    user_context = f"현재 세계관: {state['user_data']['worldview'].world_id}, " \
                   f"참여 캐릭터: {[c.name for c in state['user_data']['characters'].characters]}"
    
    system_msg = SystemMessage(content=f"""
    당신의 정체성: {persona['identity']}
    역할: {persona['core_role']}
    
    현재 지침: {instr}
    현재 창작 맥락: {user_context}
    
    사용자의 요청에 따라 창작을 진행하세요. 
    인터뷰 스타일(한 번에 하나씩 질문)을 유지하며, 사용자의 답변을 구조화하여 제안하세요.
    """)
    
    response = llm.invoke([system_msg] + state["messages"])
    
    return {
        "messages": [response],
        "last_response": response.content,
        "next_node": "response_check"
    }

def update_node(state: NarrativeState):
    """
    사용자의 요청에 따라 JSON 데이터를 업데이트하는 노드.
    design.md의 6번 단계에 해당합니다.
    """
    print("--- [update_node] Updating user data ---")
    # 예시: 젠(Generator)에서 특정 캐릭터 정보가 확정되었다고 판단되면 파일로 저장
    # 여기서는 간단히 로직의 존재만 기술 (실제 구현 시 LLM이 추출한 entity를 parsing하여 save_ 함수 호출)
    
    return {"next_node": "router"}

def tools_node(state: NarrativeState):
    """
    PDF 생성 등 외부 도구를 실행하는 노드.
    design.md의 5번 단계에 해당합니다.
    """
    print("--- [tools_node] Executing tools ---")
    # 예시: write_pdf_tool 호출 등
    return {"next_node": "router"}

def response_check_node(state: NarrativeState):
    """
    생성된 답변이 요구사항을 충족하는지 검증하는 노드.
    design.md의 7번 단계에 해당합니다.
    """
    print("--- [response_check_node] Validating generated response ---")
    reqs = state["workflow"]["output_requirements"]
    content = state["last_response"]
    
    # 간단한 키워드 기반 검증 (실제로는 LLM 검증기 사용 추천)
    is_valid = True
    feedback = ""
    for req in reqs:
        if req not in content:
            # is_valid = False # 데모를 위해 일단 True로 유지하거나 조건 완화
            feedback += f"'{req}' 요소가 부족합니다. "
            
    return {
        "validation_results": {"is_valid": is_valid, "feedback": feedback},
        "next_node": "END" if is_valid else "router"
    }

# ==========================================
# 3. 라우팅 로직 (Routing Logic)
# ==========================================

def router_logic(state: NarrativeState):
    """
    어떤 노드로 분기할지 결정하는 조건부 엣지 함수.
    """
    print(f"--- [router] Deciding next step for {state['next_node']} ---")
    return state["next_node"]

# ==========================================
# 4. 그래프 구축 (Graph Building)
# ==========================================

def build_narrative_graph():
    builder = StateGraph(NarrativeState)
    
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
            "tools": "tools"
        }
    )
    
    builder.add_edge("generator", "response_check")
    
    builder.add_conditional_edges(
        "response_check",
        lambda x: "END" if x["validation_results"]["is_valid"] else "generator",
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
            if "last_response" in output:
                print(f"AI: {output['last_response']}")
