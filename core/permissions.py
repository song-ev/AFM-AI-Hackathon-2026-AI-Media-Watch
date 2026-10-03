"""
Reusable DRF permission classes keyed on the user's role.

Roles (see accounts.User.Role):
    analyst      — internal: queue, cards, graphs, connections, decisions.
    afm_lead     — internal: everything an analyst can do + leadership
                   dashboards and dictionary review.
    system_admin — internal: full access, including user management.
    bank_admin   — external: only ever touches bankapi.

The `*OrAbove` classes implement an inclusive hierarchy
(analyst ⊂ afm_lead ⊂ system_admin); a Django superuser always passes the
internal checks. bank_admin is deliberately disjoint from the internal roles.
"""
from rest_framework.permissions import BasePermission

from accounts.models import User

Role = User.Role

# Every internal (non-bank) role, in ascending order of privilege.
INTERNAL_ROLES = (Role.ANALYST, Role.AFM_LEAD, Role.SYSTEM_ADMIN)


class _RolePermission(BasePermission):
    """Allow authenticated users whose role is in `allowed_roles`.

    A superuser always passes (unless the class opts out via
    `superuser_bypass = False`, used by the bank-only check).
    """

    allowed_roles: tuple = ()
    superuser_bypass: bool = True

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if self.superuser_bypass and user.is_superuser:
            return True
        return getattr(user, "role", None) in self.allowed_roles


class IsAnalystOrAbove(_RolePermission):
    """Any internal role (analyst, afm_lead, system_admin)."""

    allowed_roles = INTERNAL_ROLES


class IsAfmLeadOrAbove(_RolePermission):
    """Leadership features (trends, dictionary review).

    Admits every internal role: in this product analysts have full internal
    access, and afm_lead/system_admin are supersets. Tighten to
    (afm_lead, system_admin) here if lead-only gating is later required.
    """

    allowed_roles = INTERNAL_ROLES


class IsSystemAdmin(_RolePermission):
    """Administrative actions — system_admin (or Django superuser)."""

    allowed_roles = (Role.SYSTEM_ADMIN,)


class IsBankAdmin(_RolePermission):
    """bank_admin only — external bank integrations. No superuser bypass."""

    allowed_roles = (Role.BANK_ADMIN,)
    superuser_bypass = False
