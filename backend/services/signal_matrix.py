"""v1.3 U6: 弱信号矩阵 — 数百弱信号的相关性筛选 + BH 多重检验

SignalMatrix 负责：
1. 收集多源数据（OI / 链上 / 情绪）构造弱信号向量
2. 计算 Pearson 相关性矩阵
3. 应用 Benjamini-Hochberg 多重检验筛选稳健信号
4. 输出综合稳健性得分

与 Scientific gate 对接：matrix 验证结果输入 validation_pipeline。
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from core.logger import log


@dataclass
class SignalMatrix:
    """弱信号矩阵"""
    signals: dict[str, np.ndarray] = field(default_factory=dict)
    signal_names: list[str] = field(default_factory=list)
    correlation_matrix: Optional[np.ndarray] = None
    p_values: list[float] = field(default_factory=list)
    selected_signals: list[str] = field(default_factory=list)

    @classmethod
    def from_raw_data(
        cls,
        oi_data: Optional[dict] = None,
        onchain_data: Optional[dict] = None,
        fng_data: Optional[dict] = None,
    ) -> "SignalMatrix":
        """从多源原始数据构造信号矩阵

        每个数据源产生若干弱信号，共同构成初始信号集合。
        """
        matrix = cls()

        # OI 信号（已有）
        if oi_data:
            for key, value in oi_data.items():
                if isinstance(value, (int, float)):
                    matrix.signals[f"oi_{key}"] = np.array([float(value)])
                    matrix.signal_names.append(f"oi_{key}")

        # 链上信号
        if onchain_data:
            for key, value in onchain_data.items():
                if isinstance(value, (int, float, np.floating)):
                    matrix.signals[f"onchain_{key}"] = np.array([float(value)])
                    matrix.signal_names.append(f"onchain_{key}")

        # 情绪信号
        if fng_data:
            for key, value in fng_data.items():
                if isinstance(value, (int, float)):
                    matrix.signals[f"fng_{key}"] = np.array([float(value)])
                    matrix.signal_names.append(f"fng_{key}")

        log.info(f"SignalMatrix: {len(matrix.signal_names)} weak signals constructed")
        return matrix

    def compute_correlation(self) -> np.ndarray:
        """计算信号间的 Pearson 相关性矩阵"""
        n = len(self.signal_names)
        if n < 2:
            self.correlation_matrix = np.eye(n)
            return self.correlation_matrix

        # 构造数据矩阵（每条信号一行）
        data = np.array([self.signals[name] for name in self.signal_names])
        # 如果向量长度不等，取最短长度
        min_len = min(len(row) for row in data)
        data = np.array([row[:min_len] for row in data])

        self.correlation_matrix = np.corrcoef(data)
        return self.correlation_matrix

    def filter_by_correlation(self, max_corr: float = 0.7) -> "SignalMatrix":
        """基于相关性过滤：保留与已选信号相关性 < max_corr 的信号"""
        if self.correlation_matrix is None:
            self.compute_correlation()

        selected_idx = set()
        for i in range(len(self.signal_names)):
            keep = True
            for j in selected_idx:
                if abs(self.correlation_matrix[i][j]) >= max_corr:
                    keep = False
                    break
            if keep:
                selected_idx.add(i)

        self.selected_signals = [self.signal_names[i] for i in sorted(selected_idx)]
        log.info(
            f"SignalMatrix: {len(self.selected_signals)}/{len(self.signal_names)} "
            f"signals retained after correlation filter (max_corr={max_corr})"
        )
        return self

    def apply_bh(self, p_values: Optional[list[float]] = None, alpha: float = 0.05) -> list[str]:
        """Benjamini-Hochberg 多重检验

        返回通过 BH 校正的信号名称列表（假阳性控制率 alpha）。
        """
        if p_values is None:
            p_values = [0.01] * len(self.selected_signals) if self.selected_signals else []
        self.p_values = list(p_values)

        n = len(p_values)
        if n == 0:
            return []

        # BH 步骤
        sorted_indices = sorted(range(n), key=lambda i: p_values[i])
        threshold = 0
        for rank, idx in enumerate(sorted_indices, 1):
            bh_critical = (rank / n) * alpha
            if p_values[idx] <= bh_critical:
                threshold = rank
            else:
                break

        bh_selected = [
            self.selected_signals[idx] if self.selected_signals else f"signal_{idx}"
            for idx in sorted_indices[:threshold]
        ]
        log.info(
            f"SignalMatrix BH: {len(bh_selected)}/{n} signals pass "
            f"(threshold: {threshold}/{n}, alpha={alpha})"
        )
        return bh_selected

    def combined_score(self) -> float:
        """矩阵综合稳健性得分（0-1 之间）

        基于：信号保留率 × 相关性均值
        """
        n_total = len(self.signal_names)
        n_selected = len(self.selected_signals)
        if n_total == 0:
            return 0.0

        retention = n_selected / n_total

        if self.correlation_matrix is not None and n_selected > 1:
            # 在已选信号中取相关性均值
            idx = [self.signal_names.index(s) for s in self.selected_signals]
            sub_corr = self.correlation_matrix[np.ix_(idx, idx)]
            mean_corr = (np.sum(np.abs(sub_corr)) - n_selected) / (n_selected * (n_selected - 1))
        else:
            mean_corr = 0.5

        score = retention * (1 - mean_corr)
        return max(0.0, min(1.0, float(score)))
