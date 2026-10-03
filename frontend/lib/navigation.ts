import type { Role } from "@/lib/stores/authStore";

export interface NavItem {
  label: string;
  href: string;
  roles: Role[];
}

// Dashboard menu. bank_admin is intentionally absent — banks use the REST API
// (C6) and do not get the internal dashboard (see app/(bank)). All internal
// sections belong to the single `analyst` role.
export const DASHBOARD_NAV: NavItem[] = [
  { label: "Очередь", href: "/queue", roles: ["analyst"] },
  { label: "Анализ", href: "/analyze", roles: ["analyst"] },
  { label: "Связи", href: "/connections", roles: ["analyst"] },
  { label: "Тренды", href: "/trends", roles: ["analyst"] },
];

export function navItemsForRole(role: Role | undefined): NavItem[] {
  if (!role) return [];
  return DASHBOARD_NAV.filter((item) => item.roles.includes(role));
}

// Roles allowed to view a dashboard path. analyst is the only internal role.
export function requiredRolesForPath(_pathname: string): Role[] {
  return ["analyst"];
}

// Where to send a user after login, based on role.
export function landingPathForRole(role: Role): string {
  if (role === "bank_admin") return "/bank";
  return "/queue";
}
