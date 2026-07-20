/** v1.3 U3: 分析页 API 响应类型 */
export interface IndicatorsData {
  rsi?: number;
  volatility?: number;
  price_vs_sma20?: number;
  price_vs_sma50?: number;
  macd?: number;
  ma_cross?: string;
  volume_ratio?: number;
  [key: string]: unknown;
}

export interface PredictionData {
  signal?: string;
  prediction?: string;
  confidence?: number;
  current_price?: number;
  prob_up?: number;
  prob_down?: number;
  [key: string]: unknown;
}

export interface RegimeData {
  regime?: string;
  volatility?: number;
  [key: string]: unknown;
}

export interface TrainResultData {
  train_accuracy?: number;
  test_accuracy?: number;
  train_samples?: number;
  test_samples?: number;
  feature_count?: number;
  error?: string;
  [key: string]: unknown;
}
