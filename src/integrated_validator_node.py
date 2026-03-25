
import json
from src.constraint_solver import NarrativeConstraintSolver # 동료의 로직 참조

class IntegratedValidator:
    def __init__(self, theory_type="propp", schema_path="../data/system/schema_data_modified.json"):
        # 1계층: 구조적 전이 검증기 (동료의 Solver)
        self.path_solver = NarrativeConstraintSolver(theory_type=theory_type)
        # 2계층: 맥락적 제약 검증 데이터
        with open(schema_path, 'r', encoding='utf-8') as f:
            self.master_schema = json.load(f)

    def validate_node(self, state):
        """⚙️ LangGraph Node: 경로와 맥락을 동시 검증"""
        proposal = state['generated_proposals'][-1]
        locks = state['archetype_locks']
        history = state.get('violation_log', [])
        
        violation_count = 0
        total_checks = 0
        current_violations = []

        # --- [1단계: 경로 검증 (Path Integrity)] ---
        if len(state['generated_proposals']) > 1:
            prev_node = state['generated_proposals'][-2]
            # 동료의 Solver를 활용한 ID 전이 체크
            is_path_valid = self.path_solver.validate_transition(
                prev_node['func_id'], proposal['func_id']
            )
            total_checks += 1
            if not is_path_valid:
                violation_count += 1
                current_violations.append(f"구조 위반(L_STRUCT_V): {prev_node['func_id']} 후 {proposal['func_id']} 불가")

        # --- [2단계: 맥락 검증 (Context Integrity)] ---
        for char_id, traits in locks.items():
            forbidden = traits.get('Forbidden_Action', [])
            total_checks += len(forbidden)
            
            for action in forbidden:
                if action in proposal['content']:
                    # [동적 수정 로직]: 전환점 노드라면 극복으로 인정
                    if state.get('is_turning_point', False):
                        print(f"[동적 합법화] {char_id}의 트라우마 극복 지점 확인.")
                    else:
                        violation_count += 1
                        current_violations.append(f"캐릭터 위반(L_CHAR_V): {char_id}의 금기 행동 '{action}' 감지")

        # --- [3단계: 지표 산출 및 상태 갱신] ---
        v_rate = (violation_count / total_checks * 100) if total_checks > 0 else 0
        
        return {
            "is_valid": violation_count == 0,
            "violation_rate": v_rate,
            "violation_log": history + current_violations,
            "pending_queries": state['pending_queries'] if violation_count == 0 else ["RE-GENERATE"]
        }
