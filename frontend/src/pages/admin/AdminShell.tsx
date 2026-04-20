/**
 * AdminShell — navigation wrapper for all admin pages.
 *
 * Tabs: Users | Config & Hub Pairs
 *
 * Access: admin role only.  Non-admins see a 403-style message.
 */

import { NavLink, Outlet } from "react-router-dom";
import type React from "react";
import { tokens } from "@/theme/tokens";
import { useCurrentUser } from "@/hooks/useAuth";

const shellStyle: React.CSSProperties = {
  minHeight: "100vh",
  background: tokens.colors.lightGrey,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.black,
};

const headerStyle: React.CSSProperties = {
  background: tokens.colors.navy,
  padding: `0 ${tokens.spacing.xl}px`,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  height: 68,
};

const titleStyle: React.CSSProperties = {
  color: tokens.colors.white,
  fontSize: tokens.typography.heading.h4.size,
  fontWeight: tokens.typography.heading.h4.weight,
  fontFamily: tokens.typography.fontFamily,
  margin: 0,
};

const navStyle: React.CSSProperties = {
  display: "flex",
  gap: tokens.spacing.xl,
  padding: `0 ${tokens.spacing.xl}px`,
  background: tokens.colors.white,
  borderBottom: `1px solid ${tokens.colors.lightGrey}`,
};

const navLinkBase: React.CSSProperties = {
  display: "inline-block",
  padding: `${tokens.spacing.md}px 0`,
  fontSize: 14,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.black,
  textDecoration: "none",
  borderBottom: "3px solid transparent",
};

const mainStyle: React.CSSProperties = {
  maxWidth: 1200,
  margin: "0 auto",
  padding: `${tokens.spacing.xl}px ${tokens.spacing.lg}px`,
};

const backLinkStyle: React.CSSProperties = {
  color: tokens.colors.white,
  fontSize: 13,
  fontFamily: tokens.typography.fontFamily,
  textDecoration: "none",
};

export function AdminShell() {
  const { data: me, isLoading } = useCurrentUser();

  if (isLoading) return <p style={{ padding: tokens.spacing.lg }}>Loading…</p>;

  if (me?.role !== "admin") {
    return (
      <div style={{ padding: tokens.spacing.xl, fontFamily: tokens.typography.fontFamily }}>
        <p style={{ color: tokens.colors.black }}>You need admin access to view this page.</p>
      </div>
    );
  }

  return (
    <div style={shellStyle}>
      <header style={headerStyle}>
        <div>
          <h1 style={titleStyle}>Admin</h1>
        </div>
        <a href="/" style={backLinkStyle}>
          ← Back to report
        </a>
      </header>

      <nav style={navStyle} aria-label="Admin navigation">
        <NavLink
          to="/admin/users"
          style={({ isActive }) => ({
            ...navLinkBase,
            color: isActive ? tokens.colors.primary : tokens.colors.black,
            borderBottomColor: isActive ? tokens.colors.primary : "transparent",
          })}
        >
          Users
        </NavLink>
        <NavLink
          to="/admin/config"
          style={({ isActive }) => ({
            ...navLinkBase,
            color: isActive ? tokens.colors.primary : tokens.colors.black,
            borderBottomColor: isActive ? tokens.colors.primary : "transparent",
          })}
        >
          Config &amp; hub pairs
        </NavLink>
      </nav>

      <main style={mainStyle}>
        <Outlet />
      </main>
    </div>
  );
}
