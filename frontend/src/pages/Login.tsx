import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Radio } from "lucide-react";
import { FormEvent, useState } from "react";
import { useLocation } from "wouter";

import { api } from "../api";

export function Login() {
  const [, navigate] = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api.post<void>("/api/auth/login", { username, password }),
    onSuccess: () => navigate("/"),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate();
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true"><Radio size={23} strokeWidth={2.3} /></div>
        <p className="product-name">知流</p>
        <h1 id="login-title">登录你的情报台</h1>
        <form onSubmit={submit} className="login-form">
          <label>
            <span>用户名</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          </label>
          <label>
            <span>密码</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          </label>
          {login.isError && <p className="form-error" role="alert">{login.error.message}</p>}
          <button className="primary-button" type="submit" disabled={login.isPending}>
            <span>{login.isPending ? "正在登录" : "登录"}</span>
            <ArrowRight size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}
