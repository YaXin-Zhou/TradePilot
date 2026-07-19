"""三道门槛验证管线 — Replay → Scientific → Production"""
import json
import pathlib
from enum import Enum
from datetime import datetime, timezone
from dataclasses import dataclass, field
from core.logger import log


class ValidationStage(str, Enum):
    REPLAY = "replay"           # 基础回放验证
    SCIENTIFIC = "scientific"   # 五重统计检验
    PRODUCTION = "production"   # 模拟盘 24H 稳定性
    PASSED = "passed"           # 全部通过
    FAILED = "failed"           # 任一门槛未通过


STAGE_ORDER = [
    ValidationStage.REPLAY,
    ValidationStage.SCIENTIFIC,
    ValidationStage.PRODUCTION,
    ValidationStage.PASSED,
]


@dataclass
class GateResult:
    stage: ValidationStage
    passed: bool
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineState:
    strategy_id: str
    current_stage: ValidationStage = ValidationStage.REPLAY
    gates: list[GateResult] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    @property
    def progress_pct(self) -> float:
        """当前进度百分比"""
        idx = STAGE_ORDER.index(self.current_stage) if self.current_stage in STAGE_ORDER else 0
        total = len(STAGE_ORDER) - 1  # PASSED 不算独立阶段
        return round(idx / total * 100, 1)

    @property
    def is_complete(self) -> bool:
        return self.current_stage in (ValidationStage.PASSED, ValidationStage.FAILED)


PIPELINE_DIR = pathlib.Path(__file__).parent.parent / "data"
PIPELINE_FILE = PIPELINE_DIR / "validation_pipelines.json"


def _load_pipelines() -> dict[str, dict]:
    """加载所有管线状态"""
    if not PIPELINE_FILE.exists():
        return {}
    try:
        return json.loads(PIPELINE_FILE.read_text())
    except Exception:
        return {}


def _save_pipelines(pipelines: dict[str, dict]):
    """保存管线状态"""
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    PIPELINE_FILE.write_text(json.dumps(pipelines, ensure_ascii=False, indent=2))


def _state_to_dict(state: PipelineState) -> dict:
    return {
        "strategy_id": state.strategy_id,
        "current_stage": state.current_stage.value,
        "progress_pct": state.progress_pct,
        "is_complete": state.is_complete,
        "gates": [{"stage": g.stage.value, "passed": g.passed, "detail": g.detail, "timestamp": g.timestamp} for g in state.gates],
        "started_at": state.started_at,
        "completed_at": state.completed_at,
    }


def _dict_to_state(data: dict) -> PipelineState:
    state = PipelineState(
        strategy_id=data["strategy_id"],
        current_stage=ValidationStage(data["current_stage"]),
        started_at=data.get("started_at", ""),
        completed_at=data.get("completed_at", ""),
    )
    for g in data.get("gates", []):
        state.gates.append(GateResult(
            stage=ValidationStage(g["stage"]),
            passed=g["passed"],
            detail=g.get("detail", ""),
            timestamp=g.get("timestamp", ""),
        ))
    return state


# ─── 管线操作 ──────────────────────────────────────────────────


def start_pipeline(strategy_id: str) -> PipelineState:
    """为新策略启动验证管线"""
    pipelines = _load_pipelines()
    state = PipelineState(strategy_id=strategy_id)
    pipelines[strategy_id] = _state_to_dict(state)
    _save_pipelines(pipelines)
    log.info(f"Validation pipeline started for strategy {strategy_id}")
    return state


def get_pipeline(strategy_id: str) -> PipelineState | None:
    """获取管线状态"""
    pipelines = _load_pipelines()
    data = pipelines.get(strategy_id)
    if not data:
        return None
    return _dict_to_state(data)


def submit_gate(
    strategy_id: str,
    stage: ValidationStage,
    passed: bool,
    detail: str = "",
) -> PipelineState:
    """提交门槛验证结果，自动推进管线"""
    pipelines = _load_pipelines()
    data = pipelines.get(strategy_id)
    if not data:
        state = PipelineState(strategy_id=strategy_id)
    else:
        state = _dict_to_state(data)

    # 记录本次结果
    state.gates.append(GateResult(stage=stage, passed=passed, detail=detail))

    if passed:
        # 推进到下一阶段
        idx = STAGE_ORDER.index(stage)
        if idx < len(STAGE_ORDER) - 1:
            if stage == ValidationStage.PRODUCTION:
                state.current_stage = ValidationStage.PASSED
                state.completed_at = datetime.now(timezone.utc).isoformat()
                log.info(f"Strategy {strategy_id} passed all validation gates!")
            else:
                state.current_stage = STAGE_ORDER[idx + 1]
        else:
            state.current_stage = ValidationStage.PASSED
            state.completed_at = datetime.now(timezone.utc).isoformat()
    else:
        state.current_stage = ValidationStage.FAILED
        state.completed_at = datetime.now(timezone.utc).isoformat()
        log.warning(f"Strategy {strategy_id} failed at {stage.value}: {detail}")

    pipelines[strategy_id] = _state_to_dict(state)
    _save_pipelines(pipelines)
    return state


def run_replay_gate(strategy_id: str, backtest_result: dict) -> GateResult:
    """
    Replay 门槛：基础回放验证

    条件：
    - 回测成功完成
    - 总交易数 ≥ 1
    - 无异常崩溃
    """
    if not backtest_result:
        return GateResult(ValidationStage.REPLAY, False, "回测结果为空")

    trades = backtest_result.get("total_trades", 0)
    if trades < 1:
        return GateResult(ValidationStage.REPLAY, False, f"总交易数为 {trades}，不满足最低要求")

    # Replay 门槛相对宽松，只要回测能正常运行即通过
    return GateResult(
        ValidationStage.REPLAY,
        True,
        f"回放验证通过：{trades} 笔交易，夏普 {backtest_result.get('sharpe_ratio', 0):.2f}",
    )


def run_scientific_gate(strategy_id: str, validation: dict) -> GateResult:
    """
    Scientific 门槛：五重统计检验

    条件（全部满足）：
    - PBO ≤ 0.5
    - DSR > 0
    - NW t-stat > 1.65（单尾 5% 显著性）
    - SPA p-value < 0.05（如有）
    """
    if not validation:
        return GateResult(ValidationStage.SCIENTIFIC, False, "检验结果为空")

    checks = []
    pbo = validation.get("pbo", 1.0)
    dsr = validation.get("dsr", 0)
    nw_t = validation.get("nw_t_stat", 0)
    spa_p = validation.get("spa_p_value")

    if pbo > 0.5:
        checks.append(f"PBO={pbo:.2%} > 50%")
    if dsr <= 0:
        checks.append(f"DSR={dsr:.4f} ≤ 0")
    if abs(nw_t) < 1.65:
        checks.append(f"NW t-stat={nw_t:.2f} < 1.65")
    if spa_p is not None and spa_p >= 0.05:
        checks.append(f"SPA p={spa_p:.4f} ≥ 0.05")

    if checks:
        return GateResult(ValidationStage.SCIENTIFIC, False, "; ".join(checks))

    return GateResult(
        ValidationStage.SCIENTIFIC,
        True,
        f"Scientific 验证通过：PBO={pbo:.2%}, DSR={dsr:.2f}, NW t={nw_t:.2f}",
    )


def run_production_gate(
    strategy_id: str,
    sim_sharpe: float,
    live_sharpe: float,
    sim_max_dd: float,
    live_max_dd: float,
) -> GateResult:
    """
    Production 门槛：模拟盘 24H 稳定性

    条件：
    - 夏普衰减 < 30%（即 live_sharpe / sim_sharpe > 0.7）
    - 最大回撤 < 40%
    """
    if sim_sharpe == 0:
        return GateResult(ValidationStage.PRODUCTION, False, "模拟盘无有效 Sharpe")

    sharpe_decay = 1 - (live_sharpe / sim_sharpe) if sim_sharpe > 0 else 1.0
    checks = []

    if sharpe_decay > 0.3:
        checks.append(f"夏普衰减={sharpe_decay:.1%} > 30%")
    if live_max_dd > 40:
        checks.append(f"实盘最大回撤={live_max_dd:.1f}% > 40%")

    if checks:
        return GateResult(ValidationStage.PRODUCTION, False, "; ".join(checks))

    return GateResult(
        ValidationStage.PRODUCTION,
        True,
        f"Production 验证通过：夏普衰减={sharpe_decay:.1%}, 最大回撤={live_max_dd:.1f}%",
    )


# ─── 便捷：从回测结果批量推进管线 ──────────────────────────────


def process_backtest_result(strategy_id: str, backtest_result: dict) -> PipelineState:
    """处理回测结果，自动推进前两道门槛"""
    # Replay
    replay = run_replay_gate(strategy_id, backtest_result)
    state = submit_gate(strategy_id, ValidationStage.REPLAY, replay.passed, replay.detail)

    if not replay.passed:
        return state

    # Scientific
    validation = backtest_result.get("validation", {})
    scientific = run_scientific_gate(strategy_id, validation)
    state = submit_gate(strategy_id, ValidationStage.SCIENTIFIC, scientific.passed, scientific.detail)

    return state
