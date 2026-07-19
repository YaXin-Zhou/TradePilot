/** 骨架屏加载组件 — 仪表盘/交易/回测三个页面 */
import React from "react";

interface SkeletonProps {
  className?: string;
}

function Pulse({ className = "" }: SkeletonProps) {
  return <div className={`animate-pulse bg-[#1a1a1a] rounded ${className}`} />;
}

/** 仪表盘骨架屏 */
export function DashboardSkeleton() {
  return (
    <div className="space-y-4 p-4">
      {/* 顶栏卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-[#0e0e0e] rounded-lg p-4 space-y-3 border border-[#1a1a1a]">
            <Pulse className="h-3 w-20" />
            <Pulse className="h-7 w-32" />
            <Pulse className="h-3 w-16" />
          </div>
        ))}
      </div>
      {/* 图表区 */}
      <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a]">
        <Pulse className="h-4 w-32 mb-4" />
        <Pulse className="h-[300px] w-full" />
      </div>
      {/* 底部网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a] space-y-3">
          <Pulse className="h-4 w-24" />
          <Pulse className="h-[200px] w-full" />
        </div>
        <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a] space-y-3">
          <Pulse className="h-4 w-24" />
          <Pulse className="h-[200px] w-full" />
        </div>
      </div>
    </div>
  );
}

/** 交易页面骨架屏 */
export function TradingSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 p-4">
      <div className="lg:col-span-2 bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a]">
        <Pulse className="h-[400px] w-full" />
      </div>
      <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a] space-y-4">
        <Pulse className="h-6 w-24" />
        <Pulse className="h-10 w-full" />
        <Pulse className="h-10 w-full" />
        <Pulse className="h-10 w-full" />
        <Pulse className="h-10 w-32" />
      </div>
    </div>
  );
}

/** 回测页面骨架屏 */
export function BacktestSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a] space-y-3">
        <Pulse className="h-4 w-28" />
        <div className="flex gap-4">
          <Pulse className="h-10 flex-1" />
          <Pulse className="h-10 w-24" />
        </div>
      </div>
      <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a]">
        <Pulse className="h-[300px] w-full" />
      </div>
      <div className="bg-[#0e0e0e] rounded-lg p-4 border border-[#1a1a1a] space-y-2">
        <Pulse className="h-4 w-20" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Pulse key={i} className="h-8 w-full" />
        ))}
      </div>
    </div>
  );
}
