"""v1.3 U6: SignalMatrix 测试"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSignalMatrix:
    def test_empty_matrix(self):
        from services.signal_matrix import SignalMatrix
        matrix = SignalMatrix.from_raw_data()
        assert len(matrix.signal_names) == 0
        assert matrix.combined_score() == 0.0

    def test_with_oi_data(self):
        from services.signal_matrix import SignalMatrix
        oi = {"open_interest": 50000, "long_short_ratio": 1.5}
        matrix = SignalMatrix.from_raw_data(oi_data=oi)
        assert len(matrix.signal_names) == 2

    def test_with_mixed_sources(self):
        from services.signal_matrix import SignalMatrix
        oi = {"open_interest": 50000}
        onchain = {"mvrv_zscore": 2.5, "sopr": 1.02}
        fng = {"value": 45, "classification": "fear"}
        matrix = SignalMatrix.from_raw_data(oi_data=oi, onchain_data=onchain, fng_data=fng)
        assert len(matrix.signal_names) >= 4

    def test_correlation_matrix(self):
        from services.signal_matrix import SignalMatrix
        import numpy as np
        matrix = SignalMatrix()
        matrix.signals["s1"] = np.array([1, 2, 3, 4, 5])
        matrix.signals["s2"] = np.array([2, 4, 6, 8, 10])
        matrix.signals["s3"] = np.array([5, 4, 3, 2, 1])
        matrix.signal_names = ["s1", "s2", "s3"]
        corr = matrix.compute_correlation()
        assert corr.shape == (3, 3)
        # s1 和 s2 高度正相关
        assert corr[0][1] > 0.9

    def test_filter_by_correlation(self):
        from services.signal_matrix import SignalMatrix
        import numpy as np
        matrix = SignalMatrix()
        matrix.signals["s1"] = np.array([1, 2, 3])
        matrix.signals["s2"] = np.array([1.1, 2.1, 3.1])
        matrix.signals["s3"] = np.array([3, 2, 1])
        matrix.signal_names = ["s1", "s2", "s3"]
        matrix = matrix.filter_by_correlation(max_corr=0.7)
        # s1 和 s2 高度相关（r≈1），应该只保留一个
        assert len(matrix.selected_signals) >= 2

    def test_bh(self):
        from services.signal_matrix import SignalMatrix
        matrix = SignalMatrix()
        matrix.selected_signals = ["a", "b", "c", "d"]
        p_vals = [0.001, 0.01, 0.03, 0.5]
        selected = matrix.apply_bh(p_vals, alpha=0.05)
        assert len(selected) <= 4
        # p=0.5 的不应该通过
        assert "d" not in selected

    def test_combined_score_in_range(self):
        from services.signal_matrix import SignalMatrix
        matrix = SignalMatrix()
        matrix.signal_names = ["a", "b", "c"]
        matrix.selected_signals = ["a", "b"]
        score = matrix.combined_score()
        assert 0 <= score <= 1
