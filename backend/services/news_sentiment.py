"""
新闻情绪分析 — CryptoPanic RSS + DeepSeek 情感分析

功能:
  - CryptoPanic 新闻聚合（免费 API + RSS fallback）
  - DeepSeek 情感分类：bullish / bearish / neutral
  - 关键词规则回退（DeepSeek 不可用时）
  - 情绪分数合成：加权平均 → 综合情绪信号
  - 情绪信号注入 Regime 检测器（辅助维度）

数据流:
  CryptoPanic → 解析标题+正文 → DeepSeek 分类 → 情绪分数向量 → 作为 Regime 辅助输入
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

from core.logger import log


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


class Sentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class NewsItem:
    """单条新闻"""
    title: str
    url: str
    source: str
    published_at: str                       # ISO 8601
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_score: float = 0.0            # -1.0 ~ +1.0
    confidence: float = 0.0                 # 置信度 0~1
    currencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "sentiment": self.sentiment.value,
            "sentiment_score": round(self.sentiment_score, 4),
            "confidence": round(self.confidence, 4),
            "currencies": self.currencies,
        }


@dataclass
class SentimentReport:
    """情绪分析报告"""
    symbol: str
    composite_score: float                  # 综合情绪分数 -1.0~+1.0
    composite_sentiment: Sentiment
    bullish_ratio: float                    # 看涨占比
    bearish_ratio: float                    # 看跌占比
    neutral_ratio: float                    # 中性占比
    news_count: int
    analyzed_count: int
    news_items: list[NewsItem] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "composite_score": round(self.composite_score, 4),
            "composite_sentiment": self.composite_sentiment.value,
            "bullish_ratio": round(self.bullish_ratio, 4),
            "bearish_ratio": round(self.bearish_ratio, 4),
            "neutral_ratio": round(self.neutral_ratio, 4),
            "news_count": self.news_count,
            "analyzed_count": self.analyzed_count,
            "news_items": [n.to_dict() for n in self.news_items[:10]],
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# 关键词规则回退（DeepSeek 不可用时）
# ------------------------------------------------------------------


class KeywordSentiment:
    """基于关键词规则的情绪分析"""

    BULLISH_PATTERNS = [
        r'\b(bullish|surge|rally|breakout|pump|moon|rocket|soar|spike)\b',
        r'\b(all.time.high|new.high|ATH|record)\b',
        r'\b(accumulat|buy|long|bid|inflow|adoption)\b',
        r'\b(ETF.approved|halving|partnership|launch|upgrade)\b',
        # 中文 — 不用 \b，中文不是 word character
        r'(上涨|飙升|突破|牛市|暴涨|利好|反弹|看涨)',
        r'(减半|ETF\s*通过|上线|合作|升级)',
    ]

    BEARISH_PATTERNS = [
        r'\b(bearish|crash|dump|plunge|collapse|decline|sell.off)\b',
        r'\b(all.time.low|new.low|ATL)\b',
        r'\b(distribut|sell|short|ask|outflow|liquidation)\b',
        r'\b(ban|regulat|crackdown|hack|exploit|scam|FUD)\b',
        # 中文 — 不用 \b
        r'(下跌|暴跌|崩盘|熊市|抛售|利空|看跌)',
        r'(监管|打击|黑客|攻击|漏洞|骗局)',
    ]

    @classmethod
    def analyze(cls, text: str) -> tuple[Sentiment, float, float]:
        """
        对文本做关键词规则分析
        返回: (sentiment, score, confidence)
        """
        text_lower = text.lower()
        bullish_hits = 0
        bearish_hits = 0

        for pattern in cls.BULLISH_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            bullish_hits += len(matches)

        for pattern in cls.BEARISH_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            bearish_hits += len(matches)

        total_hits = bullish_hits + bearish_hits

        if total_hits == 0:
            return Sentiment.NEUTRAL, 0.0, 0.3

        # 分数: [-1, +1]
        score = (bullish_hits - bearish_hits) / max(bullish_hits + bearish_hits, 1)

        # 置信度与命中次数正相关，最多 0.7（关键词法上限低）
        confidence = min(0.7, total_hits / 10)

        if score > 0.15:
            return Sentiment.BULLISH, round(score, 4), round(confidence, 4)
        elif score < -0.15:
            return Sentiment.BEARISH, round(score, 4), round(confidence, 4)
        else:
            return Sentiment.NEUTRAL, round(score, 4), round(confidence, 4)


# ------------------------------------------------------------------
# CryptoPanic News Fetcher
# ------------------------------------------------------------------


class CryptoPanicFetcher:
    """CryptoPanic 新闻获取器"""

    BASE_URL = "https://cryptopanic.com/api/v1"
    CACHE_TTL: float = 900.0  # 15分钟

    def __init__(self, auth_token: str = ""):
        self.auth_token = auth_token
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}

    async def fetch_news(
        self,
        currencies: list[str] | None = None,
        limit: int = 20,
    ) -> list[NewsItem]:
        """获取新闻列表"""
        cache_key = ",".join(sorted(currencies or [])) + f":{limit}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            return cached[1]

        news_items: list[NewsItem] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {
                    "public": "true",
                    "kind": "news",
                }
                if currencies:
                    params["currencies"] = ",".join(currencies)
                if self.auth_token:
                    params["auth_token"] = self.auth_token

                url = f"{self.BASE_URL}/posts/"
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                body = resp.json()

                if body.get("results"):
                    for item in body["results"][:limit]:
                        news_items.append(self._parse_item(item))

        except Exception as e:
            log.warning(f"CryptoPanicFetcher: API error: {e}")
            # 尝试 RSS 回退
            news_items = await self._fetch_rss_fallback(currencies, limit)

        self._cache[cache_key] = (time.time(), news_items)
        return news_items

    async def _fetch_rss_fallback(
        self, currencies: list[str] | None, limit: int
    ) -> list[NewsItem]:
        """RSS 回退方案"""
        items: list[NewsItem] = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = "https://cryptopanic.com/news/rss/"
                resp = await client.get(url)
                # 简单 HTML 解析（避免额外依赖）
                text = resp.text
                # 提取 title 标签中的标题
                titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', text)
                for title in titles[1:limit+1]:  # 跳过第一个 (频道标题)
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    if title:
                        items.append(NewsItem(
                            title=title,
                            url="",
                            source="CryptoPanic RSS",
                            published_at=datetime.now(timezone.utc).isoformat(),
                        ))
        except Exception as e:
            log.warning(f"CryptoPanicFetcher: RSS fallback also failed: {e}")

        return items

    def _parse_item(self, item: dict) -> NewsItem:
        """解析 API 返回的单条新闻"""
        # 提取涉及的币种
        currencies = []
        if item.get("currencies"):
            currencies = [c.get("code", "") for c in item["currencies"] if c.get("code")]

        return NewsItem(
            title=item.get("title", ""),
            url=item.get("url", ""),
            source=item.get("source", {}).get("title", "Unknown"),
            published_at=item.get("published_at", ""),
            currencies=currencies,
        )

    def clear_cache(self):
        self._cache.clear()


# ------------------------------------------------------------------
# NewsSentimentEngine — 主引擎
# ------------------------------------------------------------------


class NewsSentimentEngine:
    """新闻情绪分析引擎"""

    CACHE_TTL: float = 600.0  # 10分钟

    def __init__(self, deepseek_api_key: str = "", auth_token: str = ""):
        self.deepseek_api_key = deepseek_api_key
        self.fetcher = CryptoPanicFetcher(auth_token=auth_token)
        self._cache: dict[str, tuple[float, SentimentReport]] = {}

    async def analyze(
        self,
        symbol: str = "BTC/USDT",
        news_limit: int = 20,
        use_ai: bool = True,
    ) -> SentimentReport:
        """分析新闻情绪"""
        cache_key = f"{symbol}:{news_limit}:{use_ai}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            return cached[1]

        # 提取币种代码
        currency = symbol.split("/")[0] if "/" in symbol else symbol

        # 1) 获取新闻
        news_items = await self.fetcher.fetch_news(
            currencies=[currency],
            limit=news_limit,
        )

        if not news_items:
            report = self._empty_report(symbol)
            self._cache[cache_key] = (time.time(), report)
            return report

        # 2) 情感分析
        news_items = await self._analyze_sentiment(news_items, use_ai)

        # 3) 聚合
        analyzed = [n for n in news_items if n.confidence > 0]
        total = len(news_items)
        analyzed_count = len(analyzed)

        if analyzed_count == 0:
            report = SentimentReport(
                symbol=symbol,
                composite_score=0.0,
                composite_sentiment=Sentiment.NEUTRAL,
                bullish_ratio=0.0,
                bearish_ratio=0.0,
                neutral_ratio=1.0,
                news_count=total,
                analyzed_count=0,
                news_items=news_items,
            )
        else:
            bullish = sum(1 for n in analyzed if n.sentiment == Sentiment.BULLISH)
            bearish = sum(1 for n in analyzed if n.sentiment == Sentiment.BEARISH)
            neutral = analyzed_count - bullish - bearish

            # 加权综合分数
            weighted_sum = sum(n.sentiment_score * n.confidence for n in analyzed)
            total_confidence = sum(n.confidence for n in analyzed)
            composite = weighted_sum / total_confidence if total_confidence > 0 else 0.0

            # 综合情绪
            if composite > 0.1:
                comp_sentiment = Sentiment.BULLISH
            elif composite < -0.1:
                comp_sentiment = Sentiment.BEARISH
            else:
                comp_sentiment = Sentiment.NEUTRAL

            report = SentimentReport(
                symbol=symbol,
                composite_score=round(composite, 4),
                composite_sentiment=comp_sentiment,
                bullish_ratio=round(bullish / analyzed_count, 4),
                bearish_ratio=round(bearish / analyzed_count, 4),
                neutral_ratio=round(neutral / analyzed_count, 4),
                news_count=total,
                analyzed_count=analyzed_count,
                news_items=news_items,
            )

        self._cache[cache_key] = (time.time(), report)
        log.info(f"NewsSentiment[{symbol}]: composite={report.composite_score:.3f} "
                 f"({report.bullish_ratio:.0%}B/{report.bearish_ratio:.0%}A/{report.neutral_ratio:.0%}N) "
                 f"from {analyzed_count}/{total} articles")
        return report

    async def _analyze_sentiment(
        self, news_items: list[NewsItem], use_ai: bool
    ) -> list[NewsItem]:
        """对新闻列表做情感分析"""
        if use_ai and self.deepseek_api_key:
            return await self._analyze_with_deepseek(news_items)
        else:
            return self._analyze_with_keywords(news_items)

    async def _analyze_with_deepseek(self, news_items: list[NewsItem]) -> list[NewsItem]:
        """使用 DeepSeek API 做情感分析"""
        try:
            # 批量分析（减少 API 调用）
            titles = [n.title for n in news_items]
            batch_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))

            prompt = f"""You are a crypto news sentiment analyzer. For each of the following news headlines, classify the sentiment as one of: bullish, bearish, or neutral. Provide a sentiment score from -1.0 (very bearish) to +1.0 (very bullish) and a confidence from 0.0 to 1.0.

Return ONLY a valid JSON array where each element has: {{"index": number, "sentiment": "bullish"|"bearish"|"neutral", "score": number, "confidence": number}}

News headlines:
{batch_text}

JSON response:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 2000,
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"].strip()

                # 提取 JSON
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    results = json.loads(json_match.group())
                    for r in results:
                        idx = r.get("index", 0) - 1
                        if 0 <= idx < len(news_items):
                            news_items[idx].sentiment = Sentiment(r.get("sentiment", "neutral"))
                            news_items[idx].sentiment_score = float(r.get("score", 0))
                            news_items[idx].confidence = float(r.get("confidence", 0.5))

                    log.info(f"DeepSeek analyzed {len(results)} news items")
                    return news_items

        except Exception as e:
            log.warning(f"DeepSeek sentiment analysis failed: {e}, falling back to keywords")

        # Fallback
        return self._analyze_with_keywords(news_items)

    @staticmethod
    def _analyze_with_keywords(news_items: list[NewsItem]) -> list[NewsItem]:
        """关键词规则回退"""
        for item in news_items:
            sentiment, score, confidence = KeywordSentiment.analyze(item.title)
            item.sentiment = sentiment
            item.sentiment_score = score
            item.confidence = confidence
        return news_items

    def clear_cache(self):
        self._cache.clear()
        self.fetcher.clear_cache()

    @staticmethod
    def _empty_report(symbol: str) -> SentimentReport:
        return SentimentReport(
            symbol=symbol,
            composite_score=0.0,
            composite_sentiment=Sentiment.NEUTRAL,
            bullish_ratio=0.0,
            bearish_ratio=0.0,
            neutral_ratio=1.0,
            news_count=0,
            analyzed_count=0,
        )


# 全局单例（延迟初始化 DeepSeek Key）
_engine: Optional[NewsSentimentEngine] = None


def get_news_sentiment_engine() -> NewsSentimentEngine:
    global _engine
    if _engine is None:
        from config import settings
        api_key = getattr(settings, "DEEPSEEK_API_KEY", "")
        auth_token = getattr(settings, "CRYPTOPANIC_AUTH_TOKEN", "")
        _engine = NewsSentimentEngine(
            deepseek_api_key=api_key,
            auth_token=auth_token,
        )
    return _engine
