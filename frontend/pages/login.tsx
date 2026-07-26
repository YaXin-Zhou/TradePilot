import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import { API_BASE } from "@/lib/api";
import { useLanguage } from "@/lib/LanguageContext";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  const { t } = useLanguage();

  useEffect(() => {
    try { if (localStorage.getItem("auth_token")) router.push("/"); } catch {}
  }, []);

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    try {
      if (mode === "register") {
        if (password.length < 8) {
          setError("密码至少 8 个字符");
          setLoading(false);
          return;
        }
        if (!/\d/.test(password)) {
          setError("密码必须包含至少 1 个数字");
          setLoading(false);
          return;
        }
        if (!/[a-zA-Z]/.test(password)) {
          setError("密码必须包含至少 1 个字母");
          setLoading(false);
          return;
        }
      }
      const res = await fetch(`${API_BASE}/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, email: `${username}@quant.com` }),
      });
      const data = await res.json();
      if (res.ok && data.access_token) {
        localStorage.setItem("auth_token", data.access_token);
        router.push("/");
      } else {
        setError(data.detail?.[0]?.msg || data.detail || t("auth.failed"));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("auth.networkError"));
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-950">
      <div className="card w-96">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-okx-green flex items-center justify-center flex-shrink-0">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/></svg>
          </div>
          <h2 className="text-lg font-semibold text-white">AI Quant Trade</h2>
        </div>
        <p className="text-xs text-dark-400 mb-6">
          {mode === "login" ? t("auth.signIn") : t("auth.createAccount")}
        </p>
        {error && <div className="text-xs text-okx-red mb-4 p-2 rounded bg-okx-red/10">{error}</div>}
        <div className="space-y-4">
          <div>
            <label className="text-xs text-dark-400 block mb-1">{t("auth.username")}</label>
            <input value={username} onChange={e => setUsername(e.target.value)} className="w-full" />
          </div>
          <div>
            <label className="text-xs text-dark-400 block mb-1">{t("auth.password")}</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full" />
            {mode === "register" && (
              <p className="text-xs text-dark-500 mt-1">密码至少 8 字符，需包含字母和数字</p>
            )}
          </div>
          <button onClick={handleSubmit} disabled={loading || !username || !password}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm py-2.5">
            {loading
              ? t("auth.loading")
              : mode === "login" ? t("auth.signInBtn") : t("auth.registerBtn")}
          </button>
        </div>
        <p className="text-xs text-dark-500 text-center mt-4">
          {mode === "login" ? (
            <>{t("auth.noAccount")} <button onClick={() => setMode("register")} className="text-okx-green hover:underline">{t("auth.register")}</button></>
          ) : (
            <>{t("auth.hasAccount")} <button onClick={() => setMode("login")} className="text-okx-green hover:underline">{t("auth.signInLink")}</button></>
          )}
        </p>
      </div>
    </div>
  );
}
