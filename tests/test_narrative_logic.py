# tests/test_narrative_logic.py
import unittest
import sys
import os

# 현재 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.constraint_solver import NarrativeConstraintSolver
from src.validator_agent import ValidatorAgent

class TestNarrativeLogic(unittest.TestCase):
    def setUp(self):
        """테스트 시작 전 초기화"""
        self.theory_type = "propp"
        self.solver = NarrativeConstraintSolver(theory_type=self.theory_type)
        self.validator = ValidatorAgent(theory_type=self.theory_type)

    def test_propp_initial_step(self):
        """P01(Initial Situation)에서 시작할 수 있는지 테스트"""
        valid_next = self.solver.get_valid_next_ids(None)
        self.assertIn("P01", valid_next, "P01 should be a valid starting point.")

    def test_propp_valid_transition(self):
        """P01 -> P02 전이가 유효한지 테스트"""
        is_valid = self.validator.validate_transition("P01", "P02")
        self.assertTrue(is_valid, "P01 to P02 should be a valid transition.")

    def test_propp_invalid_transition(self):
        """P01 -> P04(직행) 전이가 유효하지 않은지 테스트"""
        is_valid = self.validator.validate_transition("P01", "P04")
        self.assertFalse(is_valid, "P01 to P04 should NOT be valid (skipping steps).")

    def test_logic_constraint_sequence(self):
        """CP-SAT 솔버가 유효한 3단계 시퀀스를 생성하는지 테스트"""
        sequence = self.solver.solve_sequence(length=3)
        self.assertEqual(len(sequence), 3, "Should generate a sequence of length 3.")
        
        # 첫 번째 노드가 P01인지 확인 (데이터 설정에 따라 다를 수 있음)
        self.assertEqual(sequence[0], "P01")
        
        # 각 단계 간의 전이 유효성 검증
        for i in range(len(sequence) - 1):
            valid = self.validator.validate_transition(sequence[i], sequence[i+1])
            self.assertTrue(valid, f"Transition from {sequence[i]} to {sequence[i+1]} should be valid.")

if __name__ == "__main__":
    unittest.main()
