import { Brain, RefreshCw, CheckCircle, XCircle } from "lucide-react";
import useSWR from "swr";
import { api } from "../lib/api";
import { useLanguage } from "../lib/LanguageContext";
import Skeleton from "./Skeleton";

interface IterationTask {
  task_id: string;
  status: string;
  goal: string;
  symbol: string;
  current_round: number;
  max_rounds: number;
  total_variants: number;
  scientific_passed: number;
  created_at: string;
}

function useIterationTasks() {
  return useSWR(
    "iteration:tasks",
    () => api.listIterationTasks(10) as Promise<IterationTask[]>,
    { refreshInterval: 5000, revalidateOnMount: true, keepPreviousData: true }
  );
}

export default function IterationProgress() {
  const { t, lang } = useLanguage();
  const { data: tasks, isLoading } = useIterationTasks();
  const isZh = lang === "zh";

  if (isLoading) return <Skeleton height={120} />;
  if (!tasks || tasks.length === 0) return null;

  const inProgress = tasks.filter((t) => t.status === "running" || t.status === "pending");

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <Brain size={16} className="text-okx-blue" />
        <span className="text-sm font-semibold text-white">
          {isZh ? "AI 迭代任务" : "AI Iteration Tasks"}
        </span>
        <span className="text-xs text-dark-400 ml-auto">
          {inProgress.length} {isZh ? "运行中" : "active"}
        </span>
      </div>

      {inProgress.length === 0 ? (
        <p className="text-xs text-dark-500 text-center py-4">
          {isZh ? "暂无运行中的迭代" : "No active iterations"}
        </p>
      ) : (
        <div className="space-y-2">
          {inProgress.slice(0, 5).map((task) => {
            const pct = Math.round((task.current_round / task.max_rounds) * 100);
            return (
              <div key={task.task_id} className="p-3 rounded bg-dark-800/50 border border-dark-700">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {task.status === "running" ? (
                      <RefreshCw size={12} className="text-okx-blue animate-spin" />
                    ) : task.status === "done" ? (
                      <CheckCircle size={12} className="text-green" />
                    ) : (
                      <XCircle size={12} className="text-red" />
                    )}
                    <span className="text-xs text-dark-200 truncate max-w-[300px]">
                      {task.goal.slice(0, 60)}{task.goal.length > 60 ? "..." : ""}
                    </span>
                  </div>
                  <span className="text-xs text-dark-400">{task.symbol}</span>
                </div>
                <div className="w-full h-2 bg-dark-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-okx-blue rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(pct, 2)}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-[10px] text-dark-500">
                    Round {task.current_round}/{task.max_rounds}
                  </span>
                  <span className="text-[10px] text-dark-500">
                    {task.total_variants} variants | {task.scientific_passed} passed
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
