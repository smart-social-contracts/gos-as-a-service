from ic_python_db import Entity, Float, Integer, String, TimestampedMixin, Boolean


class UserCredits(Entity, TimestampedMixin):
    __alias__ = "principal_id"
    principal_id = String()
    balance = Integer()
    total_purchased = Integer()
    total_spent = Integer()

    def to_dict(self) -> dict:
        return {
            "principal_id": self.principal_id,
            "balance": self.balance or 0,
            "total_purchased": self.total_purchased or 0,
            "total_spent": self.total_spent or 0,
        }


class CreditTransaction(Entity, TimestampedMixin):
    __alias__ = "id"
    id = String()
    principal_id = String()
    amount = Integer()
    transaction_type = String()
    description = String()
    stripe_session_id = String()
    timestamp = Float()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "principal_id": self.principal_id,
            "amount": self.amount or 0,
            "transaction_type": self.transaction_type or "",
            "description": self.description or "",
            "stripe_session_id": self.stripe_session_id or "",
            "timestamp": self.timestamp or 0,
        }


class DeploymentCreditHold(Entity, TimestampedMixin):
    __alias__ = "job_id"
    job_id = String()
    principal_id = String()
    amount = Integer()
    status = String()
    reason = String()
    created_at = Float()
    settled_at = Float()

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "principal_id": self.principal_id,
            "amount": self.amount or 0,
            "status": self.status or "",
            "reason": self.reason or "",
            "created_at": self.created_at or 0.0,
            "settled_at": self.settled_at or 0.0,
        }


class RealmRecord(Entity, TimestampedMixin):
    __alias__ = "id"
    id = String()
    name = String()
    url = String(max_length=512)
    backend_url = String(max_length=512)
    logo = String(max_length=512)
    users_count = Integer()
    created_at = Float()
    frontend_canister_id = String(max_length=64)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name or "",
            "url": self.url or "",
            "backend_url": self.backend_url or "",
            "logo": self.logo or "",
            "users_count": self.users_count or 0,
            "created_at": self.created_at or 0.0,
            "frontend_canister_id": self.frontend_canister_id or "",
        }


class SlugRecord(Entity, TimestampedMixin):
    """Federation slug → realm mapping (portal routing authority)."""
    __alias__ = "slug"
    slug = String(max_length=64)
    realm_id = String(max_length=64)
    frontend_canister_id = String(max_length=64)
    claimed_by = String(max_length=64)
    claimed_at = Float()
    portal_url = String(max_length=512)
    pretty_hostname = String(max_length=256)
    pretty_hostname_status = String(max_length=16)
    gos_implementation = String(max_length=64)
    gos_version = String(max_length=32)
    ggg_conformance = String(max_length=32)
    loader_profile = String(max_length=64)
    created_at = Float()
    updated_at = Float()

    def to_dict(self) -> dict:
        return {
            "slug": self.slug or "",
            "realm_id": self.realm_id or "",
            "frontend_canister_id": self.frontend_canister_id or "",
            "claimed_by": self.claimed_by or "",
            "claimed_at": self.claimed_at or 0.0,
            "portal_url": self.portal_url or "",
            "pretty_hostname": self.pretty_hostname or "",
            "pretty_hostname_status": self.pretty_hostname_status or "",
            "gos_implementation": self.gos_implementation or "",
            "gos_version": self.gos_version or "",
            "ggg_conformance": self.ggg_conformance or "",
            "loader_profile": self.loader_profile or "",
            "created_at": self.created_at or 0.0,
            "updated_at": self.updated_at or 0.0,
        }


class InvitationCode(Entity, TimestampedMixin):
    __alias__ = "code_hash"
    code_hash = String(max_length=64)
    redeemed_by = String(max_length=64)
    is_active = Boolean(default=True)
    redeemed_at = Float()
    created_at = Float()

    def to_dict(self) -> dict:
        return {
            "code_hash": self.code_hash or "",
            "redeemed_by": self.redeemed_by or "",
            "is_active": bool(self.is_active),
            "redeemed_at": self.redeemed_at or 0.0,
            "created_at": self.created_at or 0.0,
        }


class ActivatedPrincipal(Entity, TimestampedMixin):
    __alias__ = "principal_id"
    principal_id = String(max_length=64)
    invitation_code_hash = String(max_length=64)
    activated_at = Float()

    def to_dict(self) -> dict:
        return {
            "principal_id": self.principal_id or "",
            "invitation_code_hash": self.invitation_code_hash or "",
            "activated_at": self.activated_at or 0.0,
        }


class RegistryConfig(Entity):
    __alias__ = "key"
    key = String(max_length=64)
    value = String(max_length=256)


class WizardDraft(Entity, TimestampedMixin):
    """Persisted create-realm wizard state so users can leave and resume."""
    __alias__ = "id"
    id = String(max_length=64)
    principal_id = String(max_length=64)
    realm_name = String(max_length=128)
    draft_json = String(max_length=8192)
    current_step = Integer(default=0)
    deploy_version = String(max_length=32)
    updated_at = Float(default=0.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id or "",
            "principal_id": self.principal_id or "",
            "realm_name": self.realm_name or "",
            "draft_json": self.draft_json or "{}",
            "current_step": self.current_step or 0,
            "deploy_version": self.deploy_version or "",
            "updated_at": self.updated_at or 0.0,
        }


class VersionInfo(Entity, TimestampedMixin):
    """Tracks available realm versions for self-upgrade."""
    __alias__ = "id"
    id = String(max_length=32)
    version = String(max_length=32)
    backend_wasm_url = String(max_length=512)
    frontend_tar_url = String(max_length=512)
    backend_wasm_hash = String(max_length=128)
    frontend_tar_hash = String(max_length=128)
    is_latest = Boolean(default=False)
    published_at = Float()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version or "",
            "backend_wasm_url": self.backend_wasm_url or "",
            "frontend_tar_url": self.frontend_tar_url or "",
            "backend_wasm_hash": self.backend_wasm_hash or "",
            "frontend_tar_hash": self.frontend_tar_hash or "",
            "is_latest": bool(self.is_latest),
            "published_at": self.published_at or 0.0,
        }
