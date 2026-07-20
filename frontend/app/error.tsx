"use client";
// v1.3 U8: 全局错误边界
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex items-center justify-center min-h-screen bg-dark-950">
      <div className="text-center max-w-md">
        <h2 className="text-lg font-semibold text-white mb-2">Something went wrong</h2>
        <p className="text-dark-400 text-sm mb-4">{error.message}</p>
        <button onClick={reset} className="btn-ghost text-sm">Try again</button>
      </div>
    </div>
  );
}
