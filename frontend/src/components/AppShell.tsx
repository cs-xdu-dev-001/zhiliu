import { ArrowLeft, BookOpenText, CircleCheck, House, Inbox, ListFilter, Radio, Search, Settings2, Tags } from "lucide-react";
import { Component, lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
import { Link, Route, Switch, useLocation, useSearchParams } from "wouter";
import { Home } from "../pages/Home";
import { BottomNav } from "./BottomNav";
import { ServiceStatus } from "./ServiceStatus";

async function loadRoute<T>(loader: () => Promise<T>) {
  try {
    return await loader();
  } catch {
    await new Promise<void>((resolve) => {
      const finish = () => {
        window.clearTimeout(timer);
        window.removeEventListener("online", finish);
        resolve();
      };
      const timer = window.setTimeout(finish, 500);
      window.addEventListener("online", finish, { once: true });
    });
    return loader();
  }
}

const Feed = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Feed"))).Feed }));
const BriefingDetail = lazy(async () => ({ default: (await loadRoute(() => import("../pages/BriefingDetail"))).BriefingDetail }));
const ItemDetail = lazy(async () => ({ default: (await loadRoute(() => import("../pages/ItemDetail"))).ItemDetail }));
const Reports = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Reports"))).Reports }));
const SearchPage = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Search"))).SearchPage }));
const Quality = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Quality"))).Quality }));
const Subscriptions = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Subscriptions"))).Subscriptions }));
const Tasks = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Tasks"))).Tasks }));
const TaskDetail = lazy(async () => ({ default: (await loadRoute(() => import("../pages/TaskDetail"))).TaskDetail }));
const TraceDetail = lazy(async () => ({ default: (await loadRoute(() => import("../pages/TraceDetail"))).TraceDetail }));
const Topics = lazy(async () => ({ default: (await loadRoute(() => import("../pages/Topics"))).Topics }));
const TopicDetailPage = lazy(async () => ({ default: (await loadRoute(() => import("../pages/TopicDetail"))).TopicDetailPage }));

class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <div className="inline-error" role="alert">页面资源加载失败。<button type="button" onClick={() => window.location.reload()}>重新加载页面</button></div>;
    }
    return this.props.children;
  }
}

const pageNames: Record<string, string> = {
  "/": "今日情报",
  "/feed": "情报流",
  "/reports": "报告",
  "/settings": "订阅与任务",
  "/tasks": "任务收件箱",
  "/search": "搜索知流",
  "/quality": "内容质量",
  "/topics": "主题信号",
};

const desktopNav = [
  { to: "/", label: "首页", icon: House, end: true },
  { to: "/feed", label: "情报", icon: ListFilter },
  { to: "/reports", label: "报告", icon: BookOpenText },
  { to: "/tasks", label: "收件箱", icon: Inbox },
  { to: "/topics", label: "主题", icon: Tags },
  { to: "/quality", label: "质量", icon: CircleCheck },
  { to: "/settings", label: "设置", icon: Settings2 },
];

function pageName(location: string) {
  if (location.startsWith("/items/")) return "情报详情";
  if (location.startsWith("/reports/")) return "报告详情";
  if (location.startsWith("/traces/")) return "处理链路";
  if (location.startsWith("/tasks/")) return "任务详情";
  if (location.startsWith("/topics/")) return "主题详情";
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
  const [searchParams] = useSearchParams();
  const pathname = location.split(/[?#]/, 1)[0];
  const settingsView = pathname === "/settings" ? searchParams.get("view") : null;
  const title = settingsView === "runtime" ? "Hermes与运行" : settingsView === "data" ? "数据导出" : pageName(pathname);
  const isDetailPage = pathname.startsWith("/items/") || pathname.startsWith("/reports/") || pathname.startsWith("/traces/") || pathname.startsWith("/tasks/") || pathname.startsWith("/topics/");
  const hidesBottomNav = isDetailPage;
  const backHref = isDetailPage ? detailBack(pathname) : null;
  const previousTitle = useRef(title);

  useEffect(() => {
    document.title = `${title} · 知流`;
    if (previousTitle.current !== title) {
      window.requestAnimationFrame(() => document.getElementById("main-content")?.focus());
      previousTitle.current = title;
    }
  }, [title]);

  return (
    <div className={`app-layout ${hidesBottomNav ? "detail-layout" : ""}`}>
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <aside className="sidebar">
        <Link className="sidebar-brand" href="/" aria-label="知流首页"><Radio size={20} /><strong>知流</strong></Link>
        <nav aria-label="桌面导航">
          {desktopNav.map(({ to, label, icon: Icon, end }) => (
            <Link key={to} href={to} aria-current={(end ? pathname === to : pathname.startsWith(to)) ? "page" : undefined} className={(end ? pathname === to : pathname.startsWith(to)) ? "active" : ""}>
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
        <main id="main-content" tabIndex={-1} className="page-content">
          <RouteErrorBoundary key={pathname}>
            <Suspense fallback={<div className="detail-skeleton route-skeleton" role="status" aria-label="正在加载页面" />}>
              <Switch>
                <Route path="/items/:id" component={ItemDetail} />
                <Route path="/reports/:id" component={BriefingDetail} />
                <Route path="/traces/:id" component={TraceDetail} />
                <Route path="/tasks/:id" component={TaskDetail} />
                <Route path="/topics/:id" component={TopicDetailPage} />
                <Route path="/feed" component={Feed} />
                <Route path="/reports" component={Reports} />
                <Route path="/topics" component={Topics} />
                <Route path="/search" component={SearchPage} />
                <Route path="/quality" component={Quality} />
                <Route path="/settings" component={Subscriptions} />
                <Route path="/tasks" component={Tasks} />
                <Route path="/" component={Home} />
                <Route component={Home} />
              </Switch>
            </Suspense>
          </RouteErrorBoundary>
        </main>
      </div>
      {!hidesBottomNav && <BottomNav />}
    </div>
  );
}
