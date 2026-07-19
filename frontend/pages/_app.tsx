import type { AppProps } from "next/app";
import { useRouter } from "next/router";
import Layout from "../components/Layout";
import { LanguageProvider } from "../lib/LanguageContext";
import { Toaster } from "react-hot-toast";
import "../styles/globals.css";

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  // /login 页面不渲染 Layout，避免 Layout 内的鉴权 SWR 轮询（kill-switch 等）
  // 在未登录时触发 401 → 重定向 → 重新挂载 → 再 401 的无限循环（页面闪烁）
  const isLoginPage = router.pathname === "/login";

  return (
    <LanguageProvider>
      {isLoginPage ? (
        <>
          <Component {...pageProps} />
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: { background: "#1a1a1a", color: "#eaecef", border: "1px solid #262626", fontSize: "13px" },
              success: { iconTheme: { primary: "#00c076", secondary: "#000" } },
              error: { iconTheme: { primary: "#f6465d", secondary: "#000" } },
            }}
          />
        </>
      ) : (
        <Layout>
          <Component {...pageProps} />
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: { background: "#1a1a1a", color: "#eaecef", border: "1px solid #262626", fontSize: "13px" },
              success: { iconTheme: { primary: "#00c076", secondary: "#000" } },
              error: { iconTheme: { primary: "#f6465d", secondary: "#000" } },
            }}
          />
        </Layout>
      )}
    </LanguageProvider>
  );
}
