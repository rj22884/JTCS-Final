import type { ReactNode } from "react";

type LayoutProps = {
  children: ReactNode;
};

const navItems = ["Dashboard", "Settings"];

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="badge">JTCS</span>
          <strong>Final</strong>
        </div>
        <nav>
          {navItems.map((item) => (
            <a key={item} href="#" className={item === "Dashboard" ? "active" : ""}>
              {item}
            </a>
          ))}
        </nav>
      </aside>

      <div className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Workspace</p>
            <h1>Dashboard</h1>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
