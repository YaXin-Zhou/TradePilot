// v2.0: 真实 Layout 组件测试（替换旧的假 SimpleLayout 测试）
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import Layout from "../../components/Layout";

// mock next/link → 渲染为 <a>
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: any) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// mock next/router
vi.mock("next/router", () => ({
  useRouter: () => ({ pathname: "/", push: vi.fn(), query: {} }),
}));

// mock SWR hooks（返回稳定数据，避免发请求）
vi.mock("../../lib/swr-config", () => ({
  useExchangeStatus: () => ({ data: { connected: true, testnet: true }, isLoading: false }),
  useKillSwitch: () => ({ data: { status: "ARMED" }, isLoading: false }),
}));

// mock i18n
vi.mock("../../lib/LanguageContext", () => ({
  useLanguage: () => ({
    lang: "zh",
    toggleLang: vi.fn(),
    t: (k: string) => k,
  }),
}));

// mock zustand store（支持 selector 与无参两种调用）
vi.mock("../../store/useAppStore", () => ({
  useAppStore: (selector?: any) => {
    const store = {
      currentSymbol: "BTC/USDT",
      setCurrentSymbol: vi.fn(),
      setExchangeStatus: vi.fn(),
    };
    return selector ? selector(store) : store;
  },
}));

// mock 通知中心（其内部有 SWR/订阅依赖）
vi.mock("../../components/NotificationCenter", () => ({
  default: () => <div data-testid="notification-center" />,
}));

// mock api 与 toast
vi.mock("../../lib/api", () => ({
  getToken: () => null,
  clearToken: vi.fn(),
  api: { emergencyStop: vi.fn(), emergencyReset: vi.fn() },
}));
vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

describe("Layout（真实组件）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("渲染导航项（NAV_ITEMS）", () => {
    render(<Layout><div>content</div></Layout>);
    // t() mock 返回 key 本身，故导航文案形如 nav.dashboard（桌面+移动端可能重复渲染）
    expect(screen.getAllByText(/^nav\./).length).toBeGreaterThanOrEqual(8);
    expect(screen.getAllByText("nav.dashboard").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("nav.trading").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("nav.backtest").length).toBeGreaterThanOrEqual(1);
  });

  it("渲染子内容", () => {
    render(<Layout><div data-testid="page-content">页面内容</div></Layout>);
    expect(screen.getByTestId("page-content")).toBeInTheDocument();
  });

  it("渲染通知中心", () => {
    render(<Layout><div /></Layout>);
    expect(screen.getByTestId("notification-center")).toBeInTheDocument();
  });
});
