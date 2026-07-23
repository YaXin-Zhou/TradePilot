import { useEffect } from "react";

export default function AiLabRedirect() {
  useEffect(() => {
    window.location.href = "/ai-factory";
  }, []);

  return (
    <div className="page-container text-center py-16">
      <p className="text-dark-400">AI 实验室已合并到 AI 策略工厂，正在跳转...</p>
    </div>
  );
}
