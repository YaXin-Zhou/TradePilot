"""回测验证体系 — 五重统计学检验（IS/OOS + PBO + BH + DSR + Newey-West + SPA）"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from core.logger import log


@dataclass
class ValidationResult:
    """统计检验完整结果"""
    # IS/OOS
    sharpe_is: float = 0.0          # 样本内 Sharpe
    sharpe_oos: float = 0.0         # 样本外 Sharpe
    max_dd_is: float = 0.0          # 样本内最大回撤
    max_dd_oos: float = 0.0         # 样本外最大回撤
    is_bars: int = 0                # 样本内数据条数
    oos_bars: int = 0               # 样本外数据条数
    # PBO
    pbo: float = 0.0                # 过拟合概率（Bootstrap）
    pbo_warning: bool = False       # PBO > 0.5 警告
    pbo_bootstrap_runs: int = 200   # Bootstrap 重采样次数
    # BH + DSR
    bh_passed: bool = True          # Benjamini-Hochberg 检验通过
    bh_threshold: float = 0.05      # BH 动态阈值
    dsr: float = 0.0                # Deflated Sharpe Ratio
    total_attempts: int = 1         # 累计策略尝试次数
    # Newey-West
    nw_se: float = 0.0              # Newey-West 标准误
    nw_t_stat: float = 0.0          # NW t 统计量
    nw_lags: int = 0                # NW 滞后阶数
    # SPA
    spa_p_value: float = 1.0        # SPA bootstrap p-value
    spa_passed: Optional[bool] = None  # p < 0.05 → False（策略不优于基准）
    spa_bootstrap_runs: int = 1000
    # 综合判定
    scientific_passed: bool = False  # 全部检验通过
    warnings: list = field(default_factory=list)


# ─── IS/OOS 分割 ───────────────────────────────────────────────


def split_is_oos(data: pd.DataFrame, is_pct: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """将数据分割为样本内（IS）和样本外（OOS）"""
    if data is None or len(data) < 50:
        raise ValueError(f"Need at least 50 bars for IS/OOS split, got {len(data) if data is not None else 0}")
    split_idx = int(len(data) * is_pct)
    # 确保每个分区至少有 20 条数据
    if split_idx < 20:
        split_idx = 20
    if len(data) - split_idx < 20:
        split_idx = len(data) - 20
    return data.iloc[:split_idx].copy(), data.iloc[split_idx:].copy()


# ─── 通用：从 equity_curve 计算 Sharpe ─────────────────────────


def _equity_to_returns(equity_curve: list[dict]) -> np.ndarray:
    """从 equity curve 列表提取收益率序列"""
    if not equity_curve or len(equity_curve) < 2:
        return np.array([])
    vals = np.array([e["equity"] for e in equity_curve])
    returns = np.diff(vals) / vals[:-1]
    return returns[~np.isnan(returns)]


def compute_sharpe(equity_curve: list[dict], annual_factor: float = 365) -> float:
    """从 equity curve 计算年化 Sharpe Ratio"""
    rets = _equity_to_returns(equity_curve)
    if len(rets) < 2:
        return 0.0
    mean = np.mean(rets)
    std = np.std(rets, ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(mean / std * np.sqrt(annual_factor))


def compute_max_drawdown(equity_curve: list[dict]) -> float:
    """从 equity curve 计算最大回撤百分比"""
    if not equity_curve:
        return 0.0
    vals = np.array([e["equity"] for e in equity_curve])
    peak = np.maximum.accumulate(vals)
    dd = (peak - vals) / peak
    return float(np.max(dd) * 100)


# ─── PBO 过拟合概率 ────────────────────────────────────────────


def compute_pbo(
    is_data: pd.DataFrame,
    oos_data: pd.DataFrame,
    strategy_runner,
    strategy_type: str,
    params: dict,
    n_bootstrap: int = 200,
    random_seed: int = 42,
) -> float:
    """
    计算 Probability of Backtest Overfitting (PBO)

    方法：
    1. 对样本内数据做 N 次 Bootstrap 重采样
    2. 每次重采样后运行回测，记录 IS Sharpe
    3. 对每次重采样，在 OOS 上也运行回测，记录 OOS Sharpe
    4. PBO = P(IS 排名与 OOS 排名不一致) / 总组合对数

    返回 PBO 值（0-1），>0.5 表示过拟合风险高
    """
    rng = np.random.RandomState(random_seed)
    n_is = len(is_data)
    is_sharpes = []
    oos_sharpes = []

    for _ in range(n_bootstrap):
        # Bootstrap 采样（有放回）
        indices = rng.randint(0, n_is, size=n_is)
        boot_is = is_data.iloc[indices].reset_index(drop=True)

        try:
            result_is = strategy_runner(boot_is, **params)
            is_sharpes.append(result_is.sharpe_ratio)
        except Exception:
            is_sharpes.append(-999)

        try:
            result_oos = strategy_runner(oos_data, **params)
            oos_sharpes.append(result_oos.sharpe_ratio)
        except Exception:
            oos_sharpes.append(-999)

    is_arr = np.array(is_sharpes)
    oos_arr = np.array(oos_sharpes)

    # 过滤掉失败的运行
    valid = (is_arr > -990) & (oos_arr > -990)
    is_arr = is_arr[valid]
    oos_arr = oos_arr[valid]

    if len(is_arr) < 10:
        return 0.5  # 数据不足，无法可靠计算

    # 计算所有组合对的排名一致性
    n = len(is_arr)
    total_pairs = 0
    inconsistent = 0

    for i in range(n):
        for j in range(i + 1, n):
            total_pairs += 1
            is_rank = 1 if is_arr[i] > is_arr[j] else -1 if is_arr[i] < is_arr[j] else 0
            oos_rank = 1 if oos_arr[i] > oos_arr[j] else -1 if oos_arr[i] < oos_arr[j] else 0
            if is_rank != 0 and oos_rank != 0 and is_rank != oos_rank:
                inconsistent += 1

    pbo = inconsistent / total_pairs if total_pairs > 0 else 0.5
    return round(float(pbo), 4)


def compute_cscv_pbo(returns_matrix, n_splits: int = 16, random_seed: int = 42) -> float:
    """CSCV PBO（Bailey, Borwein, López de Prado & Zhu 2015）— 正确实现

    参数:
      returns_matrix: shape (n_trials, n_configs)，每个 config 的收益率序列（等长）

    返回 PBO ∈ [0,1]：IS 最优 config 在 OOS 中的平均相对排名（越高越可能过拟合）。
    注意：CSCV 需要「多个 config 的收益矩阵」，单 config 无法计算（退化为 0）。
    """
    from itertools import combinations

    M = np.asarray(returns_matrix, dtype=np.float64)
    if M.ndim != 2:
        return 0.5
    n_trials, n_configs = M.shape
    if n_trials < n_splits or n_configs < 2:
        return 0.5

    split_size = n_trials // n_splits
    if split_size < 1:
        return 0.5
    sub = [M[i * split_size:(i + 1) * split_size] for i in range(n_splits)]

    half = n_splits // 2
    combos = list(combinations(range(n_splits), half))
    if not combos:
        return 0.5

    pbo_sum = 0.0
    for combo in combos:
        is_idx = sorted(combo)
        oos_idx = sorted(set(range(n_splits)) - set(combo))
        is_sharpe = _sharpe_vector(np.vstack([sub[i] for i in is_idx]))
        oos_sharpe = _sharpe_vector(np.vstack([sub[i] for i in oos_idx]))
        is_best = int(np.argmax(is_sharpe))
        # IS 最优 config 在 OOS 中比多少 config 差（相对排名，归一化到 [0,1]）
        oos_rank = int(np.sum(oos_sharpe > oos_sharpe[is_best]))
        pbo_sum += oos_rank / (n_configs - 1)

    return round(float(pbo_sum / len(combos)), 4)


def _sharpe_vector(returns_matrix: np.ndarray) -> np.ndarray:
    """对每列（config）计算 Sharpe（不年化，排名不受年化因子影响）"""
    mean = np.mean(returns_matrix, axis=0)
    std = np.std(returns_matrix, axis=0, ddof=1)
    std = np.where(std == 0, 1e-9, std)
    return mean / std


# ─── BH 动态门槛 ───────────────────────────────────────────────


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> tuple[list[bool], float]:
    """
    Benjamini-Hochberg 多重检验校正

    给定 N 个策略的 p-value 列表，按排序动态调整拒绝阈值。
    返回 (是否通过列表, 动态阈值)。

    步骤：
    1. p 值从小到大排序
    2. 阈值 = alpha × rank / N
    3. 找到最大的 k 使得 p_{(k)} ≤ alpha × k / N
    4. 前 k 个策略视为显著
    """
    if not p_values:
        return [], alpha

    n = len(p_values)
    sorted_idx = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_idx]

    bh_threshold = alpha
    passed = [False] * n

    for k in range(1, n + 1):
        threshold = alpha * k / n
        if sorted_p[k - 1] <= threshold:
            passed[sorted_idx[k - 1]] = True
            bh_threshold = threshold
        else:
            break

    return passed, round(bh_threshold, 6)


# ─── DSR 通胀夏普 ──────────────────────────────────────────────


def compute_dsr(returns: np.ndarray, sharpe: float, total_attempts: int) -> float:
    """Deflated Sharpe Ratio（Bailey & López de Prado 2014 真实公式）

    DSR = Φ( (SR - SR₀)·√(N-1) / √(1 - γ₃·SR + ((γ₄-1)/4)·SR²) )

    其中：
      SR₀ = √(1/(T-1)) · ((1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e)))
      γ₃ = 收益偏度，γ₄ = 收益峰度，γ = 欧拉-马歇罗尼常数，e = 欧拉数

    返回 [0,1] 概率：越高表示越不可能因 N 次试验过拟合而虚高。
    旧实现 SR×√(1-1/N) 是伪公式，已移除。
    """
    from scipy.stats import norm, skew, kurtosis

    T = len(returns)
    N = total_attempts
    if T < 5 or N <= 1:
        return 0.0

    # 偏度 / 峰度（scipy fisher=True 返回 excess kurtosis，+3 得峰度）
    gamma3 = float(skew(returns))
    gamma4 = float(kurtosis(returns, fisher=True)) + 3.0

    # 零假设（所有 N 次试验真实 Sharpe=0）下的期望最大 Sharpe
    euler_gamma = 0.5772156649015329
    e = 2.718281828459045
    var_sr = 1.0 / (T - 1)
    try:
        z1 = float(norm.ppf(1.0 - 1.0 / N))
        z2 = float(norm.ppf(1.0 - 1.0 / (N * e)))
    except (ValueError, ZeroDivisionError):
        return 0.0
    sr0 = np.sqrt(var_sr) * ((1.0 - euler_gamma) * z1 + euler_gamma * z2)

    num = (sharpe - sr0) * np.sqrt(N - 1)
    den = np.sqrt(1.0 - gamma3 * sharpe + ((gamma4 - 1.0) / 4.0) * sharpe * sharpe)
    if den <= 0 or not np.isfinite(den):
        return 0.0
    return round(float(norm.cdf(num / den)), 4)


# ─── Newey-West 修正 ───────────────────────────────────────────


def compute_newey_west(equity_curve: list[dict]) -> dict:
    """
    Newey-West 异方差自相关稳健标准误

    对资金曲线收益率序列计算 HAC 标准误。
    滞后阶数 = ⌊T^(1/3)⌋（T 为样本量）

    返回 {se, t_stat, lags}
    """
    rets = _equity_to_returns(equity_curve)
    if len(rets) < 5:
        return {"se": 0.0, "t_stat": 0.0, "lags": 0}

    T = len(rets)
    lags = max(1, int(T ** (1 / 3)))
    mean_ret = np.mean(rets)

    # 计算残差
    residuals = rets - mean_ret

    # Newey-West 方差：σ² = (1/T)Σ(ê²ᵢ) + 2Σ_{j=1}^{lags} w_j Σ_{i=j+1}^{T} êᵢê_{i-j}
    # w_j = 1 - j/(lags+1)（Bartlett 核）
    nw_variance = np.sum(residuals ** 2)

    for j in range(1, lags + 1):
        weight = 1.0 - j / (lags + 1)
        autocov = np.sum(residuals[j:] * residuals[:-j])
        nw_variance += 2 * weight * autocov

    nw_variance = nw_variance / T
    # v2.0: 标准误 = sqrt(长期方差 / T)，补回 1/√T 因子（此前 t 统计量被高估 √T 倍）
    nw_se = np.sqrt(max(nw_variance / T, 1e-10))
    t_stat = mean_ret / nw_se if nw_se > 0 else 0.0

    return {
        "se": round(float(nw_se), 6),
        "t_stat": round(float(t_stat), 4),
        "lags": lags,
    }


# ─── SPA 检验 ─────────────────────────────────────────────────


def compute_spa(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    n_bootstrap: int = 1000,
    random_seed: int = 42,
) -> float:
    """
    Superior Predictive Ability (SPA) 检验

    H₀：策略不优于基准
    H₁：策略优于基准

    方法：
    1. 计算策略与基准的收益率差 d_t
    2. 对 d_t 做 Bootstrap 重采样
    3. 计算 SPA 统计量：max(mean(d) / se(d), 0)
    4. p-value = P(SPA* > SPA_observed)

    返回 p-value。p < 0.05 → 拒绝 H₀ → 策略显著优于基准
    """
    if len(strategy_returns) < 20 or len(benchmark_returns) < 20:
        return 1.0

    # 对齐长度
    min_len = min(len(strategy_returns), len(benchmark_returns))
    s_rets = strategy_returns[-min_len:]
    b_rets = benchmark_returns[-min_len:]

    # 收益率差
    d = s_rets - b_rets
    T = len(d)

    # 观测统计量
    mean_d = np.mean(d)
    std_d = np.std(d, ddof=1)
    if std_d == 0 or np.isnan(std_d):
        return 1.0
    spa_obs = max(mean_d / std_d * np.sqrt(T), 0) if mean_d > 0 else 0.0

    if spa_obs == 0:
        return 1.0

    # Bootstrap（移动块法，保持自相关）
    rng = np.random.RandomState(random_seed)
    centered = d - mean_d  # 去中心化（H0 下均值为 0）
    spa_boot = []
    block_size = max(5, int(np.sqrt(T)))

    for _ in range(n_bootstrap):
        boot_sample = _block_bootstrap(centered, block_size, rng)
        boot_mean = np.mean(boot_sample)   # ≈0，但携带抽样波动（这就是 H0 下的分布）
        boot_std = np.std(boot_sample, ddof=1)
        if boot_std == 0:
            spa_boot.append(0)
            continue
        # v2.1 修复：统计量用 boot_mean（已去中心化，均值≈0、有方差），
        # 原代码多减了 mean_d 导致 boot_mean-mean_d ≈ -mean_d < 0 → spa_val 恒 0 → p 恒 0
        spa_val = max(boot_mean / boot_std * np.sqrt(T), 0)
        spa_boot.append(spa_val)

    spa_boot = np.array(spa_boot)
    p_value = np.mean(spa_boot >= spa_obs)

    return round(float(p_value), 4)


def _block_bootstrap(data: np.ndarray, block_size: int, rng: np.random.RandomState) -> np.ndarray:
    """分块 Bootstrap 采样（移动块法 — Moving Block Bootstrap）"""
    T = len(data)
    n_blocks = int(np.ceil(T / block_size))
    boot = np.zeros(T)
    idx = 0
    for _ in range(n_blocks):
        start = rng.randint(0, T - block_size + 1)
        block = data[start:start + block_size]
        end = min(idx + block_size, T)
        boot[idx:end] = block[:end - idx]
        idx = end
        if idx >= T:
            break
    return boot[:T]


# ─── 综合验证 ──────────────────────────────────────────────────


def run_full_validation(
    data: pd.DataFrame,
    strategy_runner,
    strategy_type: str,
    params: dict,
    equity_curve: list[dict],
    total_attempts: int = 1,
    p_values_list: list[float] | None = None,
) -> ValidationResult:
    """
    运行完整五重统计学检验

    Args:
        data: 完整 OHLCV 数据
        strategy_runner: 策略运行函数，签名为 (df, **params) -> BacktestResult
        strategy_type: 策略类型标识
        params: 策略参数字典
        equity_curve: 完整回测的 equity_curve
        total_attempts: 累计策略尝试次数
        p_values_list: 历史上所有策略的 p-value 列表（用于 BH 校正）

    Returns:
        ValidationResult 完整检验结果
    """
    result = ValidationResult(total_attempts=total_attempts)
    warnings = []

    try:
        # 1. IS/OOS 分割
        is_data, oos_data = split_is_oos(data, is_pct=0.7)
        result.is_bars = len(is_data)
        result.oos_bars = len(oos_data)

        # 2. IS 回测
        bt_is = strategy_runner(is_data.copy(), **params)
        result.sharpe_is = bt_is.sharpe_ratio
        result.max_dd_is = bt_is.max_drawdown_pct

        # 3. OOS 回测
        bt_oos = strategy_runner(oos_data.copy(), **params)
        result.sharpe_oos = bt_oos.sharpe_ratio
        result.max_dd_oos = bt_oos.max_drawdown_pct

        # 4. PBO（v2.0: 已弃用——原实现为单配置 bootstrap、OOS 固定导致恒 0，且 CSCV 需跨变体矩阵）
        # 多重试验过拟合校正由下方 DSR（真实公式）承担，不再计算 PBO。
        result.pbo = 0.0
        result.pbo_warning = False

        # 5. DSR（v2.0: 真实公式，用 OOS 收益的偏度/峰度 + OOS Sharpe）
        oos_rets = _equity_to_returns(bt_oos.equity_curve)
        result.dsr = compute_dsr(oos_rets, result.sharpe_oos, total_attempts)

        # 6. Newey-West
        nw = compute_newey_west(equity_curve)
        result.nw_se = nw["se"]
        result.nw_t_stat = nw["t_stat"]
        result.nw_lags = nw["lags"]

        # 7. BH（如果有历史 p-value 列表）
        if p_values_list and len(p_values_list) > 0:
            # 用 NW t-stat 近似 p-value（双尾检验）
            from scipy import stats
            current_p = 2 * (1 - stats.norm.cdf(abs(result.nw_t_stat))) if result.nw_t_stat != 0 else 1.0
            all_p = p_values_list + [current_p]
            passed_list, bh_threshold = benjamini_hochberg(all_p)
            result.bh_passed = passed_list[-1]
            result.bh_threshold = bh_threshold
            if not result.bh_passed:
                warnings.append(f"BH 检验未通过：p={current_p:.4f} > 阈值={bh_threshold:.4f}")

        # 8. SPA（v2.0: 已弃用——原实现去中心化 bootstrap 逻辑错误导致恒 p≈0，
        # 恒通过无判别力；且 Hansen 的 stationary bootstrap 需正确 studentized max，暂不手写）
        # 策略是否优于基准的显著性由 DSR（多重试验校正）+ NW t（均值显著性）承担。
        result.spa_passed = None

        # 9. 综合判定 Scientific（v2.0: 用 DSR + NW t 统计量做真实显著性判定）
        base_checks = [
            result.sharpe_oos > 0,
            result.dsr >= 0.5,        # 50% 概率非过拟合
            result.nw_t_stat > 1.65,  # 单侧 5% 显著
            result.bh_passed,
        ]
        result.scientific_passed = all(base_checks)

    except Exception as e:
        log.warning(f"Validation failed: {e}")
        warnings.append(f"检验异常：{str(e)[:100]}")

    result.warnings = warnings
    return result


def _extract_pbo_params(strategy_type: str, params: dict, runner) -> dict:
    """从策略类型和参数中提取 PBO 运行所需参数"""
    if strategy_type == "ma_crossover":
        return {"fast_period": params.get("fast", 10), "slow_period": params.get("slow", 30)}
    elif strategy_type == "rsi":
        return {"period": params.get("period", 14), "oversold": params.get("oversold", 30), "overbought": params.get("overbought", 70)}
    elif strategy_type == "bollinger":
        return {"period": params.get("period", 20), "std_dev": params.get("std_dev", 2.0)}
    return {}
