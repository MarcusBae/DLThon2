# validator_agent.py
"""Logic, causality, and internal consistency verification agent."""

import os
from dotenv import load_dotenv
load_dotenv()

from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from collections import defaultdict

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.tools import load_worldview, load_characters, load_plot

# -----------------
# 1단계 검증용 스키마
# -----------------
class ConflictItem(BaseModel):
    entity_1_id: str = Field(description="첫 번째 충돌 주체 ID (예: CHAR_01, N_001, RULE_1)")
    entity_2_id: str = Field(description="두 번째 충돌 주체 ID (예: CHAR_02, N_003, RULE_2)")
    severity: float = Field(description="예외 규칙이나 상황설정으로 극복 가능한 가벼운 충돌이면 0.3, 아예 대립되는 심각한 충돌이면 1.0")
    reason: str = Field(description="충돌이 발생한 이유 설명")

class ConflictReport(BaseModel):
    conflicts: List[ConflictItem] = Field(description="발견된 충돌 목록", default_factory=list)


class ValidatorAgent:
    def __init__(self, story_dir: str):
        self.story_dir = story_dir
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) # 비용 절감을 위해 mini 사용 권장 (필요시 gpt-4o 변경)
        self.structured_llm = self.llm.with_structured_output(ConflictReport)
        
        # 1. 자동 데이터 매핑
        self.worldview = None
        self.character_set = None
        self.plot = None
        
        wv_path = os.path.join(story_dir, "created_worldview.json")
        ch_path = os.path.join(story_dir, "created_character.json")
        pl_path = os.path.join(story_dir, "created_plot.json")
        
        if os.path.exists(wv_path): self.worldview = load_worldview(wv_path)
        if os.path.exists(ch_path): self.character_set = load_characters(ch_path)
        if os.path.exists(pl_path): self.plot = load_plot(pl_path)

    def _analyze_conflicts_llm(self, category_name: str, entities_text: str, total_comparisons: int) -> dict:
        """LLM을 호출하여 텍스트 간 논리 충돌을 분석하고 오류율을 산출합니다."""
        if total_comparisons <= 0:
            return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "당신은 치밀한 서사 논리 검증관입니다. 제공된 {category_name} 목록 내에서 서로 모순되거나 충돌하는 설정이 있는지 찾아내세요.\n"
             "예시1(캐릭터): A가 B를 부모라고 했는데, B가 A를 할아버지라 하면 1.0 충돌\n"
             "예시2(플롯): N_01에서 잃어버린 물건을 N_03에서 그대로 사용하고 있다면 1.0 충돌\n"
             "예시3(세계관): 마법이 금지된 세계인데 마법 사용 규칙이 있다면 1.0 충돌\n"
             "가벼운 충돌(우연한 상황이나 예외 처리로 수습 가능)은 0.3, 심각한 모순은 1.0으로 분류하세요.\n"
             "충돌이 없으면 빈 배열을 반환하세요."),
            ("human", "분석할 {category_name} 텍스트:\n\n{entities_text}")
        ])
        
        chain = prompt | self.structured_llm
        report = chain.invoke({"category_name": category_name, "entities_text": entities_text})
        
        # 만약 report가 None이거나 conflicts 속성이 없는 경우 방어 코딩
        if not report or not getattr(report, "conflicts", None):
            return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": total_comparisons, "error_sum": 0.0}
            
        # 오류율 계산
        error_sum = sum(c.severity for c in report.conflicts)
        violation_rate = (error_sum / total_comparisons) * 100 if total_comparisons > 0 else 0
        
        # 트러블메이커 통계 (누가 가장 충돌을 많이 일으키는가)
        trouble_counts = defaultdict(float)
        for c in report.conflicts:
            trouble_counts[c.entity_1_id] += c.severity
            trouble_counts[c.entity_2_id] += c.severity
            
        # 내림차순 정렬
        troublemakers = sorted(trouble_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "violation_rate": violation_rate,
            "troublemakers": troublemakers,
            "details": report.conflicts,
            "total_comps": total_comparisons,
            "error_sum": error_sum
        }

    def validate_phase_1(self) -> dict:
        """
        [1단계 검증] 단일 JSON 파일 내 논리적 충돌 스캔
        비교 횟수(n*(n-1)/2) 기반으로 가중치 오류율 산출 및 문제아 리포팅
        """
        results = {}
        
        # 1. 캐릭터 파일 내 검사 (캐릭터 간 관계 및 설정 모순)
        if getattr(self, 'character_set', None) and getattr(self.character_set, 'characters', []):
            chars = self.character_set.characters
            n = len(chars)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            
            char_text = ""
            for c in chars:
                rel_info = ""
                if getattr(c, 'char_relationship', None):
                    rels = [f"{r.target_char_id}({r.relationship_title})" for r in c.char_relationship]
                    rel_info = " / ".join(rels)
                char_text += f"---\n[CHAR_ID: {c.char_id}]\n이름: {c.name}\n결핍: {getattr(c, 'initial_lack', '없음')}\n관계: {rel_info}\n특징: {c.dominant_trait}\n금기행동: {getattr(c, 'forbidden_action', '없음')}\n\n"
            
            results["Characters"] = self._analyze_conflicts_llm("캐릭터", char_text, comps)
            
        # 2. 세계관 파일 내 검사 (규칙 간 상충)
        if getattr(self, 'worldview', None) and getattr(self.worldview, 'rules', []):
            rules = self.worldview.rules
            n = len(rules)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            
            rule_text = ""
            for i, r in enumerate(rules):
                # ID가 별도로 없으므로 RULE_숫자 부여
                rule_id = f"RULE_{i+1}"
                f_events = ", ".join(r.forbidden_events) if getattr(r, 'forbidden_events', None) else "없음"
                rule_text += f"---\n[Rule_ID: {rule_id}]\n규칙명: {r.rule_title}\n설명: {r.description}\n절대 금기이벤트: {f_events}\n\n"
                
            results["Worldview"] = self._analyze_conflicts_llm("세계관 규칙", rule_text, comps)
            
        # 3. 플롯 파일 내 검사 (타임라인 상의 앞뒤 사건 모순 및 오류)
        # Sequence_Index 순으로 정렬 후 검사
        if getattr(self, 'plot', None) and getattr(self.plot, 'Plot_Nodes', []):
            nodes = sorted(self.plot.Plot_Nodes, key=lambda x: getattr(x, 'Sequence_Index', 0))
            n = len(nodes)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            
            plot_text = ""
            for pn in nodes:
                node_id = getattr(pn, 'Node_ID', 'Unknown')
                plot_text += f"---\n[Node_ID: {node_id}]\n순서: {getattr(pn, 'Sequence_Index', 0)}\n내용: {getattr(pn, 'Content', '')}\n\n"
                
            results["PlotNodes"] = self._analyze_conflicts_llm("플롯 노드", plot_text, comps)
            
        return results

if __name__ == "__main__":
    import json
    # 테스트용 드라이버 코드
    test_dir = "../data/user_data/story_20260326_110409"
    # 현재 디렉토리 구조상 main.py 위치에서 실행될 때를 고려한 안전한 상대 경로
    if not os.path.exists(test_dir):
        test_dir = "data/user_data/story_20260326_110409"

    validator = ValidatorAgent(story_dir=test_dir)
    print("=== [1단계] 문서 내부 논리 충돌 및 모순 검출 실행 ===")
    res = validator.validate_phase_1()
    
    for category, stat in res.items():
        print(f"\n[{category} 부문 검증 결과]")
        print(f" - 총 비교 횟수 조합: {stat['total_comps']} 회")
        print(f" - 누적 에러 점수: {stat['error_sum']:.1f}")
        print(f" - 위반율(오류율): {stat['violation_rate']:.1f}%")
        
        if stat['details']:
            print(" - [충돌 상세 내역]")
            for d in stat['details']:
                sev_type = "(심각)" if float(d.severity) == 1.0 else "(가벼움)"
                print(f"   *{sev_type} {d.entity_1_id} vs {d.entity_2_id}: {d.reason}")
                
        if stat['troublemakers']:
            print(" - [! 요주의 트러블메이커 순위]")
            for tm, score in stat['troublemakers']:
                print(f"   1위: {tm} (오류기여 점수: {score:.1f})") if stat['troublemakers'][0][0] == tm else print(f"   순위권: {tm} (점수: {score:.1f})")

