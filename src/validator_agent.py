# validator_agent.py
"""Logic, causality, internal consistency, and completion metric validation agent."""

import os
import json
import datetime
from dotenv import load_dotenv
load_dotenv()

from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from collections import defaultdict

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.tools import load_worldview, load_characters, load_plot
from src.constraint_solver import NarrativeConstraintSolver

class ConflictItem(BaseModel):
    entity_1_id: str = Field(description="첫 번째 충돌 주체 ID (예: CHAR_01, N_001, RULE_1)")
    entity_2_id: str = Field(description="두 번째 충돌 주체 ID (예: N_002)")
    severity: float = Field(description="가벼운 충돌(상황으로 극복 가능)이면 0.3, 심각한 모순이면 1.0 (트라우마 극복 등 정당한 설정은 0.0으로 제외)")
    reason: str = Field(description="충돌 사유 및 논리적 붕괴 설명")

class ConflictReport(BaseModel):
    conflicts: List[ConflictItem] = Field(description="발견된 충돌 목록", default_factory=list)


class ValidatorAgent:
    def __init__(self, story_dir: str):
        self.story_dir = story_dir
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.structured_llm = self.llm.with_structured_output(ConflictReport)
        
        self.wv_path = os.path.join(story_dir, "created_worldview.json")
        self.ch_path = os.path.join(story_dir, "created_character.json")
        self.pl_path = os.path.join(story_dir, "created_plot.json")
        self.cache_path = os.path.join(story_dir, "validation_history.json")
        
        self.worldview = load_worldview(self.wv_path) if os.path.exists(self.wv_path) else None
        self.character_set = load_characters(self.ch_path) if os.path.exists(self.ch_path) else None
        self.plot = load_plot(self.pl_path) if os.path.exists(self.pl_path) else None
        
        # Determine theory type from plot metadata if available
        theory_type = "THEORY_PROPP_VOGLER_HYBRID"
        if self.plot and hasattr(self.plot, 'Plot_Metadata'):
            if isinstance(self.plot.Plot_Metadata, dict):
                theory_type = self.plot.Plot_Metadata.get("Applied_Structure", theory_type)
            elif hasattr(self.plot.Plot_Metadata, "Applied_Structure"):
                theory_type = self.plot.Plot_Metadata.Applied_Structure
        
        try:
            self.solver = NarrativeConstraintSolver(theory_type=theory_type)
        except Exception:
            self.solver = NarrativeConstraintSolver()
            
        self.entity_map = {}

    def _get_mtime_iso(self, path):
        if os.path.exists(path):
            return datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
        return None

    def get_timestamps(self):
        return {
            "worldview": self._get_mtime_iso(self.wv_path),
            "characters": self._get_mtime_iso(self.ch_path),
            "plot_nodes": self._get_mtime_iso(self.pl_path),
            "report": self._get_mtime_iso(self.cache_path)
        }

    def is_report_stale(self) -> bool:
        ts = self.get_timestamps()
        rt = ts["report"]
        if not rt: return True
        
        for k in ["worldview", "characters", "plot_nodes"]:
            if ts[k] and ts[k] > rt:
                return True
        return False

    def load_history(self) -> list:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_history(self, new_report: dict):
        history = self.load_history()
        history.append(new_report)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def _check_physical_completeness(self):
        char_total = 0; char_missing = 0
        if self.character_set and hasattr(self.character_set, 'characters'):
            for c in self.character_set.characters:
                char_total += 5
                if not getattr(c, 'name', None): char_missing += 1
                if not getattr(c, 'char_role', None): char_missing += 1
                if not getattr(c, 'initial_lack', None): char_missing += 1
                if not getattr(c, 'dominant_trait', None): char_missing += 1
                if not getattr(c, 'forbidden_action', None): char_missing += 1
                
                name = getattr(c, 'name', c.char_id)
                self.entity_map[c.char_id] = {
                    "name": f"{c.char_id} ({name})",
                    "tooltip": f"결핍: {getattr(c, 'initial_lack', '')} | 특성: {getattr(c, 'dominant_trait', '')}"
                }
        
        world_total = 0; world_missing = 0
        if self.worldview and hasattr(self.worldview, 'rules'):
            for i, r in enumerate(self.worldview.rules):
                world_total += 3
                if not getattr(r, 'rule_title', None): world_missing += 1
                if not getattr(r, 'description', None): world_missing += 1
                if not getattr(r, 'forbidden_events', None): world_missing += 1
                
                rid = f"RULE_{i+1}"
                title = getattr(r, 'rule_title', rid)
                self.entity_map[rid] = {
                    "name": f"{rid} ({title})",
                    "tooltip": getattr(r, 'description', '')
                }
                
        plot_total = 0; plot_missing = 0
        if self.plot and hasattr(self.plot, 'Plot_Nodes'):
            for n in self.plot.Plot_Nodes:
                plot_total += 2
                content = getattr(n, 'Content', '')
                if not content: plot_missing += 1
                if not getattr(n, 'Function_ID', None): plot_missing += 1
                
                nid = getattr(n, 'Node_ID', '')
                snip = content[:30] + "..." if len(content) > 30 else content
                self.entity_map[nid] = {
                    "name": f"{nid} ({snip})",
                    "tooltip": content
                }
                
        def calc(tot, ms): return round(((tot - ms) / tot * 100), 1) if tot > 0 else 100.0
        
        return {
            "Characters": calc(char_total, char_missing),
            "Worldview": calc(world_total, world_missing),
            "PlotNodes": calc(plot_total, plot_missing)
        }

    def _analyze_conflicts_llm(self, category_name: str, entities_text: str, total_comparisons: int) -> dict:
        if total_comparisons <= 0:
            return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "당신은 치밀한 서사 논리 검증관입니다. 제공된 {category_name} 목록 내에서 서로 모순되거나 충돌하는 설정이 있는지 찾으세요.\n"
             "가벼운 충돌(예외가능)은 0.3, 치명적 논리 오류는 1.0 충돌로 계산하세요.\n"
             "위반율 계산을 위해 충돌이 없으면 빈 배열을 반환하세요."),
            ("human", "분석할 {category_name} 텍스트:\n\n{entities_text}")
        ])
        
        chain = prompt | self.structured_llm
        report = chain.invoke({"category_name": category_name, "entities_text": entities_text})
        
        return self._process_llm_report(report, total_comparisons)

    def _analyze_cross_domain_llm(self, plot_text: str, bg_text: str, total_comparisons: int, domain_hint: str) -> dict:
        if total_comparisons <= 0:
            return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             f"당신은 크로스도메인 논리 검증관입니다. 플롯 전개 내용이 [{domain_hint}]을(를) 위반했는지 꼼꼼히 대조하세요.\n"
             ">> 특별 예외 규칙 (Dynamic Trauma Overcoming): <<\n"
             "만약 해당 플롯이 이야기의 중대한 '전환점(예: CLIMAX, 각성, 결말 등)' 마일스톤에 해당할 때 캐릭터가 자신의 오랜 트라우마나 절대 금기행동을 깨부수는 묘사가 있다면, 이는 오류가 아니라 '트라우마 극복(성장 카타르시스)'으로 간주합니다. 이 경우 충돌로 취급하지 마세요(결과 배제).\n"
             "전환점이 아닌 평범한 구간에서 위반하면 명백한 1.0 심각 충돌입니다.\n"
             "가벼운 우연적 충돌은 0.3점입니다."),
            ("human", "분석할 배경 설정:\n{bg_text}\n\n분석할 플롯 타임라인:\n{plot_text}")
        ])
        
        chain = prompt | self.structured_llm
        report = chain.invoke({"bg_text": bg_text, "plot_text": plot_text})
        
        return self._process_llm_report(report, total_comparisons)

    def _process_llm_report(self, report, total_comparisons):
        if not report or not getattr(report, "conflicts", None):
            return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": total_comparisons, "error_sum": 0.0}
            
        error_sum = sum(c.severity for c in report.conflicts)
        violation_rate = (error_sum / total_comparisons) * 100 if total_comparisons > 0 else 0
        
        trouble_counts = defaultdict(float)
        details = []
        for c in report.conflicts:
            trouble_counts[c.entity_1_id] += c.severity
            trouble_counts[c.entity_2_id] += c.severity
            details.append({
                "entity_1_id": c.entity_1_id,
                "entity_2_id": c.entity_2_id,
                "severity": c.severity,
                "reason": c.reason
            })
            
        troublemakers = sorted(trouble_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "violation_rate": violation_rate,
            "troublemakers": troublemakers,
            "details": details,
            "total_comps": total_comparisons,
            "error_sum": error_sum
        }

    def suggest_corrections(self) -> str:
        """논리 검증 리포트(과거 캐시)를 바탕으로 모순 해결/수정안을 제안합니다."""
        history = self.load_history()
        if not history:
            return "검증 기록이 없어 수정 제안을 할 수 없습니다."
        latest = history[-1]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "당신은 서사 구조 교정(Correction) 전문가입니다. 다음은 가장 최근의 논리 검증 리포트 오류 내역입니다.\n"
             "작가가 어떻게 플롯이나 설정을 수정하면 모순을 무난하게 해결할 수 있을지 창의적이고 구체적인 시나리오 2가지를 제안해 주세요. 길지 않고 명확하게 대화체로 작성하세요."),
            ("human", f"오류 리포트 요약:\n{json.dumps(latest['logical'], ensure_ascii=False)}")
        ])
        res = self.llm.invoke(prompt)
        return str(res.content)

    def _check_phase_2_structural(self) -> dict:
        """[2단계 검증] OR-Tools 기반 플롯 홀(구조적 인과율 이탈) 검사"""
        details = []
        error_sum = 0.0
        
        if not self.plot or not getattr(self.plot, 'Plot_Nodes', []):
           return {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
           
        nodes = sorted(self.plot.Plot_Nodes, key=lambda x: getattr(x, 'Sequence_Index', 0))
        n = len(nodes)
        comps = n - 1 if n > 1 else 0
        
        if comps > 0:
            trouble_counts = defaultdict(float)
            for i in range(n - 1):
                from_id = getattr(nodes[i], 'Function_ID', '')
                to_id = getattr(nodes[i+1], 'Function_ID', '')
                if not from_id or not to_id: continue
                # 예외적으로 직접 파싱이나 수동 조립 노드(P01(부재) 등)의 경우 보정 처리 (간이 무시)
                if "(" in from_id or "(" in to_id: continue
                
                try:
                    valid_next = self.solver.get_valid_next_ids(from_id)
                except:
                    valid_next = []
                    
                if valid_next and to_id not in valid_next:
                    sev = 1.0
                    error_sum += sev
                    nid1 = getattr(nodes[i], 'Node_ID', from_id)
                    nid2 = getattr(nodes[i+1], 'Node_ID', to_id)
                    details.append({
                        "entity_1_id": nid1,
                        "entity_2_id": nid2,
                        "severity": sev,
                        "reason": f"이론적 계층 위반: [{from_id}] 이후에는 곧바로 [{to_id}] 단계가 올 수 없습니다. (플롯 홀 발생)"
                    })
                    trouble_counts[nid1] += sev
                    trouble_counts[nid2] += sev
                    
            violation_rate = (error_sum / comps) * 100 if comps > 0 else 0.0
            troublemakers = sorted(trouble_counts.items(), key=lambda x: x[1], reverse=True)
        else:
            violation_rate = 0.0
            troublemakers = []
            
        return {
            "violation_rate": violation_rate,
            "troublemakers": troublemakers,
            "details": details,
            "total_comps": comps,
            "error_sum": error_sum
        }

    def generate_report(self) -> dict:
        phys_scores = self._check_physical_completeness()
        log_res = {}
        
        # 1. 캐릭터
        if self.character_set and hasattr(self.character_set, 'characters'):
            chars = self.character_set.characters
            n = len(chars)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            
            char_text = ""
            for c in chars:
                rel_info = " / ".join([f"{r.target_char_id}({r.relationship_title})" for r in getattr(c, 'char_relationship', [])]) if getattr(c, 'char_relationship', None) else "없음"
                char_text += f"---\n[CHAR_ID: {c.char_id}]\n이름: {c.name}\n결핍: {getattr(c, 'initial_lack', '없음')}\n관계: {rel_info}\n금기행동: {getattr(c, 'forbidden_action', '없음')}\n\n"
            log_res["Characters"] = self._analyze_conflicts_llm("캐릭터", char_text, comps)
        else:
            log_res["Characters"] = {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        # 2. 세계관
        if self.worldview and hasattr(self.worldview, 'rules'):
            rules = self.worldview.rules
            n = len(rules)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            
            rule_text = ""
            for i, r in enumerate(rules):
                f_events = ", ".join(r.forbidden_events) if getattr(r, 'forbidden_events', None) else "없음"
                rule_text += f"---\n[Rule_ID: RULE_{i+1}]\n규칙명: {r.rule_title}\n설명: {r.description}\n금기이벤트: {f_events}\n\n"
            log_res["Worldview"] = self._analyze_conflicts_llm("세계관 규칙", rule_text, comps)
        else:
            log_res["Worldview"] = {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        # 3. 플롯
        nodes = sorted(self.plot.Plot_Nodes, key=lambda x: getattr(x, 'Sequence_Index', 0)) if getattr(self, 'plot', None) and getattr(self.plot, 'Plot_Nodes', []) else []
        if nodes:
            n = len(nodes)
            comps = (n * (n - 1)) / 2 if n > 1 else 0
            plot_text = ""
            for pn in nodes:
                plot_text += f"---\n[Node_ID: {getattr(pn, 'Node_ID', '')}]\n기능: {getattr(pn, 'Function_ID', '')}\n순서: {getattr(pn, 'Sequence_Index', 0)}\n내용: {getattr(pn, 'Content', '')}\n\n"
            log_res["PlotNodes"] = self._analyze_conflicts_llm("플롯 노드", plot_text, comps)
        else:
            log_res["PlotNodes"] = {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        # Phase 2
        log_res["Phase2_Path"] = self._check_phase_2_structural()
        
        # Phase 3
        if nodes and self.character_set and hasattr(self.character_set, 'characters'):
            char_bg_text = "== 캐릭터 설정 ==\n" + char_text
            n_bg = len(self.character_set.characters)
            log_res["Phase3_CharPlot"] = self._analyze_cross_domain_llm(plot_text, char_bg_text, len(nodes) * n_bg, "캐릭터 금기행동 및 초기 결핍")
        else:
            log_res["Phase3_CharPlot"] = {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        if nodes and self.worldview and hasattr(self.worldview, 'rules'):
            world_bg_text = "== 세계관 규칙 ==\n" + rule_text
            n_bg = len(self.worldview.rules)
            log_res["Phase3_WorldPlot"] = self._analyze_cross_domain_llm(plot_text, world_bg_text, len(nodes) * n_bg, "세계관 규칙 및 금기이벤트")
        else:
            log_res["Phase3_WorldPlot"] = {"violation_rate": 0.0, "troublemakers": [], "details": [], "total_comps": 0, "error_sum": 0.0}
            
        new_report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "timestamps": self.get_timestamps(),
            "physical": phys_scores,
            "logical": log_res,
            "entity_map": self.entity_map
        }
        
        self._save_history(new_report)
        return new_report
