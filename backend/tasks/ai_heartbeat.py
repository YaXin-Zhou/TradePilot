"""
AI 心跳 — 每 6 小时定时审查策略池

功能:
  1. 读取策略池当前状态（各策略权重/Sharpe/回撤/状态）
  2. 对比上一周期表现（Sharpe 变化、回撤变化、权重变化）
  3. 调用 DeepSeek 输出调整建议（降权 / 休眠 / 淘汰 / 新策略方向）
  4. 生成心跳报告（JSON），供前端通知中心展示
  5. 调整建议须经人工审核后执行（非自动执行）

设计原则:
  - AI 只给建议，不自动执行
  - 保留历史心跳记录（最近 20 条）
  - 无 DeepSeek Key 时输出基于规则的摘要
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx

from core.logger import log
from services.strategy_pool import strategy_pool, StrategyStatus


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


@dataclass
class StrategySnapshot:
    """单策略快照"""
    strategy_id: str
    name: str
    strategy_type: str
    weight: float
    sharpe: float
    max_drawdown: float
    consecutive_losses: int
    status: str
    total_trades: int

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "strategy_type": self.strategy_type,
            "weight": round(self.weight, 4),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "consecutive_losses": self.consecutive_losses,
            "status": self.status,
            "total_trades": self.total_trades,
        }


@dataclass
class HeartbeatResult:
    """心跳审查结果"""
    timestamp: float = field(default_factory=time.time)
    cycle: int = 0
    pool_summary: dict = field(default_factory=dict)
    strategies: list[StrategySnapshot] = field(default_factory=list)
    changes_since_last: list[str] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    ai_raw_response: str = ""              # DeepSeek 原始响应
    report_file: str = ""                   # 保存路径

    def to_dict(self) -> dict:
        dt = datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
        return {
            "timestamp": dt.isoformat(),
            "cycle": self.cycle,
            "pool_summary": self.pool_summary,
            "strategies": [s.to_dict() for s in self.strategies],
            "changes_since_last": self.changes_since_last,
            "recommendations": self.recommendations,
            "ai_raw_response": self.ai_raw_response[:500],
            "report_file": self.report_file,
        }


# ------------------------------------------------------------------
# AIHeartbeat
# ------------------------------------------------------------------


class AIHeartbeat:
    """AI 心跳引擎"""

    HISTORY_MAX: int = 20          # 保留最近 20 条
    REPORT_DIR: str = "data/heartbeats"

    def __init__(
        self,
        deepseek_api_key: str = "",
        report_dir: str | None = None,
    ):
        self.deepseek_api_key = deepseek_api_key
        self.report_dir = Path(report_dir or self.REPORT_DIR)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._history: list[HeartbeatResult] = []
        self._last_cycle: Optional[HeartbeatResult] = None
        self._cycle_count: int = 0

        # 加载历史
        self._load_history()

    async def beat(self) -> HeartbeatResult:
        """执行一次心跳审查"""
        self._cycle_count += 1
        log.info(f"AI Heartbeat: cycle #{self._cycle_count} starting")

        # 1) 拍快照
        summary = strategy_pool.summary()
        all_strategies = strategy_pool.list_all()

        snapshots = [
            StrategySnapshot(
                strategy_id=s.id,
                name=s.name,
                strategy_type=s.strategy_type,
                weight=s.weight,
                sharpe=s.running_sharpe,
                max_drawdown=s.running_max_dd,
                consecutive_losses=s.consecutive_losses,
                status=s.status.value,
                total_trades=s.total_trades,
            )
            for s in all_strategies
        ]

        # 2) 对比上次周期的变化
        changes = self._detect_changes(snapshots)

        # 3) AI 审查
        recommendations, ai_raw = await self._ai_review(
            summary, snapshots, changes
        )

        # 4) 生成报告
        result = HeartbeatResult(
            cycle=self._cycle_count,
            pool_summary=summary,
            strategies=snapshots,
            changes_since_last=changes,
            recommendations=recommendations,
            ai_raw_response=ai_raw,
        )

        # 5) 保存
        self._save_report(result)
        self._append_history(result)
        self._last_cycle = result

        log.info(f"AI Heartbeat: cycle #{self._cycle_count} complete, "
                 f"{len(recommendations)} recommendations pending review")
        return result

    def _detect_changes(self, current: list[StrategySnapshot]) -> list[str]:
        """对比上次周期，输出变化列表"""
        if not self._last_cycle:
            return ["Initial heartbeat — no previous cycle to compare"]

        prev_map = {s.strategy_id: s for s in self._last_cycle.strategies}
        changes = []

        for s in current:
            prev = prev_map.get(s.strategy_id)
            if prev is None:
                changes.append(f"[NEW] {s.name} joined pool "
                              f"(type={s.strategy_type}, weight={s.weight:.2%})")
                continue

            # Sharpe 变化
            sharpe_delta = s.sharpe - prev.sharpe
            if abs(sharpe_delta) > 0.1:
                direction = "↑" if sharpe_delta > 0 else "↓"
                changes.append(f"[SHARPE] {s.name}: {prev.sharpe:.2f} → {s.sharpe:.2f} ({direction}{abs(sharpe_delta):.2f})")

            # 回撤变化
            dd_delta = s.max_drawdown - prev.max_drawdown
            if dd_delta > 0.02:  # 回撤扩大 >2%
                changes.append(f"[DRAWDOWN] {s.name}: max DD {prev.max_drawdown:.1%} → {s.max_drawdown:.1%} (deepened)")

            # 状态变化
            if s.status != prev.status:
                changes.append(f"[STATUS] {s.name}: {prev.status} → {s.status}")

            # 连续亏损增加
            if s.consecutive_losses > prev.consecutive_losses and s.consecutive_losses >= 3:
                changes.append(f"[LOSSES] {s.name}: {s.consecutive_losses} consecutive losses (was {prev.consecutive_losses})")

            # 权重变化 >10%
            weight_delta = abs(s.weight - prev.weight) / max(prev.weight, 0.01)
            if weight_delta > 0.1:
                direction = "↑" if s.weight > prev.weight else "↓"
                changes.append(f"[WEIGHT] {s.name}: {prev.weight:.2%} → {s.weight:.2%} ({direction}{weight_delta:.0%})")

        # 检查被移除的策略
        current_ids = {s.strategy_id for s in current}
        for sid, prev_s in prev_map.items():
            if sid not in current_ids:
                changes.append(f"[REMOVED] {prev_s.name} no longer in pool (was {prev_s.status})")

        if not changes:
            changes.append("No significant changes since last cycle")

        return changes

    async def _ai_review(
        self,
        summary: dict,
        snapshots: list[StrategySnapshot],
        changes: list[str],
    ) -> tuple[list[dict], str]:
        """调用 DeepSeek 审查策略池"""
        recommendations: list[dict] = []

        if not self.deepseek_api_key:
            # 规则回退
            return self._rule_based_review(summary, snapshots, changes), ""

        try:
            # 构建 prompt
            strategies_text = "\n".join(
                f"- {s.name} ({s.strategy_type}): Sharpe={s.sharpe:.2f}, "
                f"MaxDD={s.max_drawdown:.1%}, Weight={s.weight:.2%}, "
                f"Losses={s.consecutive_losses}, Status={s.status}"
                for s in snapshots
            )

            changes_text = "\n".join(f"- {c}" for c in changes)

            prompt = f"""You are a quantitative trading strategy auditor. Review the following strategy pool and provide specific, actionable recommendations.

## Pool Summary
- Total: {summary.get('total_strategies', 0)}
- Active: {summary.get('active_count', 0)}
- Sleeping: {summary.get('sleeping_count', 0)}
- Avg Sharpe: {summary.get('avg_sharpe', 0):.2f}
- Max Correlation: {summary.get('max_correlation', 0):.2f}

## Strategies
{strategies_text}

## Changes Since Last Cycle
{changes_text}

## Your Task
Analyze the pool and provide recommendations in the following JSON format. Be specific — name exact strategies:

```json
{{
  "recommendations": [
    {{
      "action": "reduce_weight|increase_weight|sleep|eliminate|wake_up|new_direction|no_action",
      "strategy_name": "strategy name or 'N/A'",
      "reason": "specific reason based on data",
      "priority": "high|medium|low",
      "detail": "specific action to take (e.g. reduce weight from 0.25 to 0.10)"
    }}
  ],
  "overall_assessment": "brief summary of pool health"
}}
```

Return ONLY the JSON, no other text."""

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"].strip()

                # 提取 JSON
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    recommendations = parsed.get("recommendations", [])
                    log.info(f"DeepSeek reviewed pool: {len(recommendations)} recommendations")
                    return recommendations, content

        except Exception as e:
            log.warning(f"DeepSeek heartbeat review failed: {e}, falling back to rules")

        return self._rule_based_review(summary, snapshots, changes), ""

    @staticmethod
    def _rule_based_review(
        summary: dict,
        snapshots: list[StrategySnapshot],
        changes: list[str],
    ) -> list[dict]:
        """基于规则的策略审查"""
        recommendations = []

        for s in snapshots:
            # 连续亏损警告
            if s.consecutive_losses >= 5:
                recommendations.append({
                    "action": "sleep",
                    "strategy_name": s.name,
                    "reason": f"5+ consecutive losses",
                    "priority": "high",
                    "detail": f"Set {s.name} to SLEEPING — auto-triggered at 5 consecutive losses",
                })

            # Sharpe < -0.5 → 淘汰
            elif s.sharpe < -0.5 and s.status not in ("eliminated", "sleeping"):
                recommendations.append({
                    "action": "eliminate",
                    "strategy_name": s.name,
                    "reason": f"Sharpe {s.sharpe:.2f} < -0.5",
                    "priority": "high",
                    "detail": f"Remove {s.name} from pool — negative risk-adjusted returns",
                })

            # 回撤 > 30% 警告
            elif s.max_drawdown > 0.30 and s.status == "active":
                recommendations.append({
                    "action": "reduce_weight",
                    "strategy_name": s.name,
                    "reason": f"Max DD {s.max_drawdown:.1%} exceeds 30%",
                    "priority": "medium",
                    "detail": f"Consider reducing {s.name} weight to half of current ({s.weight:.1%})",
                })

            # Sharpe < 0 但还运行中
            elif s.sharpe < 0 and s.status == "active":
                recommendations.append({
                    "action": "reduce_weight",
                    "strategy_name": s.name,
                    "reason": f"Negative Sharpe ({s.sharpe:.2f})",
                    "priority": "low",
                    "detail": f"Monitor {s.name} closely, prepare to reduce weight if Sharpe stays negative",
                })

        if not recommendations:
            recommendations.append({
                "action": "no_action",
                "strategy_name": "N/A",
                "reason": "All strategies within acceptable parameters",
                "priority": "low",
                "detail": "Pool is healthy, no changes needed",
            })

        return recommendations

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _save_report(self, result: HeartbeatResult):
        """保存心跳报告到文件"""
        filename = f"heartbeat_{datetime.fromtimestamp(result.timestamp, tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.report_dir / filename
        try:
            filepath.write_text(
                json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result.report_file = str(filepath)
        except Exception as e:
            log.error(f"Failed to save heartbeat report: {e}")

    def _append_history(self, result: HeartbeatResult):
        """添加到内存历史"""
        self._history.append(result)
        if len(self._history) > self.HISTORY_MAX:
            self._history = self._history[-self.HISTORY_MAX:]

    def _load_history(self):
        """加载历史心跳报告"""
        try:
            files = sorted(self.report_dir.glob("heartbeat_*.json"), reverse=True)
            for f in files[:self.HISTORY_MAX]:
                try:
                    content = json.loads(f.read_text(encoding="utf-8"))
                    cycle = content.get("cycle", 0)
                    if cycle > self._cycle_count:
                        self._cycle_count = cycle
                except Exception:
                    pass
        except Exception:
            pass

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取最近 N 条历史"""
        return [h.to_dict() for h in self._history[-limit:]]

    def get_last_cycle(self) -> Optional[dict]:
        """获取上次心跳结果"""
        return self._last_cycle.to_dict() if self._last_cycle else None


# 全局单例
_heartbeat: Optional[AIHeartbeat] = None


def get_heartbeat() -> AIHeartbeat:
    global _heartbeat
    if _heartbeat is None:
        from config import settings
        api_key = getattr(settings, "DEEPSEEK_API_KEY", "")
        _heartbeat = AIHeartbeat(deepseek_api_key=api_key)
    return _heartbeat
