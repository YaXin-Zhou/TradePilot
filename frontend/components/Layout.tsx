import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  LayoutDashboard, TrendingUp, BarChart3, Settings,
  Activity, Wallet, LineChart, Menu, X, ChevronDown, Languages, LogIn, LogOut
} from "lucide-react";
import { getToken, clearToken } from "../lib/api"
import { useLanguage } from "../lib/LanguageContext";

const NAV_ITEMS = [
  { label: "nav.dashboard", icon: LayoutDashboard, href: "/", color: "#00c076" },
  { label: "nav.trading", icon: TrendingUp, href: "/trading", color: "#1e80ff" },
  { label: "nav.strategies", icon: BarChart3, href: "/strategies", color: "#f0b90b" },
  { label: "nav.analysis", icon: Activity, href: "/analysis", color: "#a855f7" },
 { label: "nav.wallet", icon: Wallet, href: "/wallet", color: "#848e9c" },
 { label: "nav.aiStrategy", icon: Activity, href: "/ai-strategy", color: "#6366f1" },
  { label: "nav.backtest", icon: BarChart3, href: "/backtest", color: "#f0b90b" },
 { label: "nav.settings", icon: Settings, href: "/settings", color: "#848e9c" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [exchangeStatus, setExchangeStatus] = useState<any>({ connected: true, testnet: true, has_api_key: false });
  const router = useRouter();
  const { t, lang, toggleLang } = useLanguage();
  const isMock = exchangeStatus && !exchangeStatus.connected;

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/exchange/status");
        const json = await res.json();
        if (json.success) setExchangeStatus(json.data);
      } catch {}
    };
    check();
    const iv = setInterval(check, 30000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-dark-950">
      {/* Sidebar */}
      <aside
        className={`flex flex-col border-r border-dark-800 bg-dark-900 transition-all duration-200 ${
          collapsed ? "w-16" : "w-56"
        }`}
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
          <h1 className="text-sm font-medium text-dark-200">
            {t(NAV_ITEMS.find((n) => n.href === router.pathname)?.label || "nav.dashboard")}
          </h1>
          <div className="flex items-center gap-4">
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
        {isMock && (
          <div className="px-4 py-2 bg-okx-yellow/10 border-b border-okx-yellow/20 flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-okx-yellow animate-pulse flex-shrink-0" />
            <span className="text-okx-yellow">
              {lang === "zh"
                ? "模拟模式 — 交易所连接不可用，显示的是模拟数据"
                : "Simulation mode — Exchange offline, showing simulated data"}
            </span>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
