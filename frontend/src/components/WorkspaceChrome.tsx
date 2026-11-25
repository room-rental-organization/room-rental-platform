import type { ReactNode } from "react";
import type { UserProfile } from "../api";
import AppLink from "./AppLink";
import "./WorkspaceChrome.css";

export type WorkspaceRole = "landlord" | "tenant" | "admin";
type NavigationProps = {
  profile: UserProfile;
  onNavigate: (path: string) => void;
  onSignOut: () => void;
};
type WorkspaceLink = { path: string; label: string; view?: string };
export const workspaceLinks: Record<WorkspaceRole, WorkspaceLink[]> = {
  landlord: [
    { path: "/landlord", label: "Dashboard", view: "overview" },
    { path: "/landlord?view=listings", label: "Listings", view: "listings" },
    { path: "/landlord?view=enquiries", label: "Enquiries", view: "enquiries" },
    { path: "/landlord/leads", label: "Lead management" },
    { path: "/conversations", label: "Messages" },
    {
      path: "/landlord?view=future",
      label: "Future interests",
      view: "future",
    },
    { path: "/landlord/verification", label: "Trust & verification" },
    { path: "/landlord/reports", label: "Reports" },
  ],
  tenant: [
    { path: "/tenant", label: "Dashboard" },
    { path: "/tenant/leads", label: "Enquiry progress" },
    { path: "/conversations", label: "Messages" },
    { path: "/tenant/reports", label: "Reports" },
  ],
  admin: [
    { path: "/admin", label: "Listings" },
    { path: "/admin/verification", label: "Verification review" },
    { path: "/admin/leads", label: "Lead management" },
    { path: "/admin/disputes", label: "Lead disputes" },
    { path: "/admin/reports", label: "Reports" },
  ],
};

export function WorkspaceSidebar({
  role,
  currentPath,
  activeView,
  onDashboardView,
  profile,
  onNavigate,
  onSignOut,
}: NavigationProps & {
  role: "landlord" | "admin";
  currentPath: string;
  activeView?: string;
  onDashboardView?: (view: string) => void;
}) {
  const admin = role === "admin";
  return (
    <aside
      className={`${admin ? "admin-sidebar" : "landlord-sidebar"} workspace-sidepanel`}
      aria-label={`${role} workspace navigation`}
    >
      <AppLink
        className="workspace-brand"
        href={`/${role}`}
        onNavigate={onNavigate}
      >
        <span aria-hidden="true">R</span>
        <span>
          <strong>Room Rentals</strong>
          <small>{role} workspace</small>
        </span>
      </AppLink>
      <p className="workspace-nav-caption">Workspace</p>
      <nav
        className={admin ? "admin-sidebar-nav" : "landlord-sidebar-nav"}
        aria-label={`${role} navigation`}
      >
        {workspaceLinks[role].map((link) => {
          const active =
            onDashboardView && link.view
              ? activeView === link.view
              : currentPath === link.path;
          const props = {
            className: `workspace-nav-item${active ? " active" : ""}`,
            "aria-current": active ? ("page" as const) : undefined,
          };
          return onDashboardView && link.view ? (
            <button
              {...props}
              key={link.path}
              type="button"
              onClick={() => onDashboardView(link.view!)}
            >
              {link.label}
            </button>
          ) : (
            <AppLink
              {...props}
              key={link.path}
              href={link.path}
              onNavigate={onNavigate}
            >
              {link.label}
            </AppLink>
          );
        })}
        <AppLink
          className="workspace-nav-item"
          href="/"
          onNavigate={onNavigate}
        >
          Browse rooms
        </AppLink>
      </nav>
      <div className="workspace-account">
        <strong>{profile.full_name}</strong>
        <span>{profile.email}</span>
        <span className="rental-status">{role}</span>
        <button className="secondary-button" type="button" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </aside>
  );
}

export function TenantWorkspaceHeader({
  profile,
  onNavigate,
  onSignOut,
  currentPath,
}: NavigationProps & { currentPath: string }) {
  return (
    <header className="tenant-topbar workspace-tenant-header">
      <AppLink className="tenant-brand" href="/tenant" onNavigate={onNavigate}>
        <span aria-hidden="true" className="tenant-brand-mark">
          R
        </span>
        <span>Room Rentals</span>
      </AppLink>
      <nav aria-label="tenant navigation" className="tenant-nav">
        {workspaceLinks.tenant.map((link) => (
          <AppLink
            key={link.path}
            className="tenant-nav-link"
            href={link.path}
            onNavigate={onNavigate}
            aria-current={currentPath === link.path ? "page" : undefined}
          >
            {link.label}
          </AppLink>
        ))}
        <AppLink className="tenant-nav-link" href="/" onNavigate={onNavigate}>
          Browse rooms
        </AppLink>
        <button className="tenant-signout" type="button" onClick={onSignOut}>
          Sign out
        </button>
      </nav>
      <span className="workspace-current-account">
        {profile.full_name} · Tenant
      </span>
    </header>
  );
}

export function WorkspaceShell({
  role,
  currentPath,
  title,
  children,
  ...navigation
}: NavigationProps & {
  role: WorkspaceRole;
  currentPath: string;
  title: string;
  children: ReactNode;
}) {
  const content = (
    <>
      <header className="role-workspace-header">
        <p className="eyebrow">{role} workspace</p>
        <h1>{title}</h1>
        <p>{navigation.profile.full_name}</p>
      </header>
      {children}
    </>
  );
  if (role === "tenant")
    return (
      <main className="page-shell tenant-page role-workspace-page">
        <div className="tenant-dashboard">
          <TenantWorkspaceHeader {...navigation} currentPath={currentPath} />
          {content}
        </div>
      </main>
    );
  return (
    <main
      className={`${role === "admin" ? "admin-dashboard" : "page-shell landlord-page"} role-workspace-page`}
    >
      <WorkspaceSidebar {...navigation} role={role} currentPath={currentPath} />
      <div
        className={`${role === "admin" ? "admin-dashboard-main" : "landlord-dashboard"} role-workspace-content`}
      >
        {content}
      </div>
    </main>
  );
}
