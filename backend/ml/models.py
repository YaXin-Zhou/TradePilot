"""ML 模型 - 信号预测器"""
import os
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

from ml.features import FeatureEngine


class MLSignalPredictor:
    """使用 ML 模型预测交易信号"""

    def __init__(self, model_dir: str = "ml/models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.scaler = StandardScaler()
        self.feature_engine = FeatureEngine()
        self.is_trained = False
        self.feature_columns = []

    def _prepare_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """准备训练数据：用技术指标预测未来 N 根 K 线的涨跌"""
        df = self.feature_engine.compute_features(df)
        if df.empty:
            return np.array([]), np.array([])

        # 标签：未来 3 根 K 线后的涨跌 (1=涨, 0=跌)
        future_return = df["close"].shift(-3) / df["close"] - 1
        y = (future_return > 0.002).astype(int).values  # 0.2% 以上算涨

        # 特征列
        self.feature_columns = [
            c for c in self.feature_engine.DEFAULT_FEATURES
            if c in df.columns
        ]
        X = df[self.feature_columns].values

        # 对齐长度
        min_len = min(len(X), len(y))
        X, y = X[:min_len], y[:min_len]

        # 去掉尾部 NaN（因为 future_return 最后几个是 NaN）
        mask = ~np.isnan(y)
        X, y = X[mask], y[mask]

        return X, y

    def train(self, df: pd.DataFrame) -> dict:
        """训练模型"""
        X, y = self._prepare_data(df)
        if len(X) < 100:
            return {"error": f"数据不足，需要至少 100 个样本，当前 {len(X)}"}

        # 划分训练/测试
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # 标准化
        self.scaler.fit(X_train)
        X_train_scaled = self.scaler.transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # 训练 Gradient Boosting 模型
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )
        self.model.fit(X_train_scaled, y_train)

        # 评估
        train_acc = accuracy_score(y_train, self.model.predict(X_train_scaled))
        test_acc = accuracy_score(y_test, self.model.predict(X_test_scaled))
        self.is_trained = True

        # 保存
        self._save_model()

        return {
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "train_accuracy": round(train_acc, 4),
            "test_accuracy": round(test_acc, 4),
            "feature_count": len(self.feature_columns),
        }

    def predict(self, df: pd.DataFrame) -> Optional[dict]:
        """预测下一个交易信号"""
        if not self.is_trained or self.model is None:
            return None

        df = self.feature_engine.compute_features(df)
        if df.empty:
            return None

        latest = df.iloc[-1:]
        X = latest[[c for c in self.feature_columns if c in latest.columns]].values

        if len(X[0]) != len(self.feature_columns):
            return None

        X_scaled = self.scaler.transform(X)

        # 预测概率
        proba = self.model.predict_proba(X_scaled)[0]
        pred = self.model.predict(X_scaled)[0]

        current_price = float(latest["close"].values[0])
        confidence = float(max(proba))
        signal = "buy" if pred == 1 else "sell" if proba[0] < 0.4 else "neutral"

        return {
            "signal": signal,
            "confidence": round(confidence, 4),
            "current_price": current_price,
            "prediction": "up" if pred == 1 else "down",
            "prob_up": round(float(proba[1]), 4),
            "prob_down": round(float(proba[0]), 4),
        }

    def _save_model(self):
        joblib.dump(self.model, self.model_dir / "model.pkl")
        joblib.dump(self.scaler, self.model_dir / "scaler.pkl")
        joblib.dump(self.feature_columns, self.model_dir / "features.pkl")

    def load_model(self) -> bool:
        model_path = self.model_dir / "model.pkl"
        if not model_path.exists():
            return False
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(self.model_dir / "scaler.pkl")
        self.feature_columns = joblib.load(self.model_dir / "features.pkl")
        self.is_trained = True
        return True
