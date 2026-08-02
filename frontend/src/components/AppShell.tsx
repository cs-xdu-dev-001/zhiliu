import { BookOpenText, House, ListFilter, Radio, Settings2 } from "lucide-react";
import { Link, Route, Switch, useLocation } from "wouter";
import { Feed } from "../pages/Feed";
import { BriefingDetail } from "../pages/BriefingDetail";
import { Home } from "../pages/Home";
import { ItemDetail } from "../pages/ItemDetail";
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

function pageName(location: string) {
  if (location.startsWith("/items/")) return "情报详情";
  if (location.startsWith("/reports/")) return "报告详情";
  return pageNames[location] ?? "今日情报";
}

export function AppShell() {
  const [location] = useLocation();

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
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="mobile-brand"><Radio size={18} /><span>知流</span></div>
          <h1>{pageName(location)}</h1>
        </header>
        <main className="page-content"><Switch><Route path="/items/:id" component={ItemDetail} /><Route path="/reports/:id" component={BriefingDetail} /><Route path="/feed" component={Feed} /><Route path="/reports" component={Reports} /><Route path="/settings" component={Subscriptions} /><Route path="/tasks" component={Tasks} /><Route path="/" component={Home} /><Route component={Home} /></Switch></main>
      </div>
      <BottomNav />
    </div>
  );
}
