// v1.3 U8: 全局加载骨架屏
export default function Loading() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-dark-950">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-okx-green/30 border-t-okx-green rounded-full animate-spin mx-auto mb-4" />
        <p className="text-dark-400 text-sm">Loading...</p>
      </div>
    </div>
  );
}
