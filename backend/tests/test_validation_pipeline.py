"""三道门槛管线测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from services.validation_pipeline import (
    ValidationStage,
    PipelineState,
    GateResult,
    start_pipeline,
    get_pipeline,
    submit_gate,
    run_replay_gate,
    run_scientific_gate,
    run_production_gate,
    process_backtest_result,
)


class TestPipelineState:
    """管线状态"""

    def test_new_pipeline_starts_at_replay(self):
        state = PipelineState(strategy_id="test-1")
        assert state.current_stage == ValidationStage.REPLAY
        assert state.progress_pct == 0.0
        assert not state.is_complete

    def test_progress_reaches_100(self):
        state = PipelineState(strategy_id="test-2")
        state.current_stage = ValidationStage.PASSED
        assert state.progress_pct == 100.0
        assert state.is_complete


class TestReplayGate:
    """Replay 门槛"""

    def test_empty_result_fails(self):
        r = run_replay_gate("s1", None)
        assert not r.passed
        assert "空" in r.detail

    def test_no_trades_fails(self):
        r = run_replay_gate("s1", {"total_trades": 0, "sharpe_ratio": 0})
        assert not r.passed

    def test_successful_backtest_passes(self):
        r = run_replay_gate("s1", {"total_trades": 10, "sharpe_ratio": 1.5})
        assert r.passed


class TestScientificGate:
    """Scientific 门槛"""

    def test_empty_validation_fails(self):
        r = run_scientific_gate("s1", {})
        assert not r.passed

    def test_all_checks_pass(self):
        r = run_scientific_gate("s1", {
            "pbo": 0.2,
            "dsr": 1.5,
            "nw_t_stat": 2.5,
            "spa_p_value": 0.01,
        })
        assert r.passed

    def test_pbo_too_high_fails(self):
        r = run_scientific_gate("s1", {
            "pbo": 0.7,
            "dsr": 1.5,
            "nw_t_stat": 2.5,
        })
        assert not r.passed
        assert "PBO" in r.detail

    def test_low_nw_t_fails(self):
        r = run_scientific_gate("s1", {
            "pbo": 0.3,
            "dsr": 0.8,
            "nw_t_stat": 1.0,
        })
        assert not r.passed
        assert "t-stat" in r.detail


class TestProductionGate:
    """Production 门槛"""

    def test_sharpe_decay_too_high_fails(self):
        r = run_production_gate("s1", sim_sharpe=2.0, live_sharpe=1.0, sim_max_dd=10, live_max_dd=20)
        assert not r.passed
        assert "衰减" in r.detail

    def test_drawdown_too_high_fails(self):
        r = run_production_gate("s1", sim_sharpe=2.0, live_sharpe=1.8, sim_max_dd=10, live_max_dd=50)
        assert not r.passed
        assert "回撤" in r.detail

    def test_all_pass(self):
        r = run_production_gate("s1", sim_sharpe=2.0, live_sharpe=1.6, sim_max_dd=20, live_max_dd=25)
        assert r.passed


class TestPipelineFlow:
    """管线流程"""

    def test_start_and_get_pipeline(self):
        sid = "test-flow-1"
        state = start_pipeline(sid)
        assert state.strategy_id == sid
        assert state.current_stage == ValidationStage.REPLAY

        loaded = get_pipeline(sid)
        assert loaded is not None
        assert loaded.current_stage == ValidationStage.REPLAY

    def test_submit_gate_advances(self):
        sid = "test-flow-2"
        start_pipeline(sid)

        # Replay 通过
        state = submit_gate(sid, ValidationStage.REPLAY, True, "replay ok")
        assert state.current_stage == ValidationStage.SCIENTIFIC

        # Scientific 通过
        state = submit_gate(sid, ValidationStage.SCIENTIFIC, True, "sci ok")
        assert state.current_stage == ValidationStage.PRODUCTION

        # Production 通过 → PASSED
        state = submit_gate(sid, ValidationStage.PRODUCTION, True, "prod ok")
        assert state.current_stage == ValidationStage.PASSED
        assert state.is_complete

    def test_submit_gate_failure_stops(self):
        sid = "test-flow-3"
        start_pipeline(sid)

        state = submit_gate(sid, ValidationStage.REPLAY, True, "ok")
        state = submit_gate(sid, ValidationStage.SCIENTIFIC, False, "pbo too high")
        assert state.current_stage == ValidationStage.FAILED
        assert state.is_complete


class TestProcessBacktestResult:
    """综合处理"""

    def test_full_pipeline_from_backtest(self):
        sid = "test-bt-1"
        bt_result = {
            "total_trades": 15,
            "sharpe_ratio": 2.1,
            "total_return_pct": 25.0,
            "max_drawdown_pct": 12.0,
            "equity_curve": [
                {"timestamp": "2024-01-01", "equity": 10000},
                {"timestamp": "2024-01-02", "equity": 10200},
                {"timestamp": "2024-01-03", "equity": 10150},
                {"timestamp": "2024-01-04", "equity": 10500},
            ],
            "validation": {
                "pbo": 0.15,
                "dsr": 1.8,
                "nw_t_stat": 2.5,
                "spa_p_value": 0.02,
            },
        }

        state = process_backtest_result(sid, bt_result)
        assert state.current_stage == ValidationStage.PRODUCTION  # 通过了 Replay 和 Scientific
