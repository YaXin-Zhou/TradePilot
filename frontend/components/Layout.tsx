import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  LayoutDashboard, TrendingUp, BarChart3, Settings,
  Activity, Wallet, LineChart, Menu, X, ChevronDown, Languages, LogIn, LogOut, FlaskConical, Shield, AlertOctagon, Briefcase
} from "lucide-react";
import { getToken, clearToken, api } from "../lib/api"
import { useLanguage } from "../lib/LanguageContext";
import { useExchangeStatus, useKillSwitch } from "../lib/swr-config";
import { useAppStore } from "../store/useAppStore";
import NotificationCenter from "./NotificationCenter";
import toast from "react-hot-toast";

const NAV_ITEMS = [
  { label: "nav.dashboard", icon: LayoutDashboard, href: "/", color: "#00c076" },
  { label: "nav.trading", icon: TrendingUp, href: "/trading", color: "#1e80ff" },
  { label: "nav.positions", icon: Briefcase, href: "/positions", color: "#00c076" },
  { label: "nav.strategies", icon: BarChart3, href: "/strategies", color: "#f0b90b" },
  { label: "nav.analysis", icon: Activity, href: "/analysis", color: "#a855f7" },
 { label: "nav.wallet", icon: Wallet, href: "/wallet", color: "#848e9c" },
  { label: "nav.aiFactory", icon: Activity, href: "/ai-factory", color: "#6366f1" },
  { label: "nav.settings", icon: Settings, href: "/settings", color: "#848e9c" },
];


function SymbolSelector() {
  const { currentSymbol, setCurrentSymbol } = useAppStore();
  const symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
  return (
    <select
      value={currentSymbol}
      onChange={(e) => setCurrentSymbol(e.target.value)}
      className="w-full bg-dark-800 border border-dark-700 rounded-lg px-2 py-1.5 text-xs text-dark-200 focus:outline-none focus:border-okx-blue"
    >
      {symbols.map((s) => (
        <option key={s} value={s}>{s}</option>
      ))}
    </select>
  );
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [emergencyDialog, setEmergencyDialog] = useState(false);
  const [emergencyLoading, setEmergencyLoading] = useState(false);
  const router = useRouter();
  const { t, lang, toggleLang } = useLanguage();

  // SWR 自动轮询交易所状态（替代硬编码 fetch + setInterval）
  const { data: exchangeStatus } = useExchangeStatus();
  const { data: killSwitchData } = useKillSwitch();
  const setExchangeStatus = useAppStore((s) => s.setExchangeStatus);

  // 同步到全局 store
  useEffect(() => {
    if (exchangeStatus) {
      setExchangeStatus(
        exchangeStatus.connected ?? false,
        exchangeStatus.testnet ?? true
      );
    }
  }, [exchangeStatus, setExchangeStatus]);

  const isMock = !exchangeStatus?.connected;
  const isKilled = killSwitchData?.status === "TRIGGERED";

  // Phase 8: 紧急停止
  const handleEmergencyStop = async () => {
    setEmergencyLoading(true);
    try {
      const res = await api.emergencyStop("手动触发紧急停止", true);
      toast.success(lang === "zh" ? `紧急停止已执行：撤单 ${res.actions?.cancelled_orders || 0}，平仓 ${res.actions?.closed_positions || 0}` : "Emergency stop executed");
      setEmergencyDialog(false);
    } catch (e: unknown) {
      toast.error((e as Error).message || "紧急停止失败");
    } finally {
      setEmergencyLoading(false);
    }
  };

  const handleEmergencyReset = async () => {
    if (!confirm(lang === "zh" ? "确认解除紧急停止？恢复交易功能。" : "Confirm reset kill switch?")) return;
    try {
      await api.emergencyReset(true);
      toast.success(lang === "zh" ? "紧急停止已解除" : "Kill switch reset");
    } catch (e: unknown) {
      toast.error((e as Error).message || "解除失败");
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-dark-950">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`flex flex-col border-r border-dark-800 bg-dark-900 transition-all duration-200 z-40
          ${collapsed ? "w-16" : "w-56"}
          max-lg:fixed max-lg:left-0 max-lg:top-0 max-lg:h-full
          ${mobileOpen ? "max-lg:translate-x-0" : "max-lg:-translate-x-full"}
        `}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 h-14 px-4 border-b border-dark-800">
          <div className="w-8 h-8 rounded-lg bg-okx-green flex items-center justify-center flex-shrink-0">
            <LineChart size={18} className="text-black" />
          </div>
          {!collapsed && (
            <span className="text-sm font-bold tracking-tight text-white">
              AI Quant
            </span>
          )}
        </div>

        {/* Symbol Selector */}
        {!collapsed && (
          <div className="px-3 py-2 border-b border-dark-800">
            <SymbolSelector />
          </div>
        )}
        {/* Nav */}
        <nav className="flex-1 py-3 px-2 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const active = router.pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-sm ${
                  active
                    ? "bg-dark-800 text-white font-medium"
                    : "text-dark-300 hover:bg-dark-800/50 hover:text-dark-100"
                }`}
                title={collapsed ? t(item.label) : undefined}
              >
                <item.icon size={18} style={{ color: active ? item.color : undefined }} />
                {!collapsed && <span>{t(item.label)}</span>}
                {active && !collapsed && (
                  <div className="ml-auto w-1.5 h-1.5 rounded-full" style={{ background: item.color }} />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Language Toggle & Collapse */}
        <div className="p-3 border-t border-dark-800 space-y-2">
          <button
            onClick={toggleLang}
            className="flex items-center justify-center gap-2 w-full py-2 rounded-lg text-dark-400 hover:text-dark-200 hover:bg-dark-800 transition-all text-xs"
          >
            <Languages size={14} />
            {lang === "zh" ? "EN" : "中"}
          </button>
          {getToken() ? (
            <button onClick={() => { clearToken(); window.location.href = "/login" }}
              className="flex items-center justify-center gap-2 w-full py-2 rounded-lg text-dark-400 hover:text-dark-200 hover:bg-dark-800 transition-all text-xs">
              <LogOut size={14} /> {lang === "zh" ? "登出" : "Logout"}
            </button>
          ) : (
            <Link href="/login"
              className="flex items-center justify-center gap-2 w-full py-2 rounded-lg text-dark-400 hover:text-dark-200 hover:bg-dark-800 transition-all text-xs">
              <LogIn size={14} /> {lang === "zh" ? "登录" : "Login"}
            </Link>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center w-full py-2 rounded-lg text-dark-400 hover:text-dark-200 hover:bg-dark-800 transition-all"
          >
            {collapsed ? <Menu size={16} /> : <ChevronDown size={16} className="rotate-90" />}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col overflow-hidden bg-dark-950">
        {/* Top Bar */}
        <header className="flex items-center justify-between h-14 px-6 border-b border-dark-800 bg-dark-900/50">
          <div className="flex items-center gap-3">
            {/* Hamburger button (mobile) */}
            <button
              onClick={() => setMobileOpen(true)}
              className="lg:hidden flex items-center justify-center w-8 h-8 rounded-lg hover:bg-dark-800 text-dark-300"
            >
              <Menu size={18} />
            </button>
            <h1 className="text-sm font-medium text-dark-200">
            {t(NAV_ITEMS.find((n) => n.href === router.pathname)?.label || "nav.dashboard")}
          </h1>
          </div>
          <div className="flex items-center gap-4">
            <NotificationCenter />
            {/* Phase 8: 紧急停止按钮 / 解除按钮 */}
            {isKilled ? (
              <button
                onClick={handleEmergencyReset}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-okx-green/20 text-okx-green border border-okx-green/30 hover:bg-okx-green/30 transition-all"
              >
                <Shield size={14} />
                {lang === "zh" ? "解除紧急停止" : "Reset Kill Switch"}
              </button>
            ) : (
              <button
                onClick={() => setEmergencyDialog(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 transition-all"
              >
                <AlertOctagon size={14} />
                {lang === "zh" ? "紧急停止" : "Emergency Stop"}
              </button>
            )}
            <button
              onClick={toggleLang}
              className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
            >
              <Languages size={14} />
              {lang === "zh" ? "English" : "中文"}
            </button>
            <div className="flex items-center gap-2 text-xs">
              <span className={`w-2 h-2 rounded-full ${isMock ? "bg-okx-yellow" : "bg-okx-green"} animate-pulse`} />
              <span className="text-dark-400">
                {isMock
                  ? (lang === "zh" ? "模拟模式" : "Simulation")
                  : exchangeStatus?.testnet
                    ? "OKX Testnet"
                    : "OKX Live"}
              </span>
              {exchangeStatus?.latency_ms != null && !isMock && (
                <span className="text-dark-500">{exchangeStatus.latency_ms}ms</span>
              )}
            </div>
          </div>
        </header>

        {/* Content */}
        {isKilled && (
          <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/30 flex items-center gap-2 text-xs">
            <AlertOctagon size={14} className="text-red-400 flex-shrink-0" />
            <span className="text-red-400 font-medium">
              {lang === "zh"
                ? "⚠️ 紧急停止已触发 — 所有交易已冻结，需手动解除"
                : "⚠️ KILL SWITCH TRIGGERED — All trading frozen, manual reset required"}
            </span>
          </div>
        )}
        {isMock && !isKilled && (
          <div className="px-4 py-2 bg-okx-yellow/10 border-b border-okx-yellow/20 flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-okx-yellow animate-pulse flex-shrink-0" />
            <span className="text-okx-yellow">
              {lang === "zh"
                ? "模拟模式 — 交易所连接不可用，显示的是模拟数据"
                : "Simulation mode — Exchange offline, showing simulated data"}
            </span>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-4 lg:p-6">
          {children}
        </div>
      </main>

      {/* Phase 8: 紧急停止确认弹窗 */}
      {emergencyDialog && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => !emergencyLoading && setEmergencyDialog(false)}>
          <div className="bg-dark-900 border border-red-500/30 rounded-xl p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
                <AlertOctagon size={20} className="text-red-400" />
              </div>
              <h3 className="text-lg font-bold text-white">
                {lang === "zh" ? "确认紧急停止？" : "Confirm Emergency Stop?"}
              </h3>
            </div>
            <p className="text-sm text-dark-300 mb-4">
              {lang === "zh"
                ? "此操作将立即：\n1. 撤销所有挂单\n2. 市价平掉所有持仓\n3. 停止所有运行中策略\n\n交易将冻结，需手动解除。"
                : "This will immediately:\n1. Cancel all open orders\n2. Market-close all positions\n3. Stop all running strategies\n\nTrading will be frozen until manual reset."}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setEmergencyDialog(false)}
                disabled={emergencyLoading}
                className="flex-1 py-2.5 rounded-lg text-sm bg-dark-800 text-dark-200 hover:bg-dark-700 transition-all disabled:opacity-50"
              >
                {lang === "zh" ? "取消" : "Cancel"}
              </button>
              <button
                onClick={handleEmergencyStop}
                disabled={emergencyLoading}
                className="flex-1 py-2.5 rounded-lg text-sm bg-red-500 text-white hover:bg-red-600 transition-all disabled:opacity-50 font-medium"
              >
                {emergencyLoading
                  ? (lang === "zh" ? "执行中..." : "Executing...")
                  : (lang === "zh" ? "确认停止" : "Confirm Stop")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
