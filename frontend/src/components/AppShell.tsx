import { useQuery } from "@tanstack/react-query";
import { BookOpenText, House, ListFilter, LogOut, Radio, Settings2 } from "lucide-react";
import { Link, Redirect, Route, Switch, useLocation } from "wouter";

import { api, ApiError } from "../api";
import type { User } from "../types";
import { Feed } from "../pages/Feed";
import { Home } from "../pages/Home";
import { Reports } from "../pages/Reports";
import { Subscriptions } from "../pages/Subscriptions";
import { Tasks } from "../pages/Tasks";
import { BottomNav } from "./BottomNav";

const pageNames: Record<string, string> = {
  "/": "今日情报",
  "/feed": "情报流",
  "/reports": "定期报告",
  "/settings": "订阅与任务",
  "/tasks": "任务记录",
};

const desktopNav = [
  { to: "/", label: "首页", icon: House, end: true },
  { to: "/feed", label: "情报", icon: ListFilter },
  { to: "/reports", label: "报告", icon: BookOpenText },
  { to: "/settings", label: "设置", icon: Settings2 },
];

export function AppShell() {
  const [location, navigate] = useLocation();
  const user = useQuery({ queryKey: ["me"], queryFn: () => api.get<User>("/api/auth/me"), retry: false });

  if (user.isPending) return <div className="app-loader">正在进入知流...</div>;
  if (user.error instanceof ApiError && user.error.status === 401) return <Redirect to="/login" replace />;
  if (user.isError) return <div className="app-loader error-text">无法连接知流服务</div>;

  async function logout() {
    await api.post<void>("/api/auth/logout");
    navigate("/login");
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand"><Radio size={20} /><strong>知流</strong></div>
        <nav aria-label="桌面导航">
          {desktopNav.map(({ to, label, icon: Icon, end }) => (
            <Link key={to} href={to} className={(end ? location === to : location.startsWith(to)) ? "active" : ""}>
              <Icon size={18} /><span>{label}</span>
            </Link>
          ))}
        </nav>
        <button className="sidebar-logout" onClick={logout} title="退出登录"><LogOut size={18} /><span>退出</span></button>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="mobile-brand"><Radio size={18} /><span>知流</span></div>
          <h1>{pageNames[location] ?? "知流"}</h1>
          <span className="user-chip">{user.data.username}</span>
        </header>
        <main className="page-content"><Switch><Route path="/feed" component={Feed} /><Route path="/reports" component={Reports} /><Route path="/settings" component={Subscriptions} /><Route path="/tasks" component={Tasks} /><Route path="/" component={Home} /></Switch></main>
      </div>
      <BottomNav />
    </div>
  );
}
