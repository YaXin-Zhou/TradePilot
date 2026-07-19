import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import { API_BASE } from "@/lib/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    try { if (localStorage.getItem("auth_token")) router.push("/"); } catch {}
  }, []);

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok && data.access_token) {
        localStorage.setItem("auth_token", data.access_token);
        router.push("/");
      } else {
        setError(data.detail?.[0]?.msg || data.detail || "Auth failed");
      }
    } catch (e: any) {
      setError(e.message || "Network error");
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
        <p className="text-xs text-dark-400 mb-6">{mode === "login" ? "Sign in" : "Create account"}</p>
        {error && <div className="text-xs text-okx-red mb-4 p-2 rounded bg-okx-red/10">{error}</div>}
        <div className="space-y-4">
          <div>
            <label className="text-xs text-dark-400 block mb-1">Username</label>
            <input value={username} onChange={e => setUsername(e.target.value)} className="w-full" />
          </div>
          <div>
            <label className="text-xs text-dark-400 block mb-1">Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} className="w-full" />
          </div>
          <button onClick={handleSubmit} disabled={loading || !username || !password}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm py-2.5">
            {loading ? "Loading..." : mode === "login" ? "Sign In" : "Register"}
          </button>
        </div>
        <p className="text-xs text-dark-500 text-center mt-4">
          {mode === "login" ? (
            <>No account? <button onClick={() => setMode("register")} className="text-okx-green hover:underline">Register</button></>
          ) : (
            <>Have an account? <button onClick={() => setMode("login")} className="text-okx-green hover:underline">Sign In</button></>
          )}
        </p>
      </div>
    </div>
  );
}
