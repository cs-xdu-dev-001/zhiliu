import { ArrowLeft, BookOpenText, CircleCheck, House, ListFilter, Radio, Search, Settings2 } from "lucide-react";
import { useEffect } from "react";
import { Link, Route, Switch, useLocation } from "wouter";
import { Feed } from "../pages/Feed";
import { BriefingDetail } from "../pages/BriefingDetail";
import { Home } from "../pages/Home";
import { ItemDetail } from "../pages/ItemDetail";
import { Reports } from "../pages/Reports";
import { SearchPage } from "../pages/Search";
import { Quality } from "../pages/Quality";
import { Subscriptions } from "../pages/Subscriptions";
import { Tasks } from "../pages/Tasks";
import { TaskDetail } from "../pages/TaskDetail";
import { TraceDetail } from "../pages/TraceDetail";
import { BottomNav } from "./BottomNav";
import { ServiceStatus } from "./ServiceStatus";

const pageNames: Record<string, string> = {
  "/": "今日情报",
  "/feed": "情报流",
  "/reports": "定期报告",
  "/settings": "订阅与任务",
  "/tasks": "任务记录",
  "/search": "搜索知流",
  "/quality": "内容质量",
};

const desktopNav = [
  { to: "/", label: "首页", icon: House, end: true },
  { to: "/feed", label: "情报", icon: ListFilter },
  { to: "/reports", label: "报告", icon: BookOpenText },
  { to: "/quality", label: "质量", icon: CircleCheck },
  { to: "/settings", label: "设置", icon: Settings2 },
];

function pageName(location: string) {
  if (location.startsWith("/items/")) return "情报详情";
  if (location.startsWith("/reports/")) return "报告详情";
  if (location.startsWith("/traces/")) return "处理链路";
  if (location.startsWith("/tasks/")) return "任务详情";
  return pageNames[location] ?? "今日情报";
}

function detailBack(location: string) {
  const fallback = location.startsWith("/reports/") ? "/reports"
    : location.startsWith("/tasks/") ? "/tasks"
      : "/feed";
  const value = new URLSearchParams(window.location.search).get("from");
  if (!value?.startsWith("/")) return fallback;
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin
      ? `${target.pathname}${target.search}${target.hash}`
      : fallback;
  } catch {
    return fallback;
  }
}

export function AppShell() {
  const [location] = useLocation();
  const pathname = location.split(/[?#]/, 1)[0];
  const title = pageName(pathname);
  const isDetailPage = pathname.startsWith("/items/") || pathname.startsWith("/reports/") || pathname.startsWith("/traces/") || pathname.startsWith("/tasks/");
  const hidesBottomNav = isDetailPage || pathname === "/tasks";
  const backHref = isDetailPage ? detailBack(pathname) : null;

  useEffect(() => {
    document.title = `${title} · 知流`;
  }, [title]);

  return (
    <div className={`app-layout ${hidesBottomNav ? "detail-layout" : ""}`}>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <div className="sidebar-brand"><Radio size={20} /><strong>知流</strong></div>
        <nav aria-label="桌面导航">
          {desktopNav.map(({ to, label, icon: Icon, end }) => (
            <Link key={to} href={to} aria-current={(end ? pathname === to : pathname.startsWith(to)) || (to === "/settings" && pathname.startsWith("/tasks")) ? "page" : undefined} className={(end ? pathname === to : pathname.startsWith(to)) || (to === "/settings" && pathname.startsWith("/tasks")) ? "active" : ""}>
              <Icon size={18} /><span>{label}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <div className="main-column">
        <header className="topbar">
          {backHref
            ? <Link className="topbar-back" href={backHref} aria-label="返回上一列表"><ArrowLeft size={19} /><span>返回</span></Link>
            : <div className="mobile-brand"><Radio size={18} /><span>知流</span></div>}
          <h1>{title}</h1>
          {!isDetailPage && <Link className="topbar-search" href="/search" aria-label="搜索知流" aria-current={pathname === "/search" ? "page" : undefined}><Search size={19} /></Link>}
        </header>
        <ServiceStatus />
        <main id="main-content" tabIndex={-1} className="page-content"><Switch><Route path="/items/:id" component={ItemDetail} /><Route path="/reports/:id" component={BriefingDetail} /><Route path="/traces/:id" component={TraceDetail} /><Route path="/tasks/:id" component={TaskDetail} /><Route path="/feed" component={Feed} /><Route path="/reports" component={Reports} /><Route path="/search" component={SearchPage} /><Route path="/quality" component={Quality} /><Route path="/settings" component={Subscriptions} /><Route path="/tasks" component={Tasks} /><Route path="/" component={Home} /><Route component={Home} /></Switch></main>
      </div>
      {!hidesBottomNav && <BottomNav />}
    </div>
  );
}
