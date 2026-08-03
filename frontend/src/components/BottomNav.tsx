import { BookOpenText, House, ListFilter, Settings2 } from "lucide-react";
import { Link, useLocation } from "wouter";

const entries = [
  { to: "/", label: "首页", icon: House, end: true },
  { to: "/feed", label: "情报", icon: ListFilter },
  { to: "/reports", label: "报告", icon: BookOpenText },
  { to: "/settings", label: "设置", icon: Settings2 },
];

export function BottomNav() {
  const [location] = useLocation();
  return (
    <nav className="bottom-nav" aria-label="主导航">
      {entries.map(({ to, label, icon: Icon, end }) => (
        <Link key={to} href={to} aria-current={(end ? location === to : location.startsWith(to)) ? "page" : undefined} className={(end ? location === to : location.startsWith(to)) ? "active" : ""}>
          <Icon size={20} />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}
