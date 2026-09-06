"""Organization limits restrict personal consent; they never supply credentials."""

from fastapi import HTTPException

from .models import OrganizationPolicy

DEFAULT_CAPABILITIES = ("mail", "calendar", "files", "files_write")
CAPABILITIES = (*DEFAULT_CAPABILITIES, "mail_send")


def allowed_capabilities(db, organization_id):
    policy = db.get(OrganizationPolicy, organization_id, populate_existing=True)
    permitted = DEFAULT_CAPABILITIES if policy is None else policy.allowed_capabilities
    return [item for item in CAPABILITIES if item in permitted]


def require_allowed(db, organization_id, capabilities):
    if not set(capabilities) <= set(allowed_capabilities(db, organization_id)):
        raise HTTPException(403, "company_policy_denied")


def policy_view(db, organization_id):
    policy = db.get(OrganizationPolicy, organization_id, populate_existing=True)
    return {
        "allowed_capabilities": allowed_capabilities(db, organization_id),
        "version": policy.version if policy else 0,
        "updated_by": policy.updated_by if policy else None,
        "updated_at": policy.updated_at if policy else None,
    }
