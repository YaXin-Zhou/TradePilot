"""OnlineLearner 测试"""
import pytest
from services.online_learner import OnlineLearner, ExpertState, LearnerResult


class TestExpertState:
    def test_to_dict(self):
        e = ExpertState(strategy_id="s1", strategy_type="ma_cross",
                        weight=0.5, cumulative_loss=0.3)
        d = e.to_dict()
        assert d["strategy_id"] == "s1"
        assert d["weight"] == 0.5
        assert d["cumulative_loss"] == 0.3


class TestLearnerResult:
    def test_to_dict(self):
        r = LearnerResult(weights={"s1": 0.6, "s2": 0.4}, sleeping=["s3"],
                          learning_rate=0.1, iteration=5)
        d = r.to_dict()
        assert d["weights"]["s1"] == 0.6
        assert d["sleeping"] == ["s3"]
        assert d["iteration"] == 5


class TestOnlineLearner:
    def setup_method(self):
        self.learner = OnlineLearner()
        self.learner.reset()

    def test_initial_update(self):
        result = self.learner.update({"s1": 0.02, "s2": 0.05})
        assert len(result.weights) == 2
        # 收益高的权重应该更大
        assert result.weights["s2"] > result.weights["s1"]

    def test_sleeping_experts(self):
        self.learner.update({"s1": 0.02, "s2": 0.05})  # initial
        result = self.learner.update({"s1": 0.02, "s2": 0.05}, sleeping=["s1"])
        assert "s1" in result.sleeping
        # s1 权重应接近 min_weight
        assert result.weights["s1"] < 0.1

    def test_negative_returns(self):
        """亏损策略权重应降低"""
        result = self.learner.update({"s1": -0.05, "s2": 0.05, "s3": -0.02})
        assert result.weights["s2"] > result.weights["s1"]
        assert result.weights["s2"] > result.weights["s3"]

    def test_weights_sum_to_one(self):
        result = self.learner.update({"s1": 0.01, "s2": 0.02, "s3": 0.03})
        total = sum(result.weights.values())
        assert abs(total - 1.0) < 0.001

    def test_eta_adaptation(self):
        """多次迭代后学习率自适应"""
        for i in range(25):
            import random
            random.seed(i)
            rets = {
                "s1": random.uniform(-0.05, 0.05),
                "s2": random.uniform(-0.05, 0.05),
            }
            self.learner.update(rets)
        # 学习率应该发生了变化
        assert self.learner.eta != 0.1

    def test_get_weights(self):
        self.learner.update({"s1": 0.02, "s2": 0.05})
        w = self.learner.get_weights()
        assert "s1" in w
        assert "s2" in w

    def test_get_all_states(self):
        self.learner.update({"s1": 0.01, "s2": 0.02})
        states = self.learner.get_all_states()
        assert len(states) == 2
        assert all("strategy_id" in s for s in states)

    def test_reset(self):
        self.learner.update({"s1": 0.02, "s2": 0.05})
        self.learner.reset()
        assert self.learner.get_weights() == {}
        assert self.learner._iteration == 0
        assert self.learner.eta == 0.1

    def test_loser_weight_decreases(self):
        """长期亏损者权重持续下降"""
        for _ in range(10):
            self.learner.update({"winner": 0.03, "loser": -0.03})
        w = self.learner.get_weights()
        assert w["winner"] > w["loser"]

    def test_empty_update(self):
        result = self.learner.update({})
        assert result.weights == {}

    def test_new_expert_added(self):
        self.learner.update({"s1": 0.01})
        result = self.learner.update({"s1": 0.01, "s2": 0.02})
        assert "s2" in result.weights
