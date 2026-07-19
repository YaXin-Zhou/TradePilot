"""AI Strategy Iterator — 单元测试"""
import json
import pathlib
import tempfile
from services.ai_iterator import (
    StrategyVariant,
    IterationRound,
    IterationTask,
    _parse_variants,
    _rank_variants,
    _check_convergence,
    _build_generation_prompt,
    _load_tasks,
    _save_tasks,
    _load_task_data,
    _save_task_data,
    DATA_DIR,
)


# ─── 数据模型 ──────────────────────────────────────────────────

class TestStrategyVariant:
    def test_to_dict_roundtrip(self):
        v = StrategyVariant(
            strategy_type="ma_crossover",
            params={"fast": 10, "slow": 30},
            rationale="simple cross",
            sharpe_is=1.2,
            sharpe_oos=0.9,
            scientific_passed=True,
        )
        d = v.to_dict()
        assert d["strategy_type"] == "ma_crossover"
        assert d["sharpe_is"] == 1.2
        assert d["scientific_passed"] is True
        assert d["status"] == "pending"

    def test_default_values(self):
        v = StrategyVariant(strategy_type="rsi", params={"period": 14})
        assert v.sharpe_is == 0.0
        assert v.sharpe_oos == 0.0
        assert v.rationale == ""
        assert v.status == "pending"


class TestIterationRound:
    def test_to_dict(self):
        rd = IterationRound(round_number=1, status="generating")
        vars_list = [
            StrategyVariant(strategy_type="rsi", params={"period": 14}).to_dict(),
            StrategyVariant(strategy_type="ma_crossover", params={"fast": 10, "slow": 30}).to_dict(),
        ]
        rd.variants = vars_list
        rd.top_sharpe_is = 1.5
        rd.top_score = 1.2
        d = rd.to_dict()
        assert d["round_number"] == 1
        assert len(d["variants"]) == 2
        assert d["top_sharpe_is"] == 1.5


class TestIterationTask:
    def test_progress_pct_zero(self):
        task = IterationTask(
            task_id="t1", goal="test", symbol="BTC/USDT", timeframe="1h",
            variants_per_round=5, max_rounds=10, risk_constraints={},
        )
        assert task.progress_pct == 0

    def test_progress_pct_half(self):
        task = IterationTask(
            task_id="t2", goal="test", symbol="BTC/USDT", timeframe="1h",
            variants_per_round=5, max_rounds=10, risk_constraints={},
        )
        task.current_round = 5
        assert task.progress_pct == 50

    def test_progress_pct_completed(self):
        task = IterationTask(
            task_id="t3", goal="test", symbol="BTC/USDT", timeframe="1h",
            variants_per_round=5, max_rounds=5, risk_constraints={},
        )
        task.current_round = 5
        task.status = "completed"
        assert task.progress_pct == 100

    def test_best_variant_returns_highest_score(self):
        task = IterationTask(
            task_id="t4", goal="test", symbol="BTC/USDT", timeframe="1h",
            variants_per_round=5, max_rounds=5, risk_constraints={},
        )
        r1 = IterationRound(round_number=1)
        r1.variants = [
            {"strategy_type": "rsi", "params": {}, "score": 0.5, "sharpe_oos": 0.3},
            {"strategy_type": "ma_crossover", "params": {}, "score": 1.2, "sharpe_oos": 0.9},
        ]
        r2 = IterationRound(round_number=2)
        r2.variants = [
            {"strategy_type": "bollinger", "params": {}, "score": 0.8, "sharpe_oos": 0.6},
            {"strategy_type": "rsi", "params": {}, "score": 2.1, "sharpe_oos": 1.5},
        ]
        task.rounds = [r1.to_dict(), r2.to_dict()]
        best = task.best_variant
        assert best is not None
        assert best["score"] == 2.1
        assert best["strategy_type"] == "rsi"


# ─── JSON 解析 ─────────────────────────────────────────────────

class TestParseVariants:
    def test_valid_array(self):
        content = json.dumps([
            {"strategy_type": "ma_crossover", "params": {"fast": 10, "slow": 30}, "rationale": "trend"},
            {"strategy_type": "rsi", "params": {"period": 14, "oversold": 30, "overbought": 70}, "rationale": "mean reversion"},
        ])
        result = _parse_variants(content)
        assert len(result) == 2
        assert result[0]["strategy_type"] == "ma_crossover"
        assert result[0]["params"]["fast"] == 10

    def test_array_with_surrounding_text(self):
        content = "Here are strategies:\n" + json.dumps([
            {"strategy_type": "bollinger", "params": {"period": 20, "std_dev": 2.0}, "rationale": "volatility"},
        ]) + "\nDone."
        result = _parse_variants(content)
        assert len(result) == 1
        assert result[0]["strategy_type"] == "bollinger"

    def test_invalid_json(self):
        result = _parse_variants("not json at all [ broken")
        assert result == []

    def test_empty_string(self):
        result = _parse_variants("")
        assert result == []

    def test_wrong_strategy_type_filtered(self):
        content = json.dumps([
            {"strategy_type": "unknown_type", "params": {}, "rationale": ""},
            {"strategy_type": "rsi", "params": {"period": 14}, "rationale": ""},
        ])
        result = _parse_variants(content)
        assert len(result) == 1
        assert result[0]["strategy_type"] == "rsi"

    def test_missing_fields_get_defaults(self):
        content = json.dumps([
            {"strategy_type": "ma_crossover", "params": {"fast": 15, "slow": 45}},
        ])
        result = _parse_variants(content)
        assert result[0]["rationale"] == ""


# ─── 排序 ──────────────────────────────────────────────────────

class TestRankVariants:
    def test_rank_by_score(self):
        variants = [
            {"strategy_type": "a", "params": {}, "sharpe_is": 1.0, "sharpe_oos": 0.5, "score": 0},
            {"strategy_type": "b", "params": {}, "sharpe_is": 2.0, "sharpe_oos": 2.0, "score": 0},
            {"strategy_type": "c", "params": {}, "sharpe_is": 0.5, "sharpe_oos": 1.0, "score": 0},
        ]
        ranked = _rank_variants(variants)
        assert ranked[0]["strategy_type"] == "b"  # 2.0*0.3 + 2.0*0.7 = 2.0
        assert ranked[1]["strategy_type"] == "c"  # 0.5*0.3 + 1.0*0.7 = 0.85
        assert ranked[2]["strategy_type"] == "a"  # 1.0*0.3 + 0.5*0.7 = 0.65

    def test_score_weighting_oos_heavier(self):
        variants = [
            {"strategy_type": "high_is", "params": {}, "sharpe_is": 3.0, "sharpe_oos": 0.5, "score": 0},
            {"strategy_type": "high_oos", "params": {}, "sharpe_is": 0.5, "sharpe_oos": 3.0, "score": 0},
        ]
        ranked = _rank_variants(variants)
        # high_oos: 0.5*0.3 + 3.0*0.7 = 2.25
        # high_is: 3.0*0.3 + 0.5*0.7 = 1.25
        assert ranked[0]["strategy_type"] == "high_oos"

    def test_empty_list(self):
        assert _rank_variants([]) == []


# ─── 收敛检测 ──────────────────────────────────────────────────

class TestCheckConvergence:
    def test_not_enough_rounds(self):
        result, reason = _check_convergence([])
        assert result is False
        assert reason == ""
        result2, _ = _check_convergence([{"round_number": 1, "variants": []}])
        assert result2 is False

    def test_small_improvement_converges(self):
        # 连续两轮 Top-1 OOS 差异 < 1%
        rounds = [
            {
                "round_number": 1,
                "variants": [
                    {"sharpe_oos": 1.000, "sharpe_is": 1.2, "score": 0},
                    {"sharpe_oos": 0.800, "sharpe_is": 1.0, "score": 0},
                ],
            },
            {
                "round_number": 2,
                "variants": [
                    {"sharpe_oos": 1.005, "sharpe_is": 1.3, "score": 0},
                ],
            },
        ]
        converged, reason = _check_convergence(rounds)
        # improvement = |1.005 - 1.000| / 1.000 = 0.5% < 1%
        assert converged is True
        assert "1%" in reason

    def test_large_improvement_no_convergence(self):
        rounds = [
            {
                "round_number": 1,
                "variants": [
                    {"sharpe_oos": 0.500, "sharpe_is": 0.8, "score": 0},
                ],
            },
            {
                "round_number": 2,
                "variants": [
                    {"sharpe_oos": 1.200, "sharpe_is": 1.5, "score": 0},
                ],
            },
        ]
        converged, _ = _check_convergence(rounds)
        # improvement = |1.2 - 0.5| / 0.5 = 140% > 1%
        assert converged is False


# ─── Prompt 构建 ────────────────────────────────────────────────

class TestBuildGenerationPrompt:
    def test_basic_prompt_structure(self):
        market = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "current_price": 85000,
            "period_return_pct": 5.2,
            "bars": 500,
            "indicators": {
                "rsi": 55.0,
                "macd": 12.5,
                "volatility": 2.3,
                "ema9_vs_ema21": "above",
                "volume_ratio": 1.2,
            },
        }
        risk = {"max_drawdown_pct": 20, "min_sharpe": 0.8, "max_concentration": 0.3}
        prompt = _build_generation_prompt(
            goal="find best BTC strategy",
            market=market,
            risk=risk,
            variants_count=5,
        )
        assert "find best BTC strategy" in prompt
        assert "BTC/USDT" in prompt
        assert "55.0" in prompt
        assert "above" in prompt
        assert "max_drawdown_pct" in prompt or "Max Drawdown" in prompt
        assert "Generate 5" in prompt

    def test_prompt_with_top_k(self):
        market = {"error": "no data"}
        risk = {"max_drawdown_pct": 15, "min_sharpe": 1.0, "max_concentration": 0.5}
        top_k = [
            {"strategy_type": "rsi", "params": {"period": 14}, "sharpe_is": 1.5, "sharpe_oos": 1.2, "scientific_passed": True},
            {"strategy_type": "ma_crossover", "params": {"fast": 12, "slow": 40}, "sharpe_is": 1.3, "sharpe_oos": 1.0, "scientific_passed": True},
        ]
        prompt = _build_generation_prompt(
            goal="optimize RSI",
            market=market,
            risk=risk,
            variants_count=8,
            top_k=top_k,
        )
        assert "Top Strategies from Previous Rounds" in prompt
        assert "rsi" in prompt
        assert "ma_crossover" in prompt
        assert "Scientifically Validated=True" in prompt
        assert "Generate 8" in prompt


# ─── 持久化 ────────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_load_tasks(self, monkeypatch, tmp_path):
        """使用临时目录测试持久化"""
        monkeypatch.setattr("services.ai_iterator.DATA_DIR", tmp_path)
        monkeypatch.setattr("services.ai_iterator.TASKS_FILE", tmp_path / "iteration_tasks.json")

        tasks = {"test_id": {"task_id": "test_id", "status": "running"}}
        _save_tasks(tasks)
        loaded = _load_tasks()
        assert loaded["test_id"]["status"] == "running"

    def test_save_and_load_task_data(self, monkeypatch, tmp_path):
        monkeypatch.setattr("services.ai_iterator.DATA_DIR", tmp_path)
        monkeypatch.setattr("services.ai_iterator.TASKS_FILE", tmp_path / "iteration_tasks.json")
        monkeypatch.setattr(
            "services.ai_iterator._save_task_data",
            lambda tid, data: (tmp_path / f"iteration_data_{tid}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            ),
        )
        monkeypatch.setattr(
            "services.ai_iterator._load_task_data",
            lambda tid: (
                json.loads((tmp_path / f"iteration_data_{tid}.json").read_text(encoding="utf-8"))
                if (tmp_path / f"iteration_data_{tid}.json").exists() else None
            ),
        )

        task_data = {
            "task_id": "detail_test",
            "status": "completed",
            "rounds": [{"round_number": 1, "variants": []}],
        }
        _save_task_data("detail_test", task_data)
        loaded = _load_task_data("detail_test")
        assert loaded is not None
        assert loaded["status"] == "completed"
        assert len(loaded["rounds"]) == 1
