"""AI 策略迭代引擎 — Phase 3 核心

流水线: AI生成→批量回测→五重检验→排序→Top-K反馈→收敛检测

P1-3: 数据持久化迁入 DB（IterationTaskRecord），替代 JSON 文件。
"""
import json
import time
import asyncio
import pathlib
import httpx
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import settings
from core.logger import log
from services.backtest_service import run_backtest, fetch_ohlcv, _increment_attempts

# 旧 JSON 文件路径（仅用于一次性迁移）
_LEGACY_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_LEGACY_TASKS_FILE = _LEGACY_DATA_DIR / "iteration_tasks.json"

# ─── 系统提示词 ────────────────────────────────────────────────

ITERATOR_SYSTEM_PROMPT = """You are a quantitative strategy generator. Your job is to explore the parameter space and generate diverse trading strategy variants.

Given market conditions, user goals, risk constraints, and optionally the top-performing strategies from previous rounds, generate N strategy variants (JSON array).

Each variant must have:
- strategy_type: "ma_crossover" | "rsi" | "bollinger"
- params: strategy-specific parameters
- rationale: 1-2 sentences explaining why this variant might work well

Parameter ranges:
- ma_crossover: {"fast": int (5-50), "slow": int (20-200)}
- rsi: {"period": int (7-21), "oversold": int (20-40), "overbought": int (60-80)}
- bollinger: {"period": int (10-30), "std_dev": float (1.5-3.0)}

IMPORTANT: Return ONLY the JSON array, no other text. Start with [ and end with ]."""

FEEDBACK_SYSTEM_PROMPT = """You are a quantitative strategy optimizer. You receive the top-K strategies from previous rounds with their backtest results and validation metrics.

Analyze WHY these strategies performed well, then generate N improved strategy variants that build on the winners' strengths while exploring nearby parameter spaces.

Return the SAME JSON array format. Start with [ and end with ]."""


# ─── 数据模型 ──────────────────────────────────────────────────

@dataclass
class StrategyVariant:
    strategy_type: str
    params: dict
    rationale: str = ""
    # 回测结果（异步填充）
    sharpe_is: float = 0.0
    sharpe_oos: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    # 验证结果
    pbo: float = 0.0
    dsr: float = 0.0
    nw_t_stat: float = 0.0
    spa_p_value: float = 0.0
    scientific_passed: bool = False
    # 综合评分
    score: float = 0.0
    # 状态
    status: str = "pending"  # pending | running | done | failed
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IterationRound:
    round_number: int
    variants: list[dict] = field(default_factory=list)  # list of StrategyVariant.to_dict()
    top_sharpe_is: float = 0.0
    top_sharpe_oos: float = 0.0
    top_score: float = 0.0
    ai_analysis: str = ""
    status: str = "pending"  # pending | generating | backtesting | done
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class IterationTask:
    task_id: str
    goal: str
    symbol: str
    timeframe: str
    variants_per_round: int
    max_rounds: int
    risk_constraints: dict
    current_round: int = 0
    rounds: list[dict] = field(default_factory=list)  # list of IterationRound.to_dict()
    total_variants: int = 0
    scientific_passed: int = 0
    converged: bool = False
    convergence_reason: str = ""
    status: str = "pending"  # pending | running | completed | failed
    created_at: str = ""
    completed_at: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def progress_pct(self) -> int:
        if self.max_rounds <= 0:
            return 100 if self.status == "completed" else 0
        return min(100, int(self.current_round / self.max_rounds * 100))

    @property
    def best_variant(self) -> dict | None:
        """返回所有轮次中评分最高的 variant"""
        best = None
        for r in self.rounds:
            for v in r.get("variants", []):
                if best is None or v.get("score", 0) > best.get("score", 0):
                    best = v
        return best


# ─── 持久化（P1-3: DB 替代 JSON）────────────────────────────────

async def _load_tasks() -> dict:
    """从 DB 加载任务列表摘要"""
    try:
        from db.database import async_session
        from db.models import IterationTaskRecord
        from sqlalchemy import select

        async with async_session() as session:
            r = await session.execute(select(IterationTaskRecord))
            rows = r.scalars().all()
            if not rows:
                # 尝试从旧 JSON 迁移
                await _migrate_from_json()
                r = await session.execute(select(IterationTaskRecord))
                rows = r.scalars().all()
            tasks = {}
            for row in rows:
                d = row.task_data or {}
                if not d:
                    # 回退到摘要字段
                    d = {
                        "task_id": row.task_id, "status": row.status,
                        "goal": row.goal, "symbol": row.symbol,
                        "timeframe": row.timeframe,
                        "max_rounds": row.max_rounds,
                        "current_round": row.current_round,
                        "total_variants": row.total_variants,
                        "scientific_passed": row.scientific_passed,
                        "best_variant": row.best_variant,
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                tasks[row.task_id] = d
            return tasks
    except Exception as e:
        log.warning(f"ai_iterator: _load_tasks failed: {e}")
        return {}


async def _save_tasks(tasks: dict):
    """保存任务列表到 DB（全量 upsert）"""
    try:
        from db.database import async_session
        from db.models import IterationTaskRecord
        from sqlalchemy import select

        async with async_session() as session:
            for task_id, data in tasks.items():
                r = await session.execute(
                    select(IterationTaskRecord).where(IterationTaskRecord.task_id == task_id)
                )
                row = r.scalar_one_or_none()
                fields = {
                    "status": data.get("status", "pending"),
                    "goal": data.get("goal", ""),
                    "symbol": data.get("symbol", "BTC/USDT"),
                    "timeframe": data.get("timeframe", "1h"),
                    "max_rounds": data.get("max_rounds", 3),
                    "current_round": data.get("current_round", 0),
                    "total_variants": data.get("total_variants", 0),
                    "scientific_passed": data.get("scientific_passed", 0),
                    "best_variant": data.get("best_variant"),
                }
                if row is None:
                    row = IterationTaskRecord(task_id=task_id, **fields)
                    session.add(row)
                else:
                    for k, v in fields.items():
                        setattr(row, k, v)
            await session.commit()
    except Exception as e:
        log.error(f"ai_iterator: _save_tasks failed: {e}")


async def _load_task_data(task_id: str) -> dict | None:
    """从 DB 加载单个任务完整详情"""
    try:
        from db.database import async_session
        from db.models import IterationTaskRecord
        from sqlalchemy import select

        async with async_session() as session:
            r = await session.execute(
                select(IterationTaskRecord).where(IterationTaskRecord.task_id == task_id)
            )
            row = r.scalar_one_or_none()
            if row and row.task_data:
                return row.task_data
            return None
    except Exception:
        return None


async def _save_task_data(task_id: str, data: dict):
    """保存单个任务完整详情到 DB"""
    try:
        from db.database import async_session
        from db.models import IterationTaskRecord
        from sqlalchemy import select

        async with async_session() as session:
            r = await session.execute(
                select(IterationTaskRecord).where(IterationTaskRecord.task_id == task_id)
            )
            row = r.scalar_one_or_none()
            fields = {
                "status": data.get("status", "pending"),
                "goal": data.get("goal", ""),
                "symbol": data.get("symbol", "BTC/USDT"),
                "timeframe": data.get("timeframe", "1h"),
                "max_rounds": data.get("max_rounds", 3),
                "current_round": data.get("current_round", 0),
                "total_variants": data.get("total_variants", 0),
                "scientific_passed": data.get("scientific_passed", 0),
                "best_variant": data.get("best_variant"),
                "task_data": data,
            }
            if row is None:
                row = IterationTaskRecord(task_id=task_id, **fields)
                session.add(row)
            else:
                for k, v in fields.items():
                    setattr(row, k, v)
            await session.commit()
    except Exception as e:
        log.error(f"ai_iterator: _save_task_data failed: {e}")


async def _migrate_from_json():
    """一次性迁移：JSON 文件 → DB"""
    try:
        if _LEGACY_TASKS_FILE.exists():
            raw = json.loads(_LEGACY_TASKS_FILE.read_text(encoding="utf-8"))
            for task_id, data in raw.items():
                # 尝试加载详情文件
                detail_file = _LEGACY_DATA_DIR / f"iteration_data_{task_id}.json"
                task_data = None
                if detail_file.exists():
                    task_data = json.loads(detail_file.read_text(encoding="utf-8"))
                    detail_file.replace(detail_file.with_suffix(".migrated"))
                await _save_task_data(task_id, task_data or data)
            _LEGACY_TASKS_FILE.replace(_LEGACY_TASKS_FILE.with_suffix(".migrated"))
            log.info(f"ai_iterator: migrated {len(raw)} tasks from JSON")
    except Exception as e:
        log.warning(f"ai_iterator: JSON migration failed: {e}")


# ─── DeepSeek 调用 ─────────────────────────────────────────────

async def _call_deepseek(prompt: str, system_prompt: str, max_tokens: int = 2000) -> str:
    """调用 DeepSeek，返回 content 字符串"""
    key = settings.DEEPSEEK_API_KEY
    if not key:
        raise ValueError("DEEPSEEK_API_KEY not configured")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_variants(content: str) -> list[dict]:
    """解析 AI 输出为 variant 列表"""
    # 提取 JSON 数组
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        log.warning(f"Failed to extract JSON array from AI response: {content[:200]}")
        return []

    try:
        variants = json.loads(m.group())
        if not isinstance(variants, list):
            return []
        result = []
        for item in variants:
            if not isinstance(item, dict):
                continue
            st = item.get("strategy_type", "")
            if st not in ("ma_crossover", "rsi", "bollinger"):
                continue
            result.append(StrategyVariant(
                strategy_type=st,
                params=item.get("params", {}),
                rationale=item.get("rationale", ""),
            ).to_dict())
        return result
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error in AI response: {e}")
        return []


# ─── 回测执行 ──────────────────────────────────────────────────

def _run_single_backtest(variant: dict, ohlcv_df, capital: float, task_id: str, variant_idx: int) -> dict:
    """同步执行单个 variant 的回测 + 验证（在 async 线程中调用）"""
    v = dict(variant)
    try:
        _increment_attempts()
        result = run_backtest(
            ohlcv_df=ohlcv_df,
            strategy_type=v["strategy_type"],
            capital=capital,
            params=v["params"],
            with_validation=True,
        )
        # 基础指标
        v["total_return_pct"] = result.get("total_return_pct", 0)
        v["max_drawdown_pct"] = result.get("max_drawdown_pct", 0)
        v["win_rate"] = result.get("win_rate", 0)
        v["total_trades"] = result.get("total_trades", 0)
        v["profit_factor"] = result.get("profit_factor", 0)

        # 验证指标
        validation = result.get("validation", {})
        if validation and not validation.get("error"):
            v["sharpe_is"] = validation.get("sharpe_is", 0)
            v["sharpe_oos"] = validation.get("sharpe_oos", 0)
            v["pbo"] = validation.get("pbo", 0)
            v["dsr"] = validation.get("dsr", 0)
            v["nw_t_stat"] = validation.get("nw_t_stat", 0)
            v["spa_p_value"] = validation.get("spa_p_value", 0)
            v["scientific_passed"] = validation.get("scientific_passed", False)
        v["status"] = "done"
    except Exception as e:
        v["status"] = "failed"
        v["error"] = str(e)[:200]
        log.warning(f"Variant {task_id}#{variant_idx} backtest failed: {e}")
    return v


async def _batch_backtest(variants: list[dict], ohlcv_df, capital: float, task_id: str) -> list[dict]:
    """异步批量回测（使用线程池并发）"""
    loop = asyncio.get_event_loop()
    tasks = []
    for i, v in enumerate(variants):
        v["status"] = "running"
        tasks.append(loop.run_in_executor(
            None, _run_single_backtest, v, ohlcv_df, capital, task_id, i
        ))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for r in results:
        if isinstance(r, Exception):
            out.append({"status": "failed", "error": str(r)[:200]})
        else:
            out.append(r)
    return out


# ─── 排序 ──────────────────────────────────────────────────────

def _rank_variants(variants: list[dict]) -> list[dict]:
    """按 score = sharpe_is × 0.3 + sharpe_oos × 0.7 排序"""
    for v in variants:
        v["score"] = v.get("sharpe_is", 0) * 0.3 + v.get("sharpe_oos", 0) * 0.7
    return sorted(variants, key=lambda x: x.get("score", 0), reverse=True)


# ─── 收敛检测 ──────────────────────────────────────────────────

def _check_convergence(rounds: list[dict]) -> tuple[bool, str]:
    """检查是否收敛：连续 2 轮 Top-1 Sharpe(OOS) 改进 < 1%"""
    if len(rounds) < 2:
        return False, ""

    recent = rounds[-2:]
    oos_vals = []
    for r in recent:
        variants = r.get("variants", [])
        if variants:
            oos_vals.append(max(v.get("sharpe_oos", 0) for v in variants))

    if len(oos_vals) < 2:
        return False, ""

    prev_abs = abs(oos_vals[0])
    if prev_abs < 0.001:
        improvement = 0
    else:
        improvement = abs(oos_vals[1] - oos_vals[0]) / prev_abs

    if improvement < 0.01:
        return True, f"连续 2 轮 Top-1 Sharpe(OOS) 改进 < 1% ({improvement*100:.2f}%)，收敛"
    return False, ""


# ─── 市场数据获取 ──────────────────────────────────────────────

def _get_market_summary(symbol: str, timeframe: str) -> dict:
    """获取市场数据摘要（供 AI prompt 使用）"""
    try:
        import pandas as pd
        from ml.features import FeatureEngine
        fe = FeatureEngine()
        df = _fetch_ohlcv_sync(symbol, timeframe, 100)
        if df is None or len(df) < 2:
            return {"error": "No market data"}
        df_feat = fe.compute_features(df)
        if df_feat.empty:
            return {"error": "Feature computation failed"}
        latest = df_feat.iloc[-1]
        first = df.iloc[0]
        last = df.iloc[-1]
        trend = (float(last["close"]) / float(first["close"]) - 1) * 100 if len(df) >= 50 else 0
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": float(last.get("close", 0)),
            "period_return_pct": round(trend, 2),
            "bars": len(df),
            "indicators": {
                "rsi": round(float(latest.get("rsi_14", 50)), 1),
                "macd": round(float(latest.get("macd", 0)), 4),
                "volatility": round(float(latest.get("atr_14", 0)), 2) / float(last.get("close", 1)) * 100 if float(last.get("close", 1)) > 0 else 0,
                "ema9_vs_ema21": "above" if float(latest.get("ema_9", 0)) > float(latest.get("ema_21", 0)) else "below",
                "volume_ratio": round(float(latest.get("volume_ratio", 1)), 2),
            },
        }
    except Exception as e:
        log.warning(f"Market summary failed: {e}")
        return {"error": str(e)[:100]}


def _fetch_ohlcv_sync(symbol, timeframe, limit):
    """同步版本的 OHLCV 获取（供同步函数和线程池使用）"""
    try:
        import pandas as pd
        from core.exchange import ExchangeClient
        ex = ExchangeClient(
            exchange_name=settings.EXCHANGE_NAME,
            api_key=settings.EXCHANGE_API_KEY,
            secret=settings.EXCHANGE_SECRET,
            passphrase=settings.EXCHANGE_PASSPHRASE,
            testnet=settings.EXCHANGE_TESTNET,
        )
        df = ex.fetch_ohlcv(symbol, timeframe, limit)
        if df is not None and len(df) > 0:
            return df
    except Exception as e:
        log.warning(f"Sync OHLCV fetch failed: {e}")
    return None


# ─── 构建 prompt ────────────────────────────────────────────────

def _build_generation_prompt(
    goal: str,
    market: dict,
    risk: dict,
    variants_count: int,
    top_k: list[dict] | None = None,
) -> str:
    """构建策略生成 prompt"""
    parts = [f"Goal: {goal}\n"]

    if market and not market.get("error"):
        ind = market.get("indicators", {})
        vol_val = ind.get("volatility", "N/A")
        vol_str = f"{vol_val:.1f}%" if isinstance(vol_val, (int, float)) else str(vol_val)
        parts.append(
            f"Market: {market.get('symbol')} {market.get('timeframe')}\n"
            f"  Price: {market.get('current_price', 'N/A')}\n"
            f"  Period Return: {market.get('period_return_pct', 'N/A')}%\n"
            f"  RSI(14): {ind.get('rsi', 'N/A')}\n"
            f"  Volatility: {vol_str}\n"
            f"  EMA9 vs EMA21: {ind.get('ema9_vs_ema21', 'N/A')}\n"
            f"  Volume Ratio: {ind.get('volume_ratio', 'N/A')}\n"
        )

    parts.append(
        f"Risk Constraints:\n"
        f"  Max Drawdown: {risk.get('max_drawdown_pct', 20)}%\n"
        f"  Min Sharpe: {risk.get('min_sharpe', 0.8)}\n"
        f"  Max Concentration: {risk.get('max_concentration', 0.3)}\n"
    )

    if top_k:
        parts.append("\nTop Strategies from Previous Rounds:")
        for i, v in enumerate(top_k[:3]):
            parts.append(
                f"  #{i+1} {v.get('strategy_type')} params={v.get('params')} "
                f"Sharpe(IS)={v.get('sharpe_is', 0):.2f} Sharpe(OOS)={v.get('sharpe_oos', 0):.2f} "
                f"Scientifically Validated={v.get('scientific_passed', False)}"
            )
        parts.append("\nAnalyze why these worked and generate improved variants exploring nearby parameter spaces.")

    parts.append(f"\nGenerate {variants_count} diverse strategy variants as JSON array.")
    return "\n".join(parts)


# ─── 主循环 ────────────────────────────────────────────────────

async def _run_round(
    task_id: str,
    round_num: int,
    goal: str,
    symbol: str,
    timeframe: str,
    variants_count: int,
    risk: dict,
    capital: float = 10000,
    previous_rounds: list[dict] | None = None,
) -> dict:
    """执行一轮迭代：生成 → 回测 → 检验 → 排序"""
    rd = IterationRound(round_number=round_num, status="generating")
    log.info(f"Iteration {task_id} round {round_num}: generating variants...")

    # 1. 获取市场数据
    market = _get_market_summary(symbol, timeframe)

    # 2. 构建 prompt + 获取 Top-K 历史
    top_k = None
    if previous_rounds:
        all_variants = []
        for pr in previous_rounds:
            all_variants.extend(pr.get("variants", []))
        top_k = _rank_variants(all_variants)[:5]

    prompt = _build_generation_prompt(goal, market, risk, variants_count, top_k)
    system_prompt = FEEDBACK_SYSTEM_PROMPT if top_k else ITERATOR_SYSTEM_PROMPT

    # 3. 调用 AI 生成
    try:
        content = await _call_deepseek(prompt, system_prompt, max_tokens=3000)
        variants_raw = _parse_variants(content)
        if not variants_raw:
            rd.status = "failed"
            rd.error = "AI generated 0 valid variants"
            return rd.to_dict()
    except Exception as e:
        rd.status = "failed"
        rd.error = f"AI generation failed: {str(e)[:200]}"
        log.error(f"Iteration {task_id} AI error: {e}")
        return rd.to_dict()

    # 限制数量
    variants_raw = variants_raw[:variants_count]
    log.info(f"Iteration {task_id} round {round_num}: AI generated {len(variants_raw)} variants, backtesting...")

    # 4. 获取回测数据
    df, _ = fetch_ohlcv(symbol, timeframe, 500)

    # 5. 批量回测
    rd.status = "backtesting"
    results = await _batch_backtest(variants_raw, df, capital, task_id)

    # 6. 排序
    ranked = _rank_variants(results)
    rd.variants = ranked
    done = sum(1 for v in ranked if v["status"] == "done")
    sci = sum(1 for v in ranked if v.get("scientific_passed"))

    # 7. 记录最佳指标
    if ranked:
        rd.top_sharpe_is = max(v.get("sharpe_is", 0) for v in ranked)
        rd.top_sharpe_oos = max(v.get("sharpe_oos", 0) for v in ranked)
        rd.top_score = ranked[0].get("score", 0)

    rd.status = "done"
    log.info(
        f"Iteration {task_id} round {round_num}: {done}/{len(results)} completed, "
        f"{sci} scientifically validated, top_score={rd.top_score:.3f}"
    )
    return rd.to_dict()


# ─── API 入口 ──────────────────────────────────────────────────

async def start_iteration(
    goal: str,
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    variants: int = 10,
    max_rounds: int = 5,
    risk_constraints: dict | None = None,
    capital: float = 10000,
) -> str:
    """启动迭代任务，返回 task_id"""
    task_id = f"iter_{int(time.time() * 1000)}"
    risk = risk_constraints or {"max_drawdown_pct": 20, "min_sharpe": 0.8, "max_concentration": 0.3}

    task = IterationTask(
        task_id=task_id,
        goal=goal,
        symbol=symbol,
        timeframe=timeframe,
        variants_per_round=variants,
        max_rounds=max_rounds,
        risk_constraints=risk,
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        status="running",
    )

    # 保存初始状态
    tasks = await _load_tasks()
    tasks[task_id] = task.to_dict()
    await _save_tasks(tasks)

    local_tasks = [task]  # 用于 _save_tasks 引用本地变量

    async def save_progress():
        """保存当前进度（包含 best_variant 计算）"""
        nonlocal local_tasks
        d = local_tasks[0].to_dict()
        # 计算 best_variant 并附加
        best = None
        for rd in d.get("rounds", []):
            for v in rd.get("variants", []):
                if best is None or v.get("score", 0) > best.get("score", 0):
                    best = v
        d["best_variant"] = best
        await _save_task_data(task_id, d)
        tasks = await _load_tasks()
        tasks[task_id] = d
        await _save_tasks(tasks)

    try:
        previous_rounds: list[dict] = []

        for r in range(1, max_rounds + 1):
            # 检查是否已收敛
            if task.converged:
                log.info(f"Iteration {task_id} converged at round {r-1}, stopping")
                break

            rd = await _run_round(
                task_id=task_id,
                round_num=r,
                goal=goal,
                symbol=symbol,
                timeframe=timeframe,
                variants_count=variants,
                risk=risk,
                capital=capital,
                previous_rounds=previous_rounds,
            )

            task.rounds.append(rd)
            task.current_round = r
            task.total_variants += len(rd.get("variants", []))
            task.scientific_passed += sum(
                1 for v in rd.get("variants", []) if v.get("scientific_passed")
            )
            previous_rounds.append(rd)
            await save_progress()

            # 收敛检测
            converged, reason = _check_convergence(task.rounds)
            if converged:
                task.converged = True
                task.convergence_reason = reason
                log.info(f"Iteration {task_id}: {reason}")
                break

        task.status = "completed"
        task.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        task.status = "failed"
        task.error = str(e)[:500]
        task.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
        log.error(f"Iteration {task_id} fatal error: {e}")
    finally:
        await save_progress()

    return task_id


async def get_task_status(task_id: str) -> dict | None:
    """获取任务当前状态"""
    # 优先读取详细数据
    detail = await _load_task_data(task_id)
    if detail:
        # 确保 best_variant 已计算
        if "best_variant" not in detail:
            best = None
            for rd in detail.get("rounds", []):
                for v in rd.get("variants", []):
                    if best is None or v.get("score", 0) > best.get("score", 0):
                        best = v
            detail["best_variant"] = best
        return detail
    # 回退到汇总
    tasks = await _load_tasks()
    return tasks.get(task_id)


async def list_tasks(limit: int = 20) -> list[dict]:
    """列出最近的任务"""
    tasks = await _load_tasks()
    items = list(tasks.values())
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit]


async def get_best_variant(task_id: str) -> dict | None:
    """获取迭代任务中的最优策略"""
    task_data = await _load_task_data(task_id)
    if not task_data:
        tasks = await _load_tasks()
        task_data = tasks.get(task_id)
    if not task_data:
        return None
    best = None
    for r in task_data.get("rounds", []):
        for v in r.get("variants", []):
            if best is None or v.get("score", 0) > best.get("score", 0):
                best = v
    return best
