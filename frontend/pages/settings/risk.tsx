import { useLanguage } from "../../lib/LanguageContext";
import { Shield, ArrowRight } from "lucide-react";

export default function RiskSettingsRedirect() {
  const { t, lang } = useLanguage();

  return (
    <div className="page-container max-w-2xl mx-auto text-center py-16">
      <Shield size={48} className="mx-auto mb-6 text-dark-500" />
      <h1 className="text-xl font-bold mb-3">
        {lang === "zh" ? "风控设置已迁移" : "Risk Settings Moved"}
      </h1>
      <p className="text-dark-400 text-sm mb-8 leading-relaxed">
        {lang === "zh"
          ? "全局风控已取消。现在风控分为两个独立的体系："
          : "Global risk control has been removed. Risk is now split into two independent systems:"}
      </p>

      <div className="grid grid-cols-2 gap-4 mb-8">
        <a
          href="/trading"
          className="card p-6 text-left hover:border-[#00c076]/30 transition-all group cursor-pointer"
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center">
              <Shield size={16} className="text-green-400" />
            </div>
            <span className="font-medium text-white group-hover:text-green-400 transition-colors">
              {lang === "zh" ? "手动交易风控" : "Manual Trading Risk"}
            </span>
          </div>
          <p className="text-dark-400 text-xs mb-3">
            {lang === "zh"
              ? "在交易页面设置：最大单笔金额、日亏损上限等"
              : "Set on Trading page: max order, daily loss limit, etc."}
          </p>
          <span className="text-xs text-green-400 flex items-center gap-1">
            {lang === "zh" ? "前往交易页" : "Go to Trading"}
            <ArrowRight size={12} />
          </span>
        </a>

        <a
          href="/ai-factory"
          className="card p-6 text-left hover:border-[#6366f1]/30 transition-all group cursor-pointer"
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 flex items-center justify-center">
              <Shield size={16} className="text-indigo-400" />
            </div>
            <span className="font-medium text-white group-hover:text-indigo-400 transition-colors">
              {lang === "zh" ? "策略风控" : "Strategy Risk"}
            </span>
          </div>
          <p className="text-dark-400 text-xs mb-3">
            {lang === "zh"
              ? "在策略工厂设置：止损、仓位、AI建议风控参数"
              : "Set in Strategy Factory: stop loss, position, AI risk params"}
          </p>
          <span className="text-xs text-indigo-400 flex items-center gap-1">
            {lang === "zh" ? "前往策略工厂" : "Go to AI Factory"}
            <ArrowRight size={12} />
          </span>
        </a>
      </div>
    </div>
  );
}
