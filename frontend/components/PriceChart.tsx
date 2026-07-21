import { useState, useEffect, useRef } from "react";
import { useOHLCV } from "../lib/swr-config";

interface OHLCVData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LiveTicker {
  last: number;
  bid: number;
  ask: number;
  high: number;
  low: number;
  volume: number;
  change_pct: number;
}

export default function PriceChart({
  ticker,
}: {
  ticker?: LiveTicker;
}) {
  const [data, setData] = useState<OHLCVData[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [livePoints, setLivePoints] = useState<number[]>([]);

  // SWR 自动轮询 OHLCV（替代双重 useEffect + setInterval）
  const { data: ohlcvData } = useOHLCV();
  useEffect(() => {
    if (ohlcvData) setData(ohlcvData);
  }, [ohlcvData]);

  useEffect(() => {
    if (!ticker) return;
    setLivePoints((prev) => {
      const next = [...prev, ticker.last];
      return next.length > 60 ? next.slice(-60) : next;
    });
  }, [ticker]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const PAD = { top: 25, bottom: 30, left: 10, right: 60 };
    const chartH = H - PAD.top - PAD.bottom;

    const allCloses = [
      ...data.map((d) => d.close),
      ...(ticker ? [ticker.last] : []),
      ...livePoints,
    ];
    if (allCloses.length === 0) return;

    const high = Math.max(...allCloses);
    const low = Math.min(...allCloses);
    const range = high - low || 1;

    ctx.fillStyle = "#0d0d0d";
    ctx.fillRect(0, 0, W, H);

    ctx.strokeStyle = "#1a1a1a";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (chartH * i) / 4;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(W - PAD.right, y);
      ctx.stroke();
    }

    if (data.length > 0) {
      const candleW = Math.max(2, (W - PAD.left - PAD.right) / data.length - 1);
      const halfW = Math.max(1, candleW * 0.4);
      data.forEach((d, i) => {
        const x = PAD.left + i * (candleW + 1) + candleW / 2;
        const openY = PAD.top + chartH - ((d.open - low) / range) * chartH;
        const closeY = PAD.top + chartH - ((d.close - low) / range) * chartH;
        const highY = PAD.top + chartH - ((d.high - low) / range) * chartH;
        const lowY = PAD.top + chartH - ((d.low - low) / range) * chartH;
        const isUp = d.close >= d.open;
        const color = isUp ? "#00c076" : "#f6465d";
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();
        ctx.fillStyle = color;
        const bodyTop = Math.min(openY, closeY);
        const bodyH = Math.max(1, Math.abs(closeY - openY));
        ctx.fillRect(x - halfW, bodyTop, halfW * 2, bodyH);
      });
    }

    if (livePoints.length > 1) {
      ctx.strokeStyle = "#a855f7";
      ctx.lineWidth = 2;
      ctx.beginPath();
      const stepX = (W - PAD.left - PAD.right) / Math.max(livePoints.length, 1);
      livePoints.forEach((p, i) => {
        const x = W - PAD.right - (livePoints.length - 1 - i) * stepX;
        const y = PAD.top + chartH - ((p - low) / range) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    if (ticker) {
      const y = PAD.top + chartH - ((ticker.last - low) / range) * chartH;
      ctx.strokeStyle = "#f0b90b";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(W - PAD.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#f0b90b";
      ctx.font = "11px monospace";
      ctx.textAlign = "right";
      ctx.fillText(ticker.last.toFixed(2), W - PAD.right - 4, y - 4);
    }

    ctx.fillStyle = "#848e9c";
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    [high, (high + low) / 2, low].forEach((p) => {
      const y = PAD.top + chartH - ((p - low) / range) * chartH;
      ctx.fillText(p.toFixed(0), W - PAD.right - 4, y + 4);
    });
  }, [data, ticker, livePoints]);

  const priceColor = ticker
    ? ticker.change_pct >= 0 ? "#00c076" : "#f6465d"
    : "#eaecef";

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-xs text-dark-400">BTC/USDT</span>
            <div className="flex items-baseline gap-2">
              <span
                className="text-2xl font-bold font-mono transition-colors duration-300"
                style={{ color: priceColor }}
              >
                {(ticker?.last ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {ticker && (
                <span
                  className="text-sm font-mono"
                  style={{ color: priceColor }}
                >
                  {ticker.change_pct >= 0 ? "+" : ""}{ticker.change_pct?.toFixed(2)}%
                </span>
              )}
            </div>
          </div>
          {ticker && (
            <div className="flex gap-3 text-xs">
              <div className="text-center">
                <div className="text-dark-400">Bid</div>
                <div className="text-green font-mono font-medium">{ticker.bid.toLocaleString("en-US", { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="text-center">
                <div className="text-dark-400">Ask</div>
                <div className="text-red font-mono font-medium">{ticker.ask.toLocaleString("en-US", { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="text-center">
                <div className="text-dark-400">Spread</div>
                <div className="text-dark-200 font-mono">{(((ticker.ask - ticker.bid) / ticker.last) * 100).toFixed(4)}%</div>
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-dark-400">
          <span className="flex items-center gap-1">
            <span className={"w-1.5 h-1.5 rounded-full " + (ticker ? "bg-okx-green animate-pulse" : "bg-dark-500")} />
            LIVE
          </span>
          <span>Vol: {ticker?.volume?.toFixed(1) || "-"}</span>
        </div>
      </div>
      <canvas ref={canvasRef} className="w-full rounded cursor-crosshair" style={{ height: "260px" }} />
    </div>
  );
}