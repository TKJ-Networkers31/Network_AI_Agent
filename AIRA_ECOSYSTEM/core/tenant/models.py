"""
AIRA OS — Multi-Tenant Core, Identity & Customer Inventory Domain Models (Networking VIII).

Defines the authoritative data models for:
- WP 8.1: Multi-Tenant Core (Tenant, Subscription, Resource Quota, Configuration)
- WP 8.2: Identity, RBAC & Access Governance (Users, Roles, Permissions, Sessions)
- WP 8.3: Customer Network Inventory (Sites, Groups, Scoped Devices with RFC 1918 overlap safety)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from typing import Any, Dict, List, Optional, Set
import uuid


# ===========================================================================
# 1. ENUMS
# ===========================================================================

class TenantStatus(str, Enum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    MAINTENANCE = "MAINTENANCE"
    DECOMMISSIONED = "DECOMMISSIONED"


class SubscriptionTier(str, Enum):
    COMMUNITY = "COMMUNITY"
    STANDARD = "STANDARD"
    ENTERPRISE = "ENTERPRISE"
    CUSTOM = "CUSTOM"


class UserRoleType(str, Enum):
    # Phase F Primary Role Hierarchy
    PLATFORM_OWNER = "PLATFORM_OWNER"
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"

    # Backward-Compatible Platform Roles
    PLATFORM_SUPER_ADMIN = "PLATFORM_SUPER_ADMIN"
    NOC_ADMIN = "NOC_ADMIN"
    NOC_OPERATOR = "NOC_OPERATOR"
    NETWORK_ENGINEER = "NETWORK_ENGINEER"
    NOC_ANALYST = "NOC_ANALYST"
    SUPPORT_OPERATOR = "SUPPORT_OPERATOR"
    AUDITOR = "AUDITOR"

    # Customer Organization Roles
    CUSTOMER_OWNER = "CUSTOMER_OWNER"
    CUSTOMER_ADMIN = "CUSTOMER_ADMIN"
    CUSTOMER_OPERATOR = "CUSTOMER_OPERATOR"
    CUSTOMER_TECHNICIAN = "CUSTOMER_TECHNICIAN"
    CUSTOMER_VIEWER = "CUSTOMER_VIEWER"


class Permission(str, Enum):
    # Granular Administrative & Platform Permissions
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    SUBSCRIPTIONS_MANAGE = "subscriptions.manage"
    ENTITLEMENTS_MANAGE = "entitlements.manage"
    BILLING_READ = "billing.read"
    BILLING_MANAGE = "billing.manage"
    INFRASTRUCTURE_READ = "infrastructure.read"
    INFRASTRUCTURE_MANAGE = "infrastructure.manage"
    SECURITY_MANAGE = "security.manage"
    PLATFORM_SETTINGS_MANAGE = "platform.settings.manage"

    # Network++ Entitlement Permissions
    NETWORK_READ = "network.read"
    NETWORK_WRITE = "network.write"
    NETWORK_OPERATE = "network.operate"

    # Personalization Permissions
    PERSONALIZATION_MANAGE = "personalization.manage"

    # Operational & Tenant Permissions
    TENANT_READ = "tenant.read"
    TENANT_MANAGE = "tenant.manage"
    SITE_READ = "site.read"
    SITE_MANAGE = "site.manage"
    DEVICE_READ = "device.read"
    DEVICE_MANAGE = "device.manage"
    EVIDENCE_READ = "evidence.read"
    INCIDENT_READ = "incident.read"
    INCIDENT_ACKNOWLEDGE = "incident.acknowledge"
    INCIDENT_MANAGE = "incident.manage"
    MAINTENANCE_READ = "maintenance.read"
    MAINTENANCE_MANAGE = "maintenance.manage"
    REPORT_READ = "report.read"
    REPORT_EXPORT = "report.export"
    USER_MANAGE = "user.manage"
    GATEWAY_MANAGE = "gateway.manage"
    SLA_READ = "sla.read"
    SLA_MANAGE = "sla.manage"
    RECOMMENDATION_READ = "recommendation.read"
    RECOMMENDATION_APPROVE = "recommendation.approve"
    AUDIT_READ = "audit.read"
    SUPPORT_READ = "support.read"
    SUPPORT_CREATE = "support.create"
    SUPPORT_COMMENT = "support.comment"
    NOTIFICATION_MANAGE = "notification.manage"


# Default permission mappings
ROLE_PERMISSIONS: Dict[UserRoleType, Set[Permission]] = {
    UserRoleType.PLATFORM_OWNER: set(Permission),
    UserRoleType.SUPERADMIN: set(Permission),
    UserRoleType.PLATFORM_SUPER_ADMIN: set(Permission),
    UserRoleType.ADMIN: {
        Permission.USERS_READ, Permission.USERS_MANAGE, Permission.INFRASTRUCTURE_READ,
        Permission.INFRASTRUCTURE_MANAGE, Permission.SUBSCRIPTIONS_MANAGE, Permission.ENTITLEMENTS_MANAGE,
        Permission.BILLING_READ, Permission.REPORT_READ, Permission.AUDIT_READ,
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
    },
    UserRoleType.USER: {
        Permission.PERSONALIZATION_MANAGE, Permission.SUPPORT_CREATE, Permission.SUPPORT_READ,
    },
    UserRoleType.GUEST: set(),
    UserRoleType.NOC_ADMIN: set(Permission),
    UserRoleType.NOC_OPERATOR: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.SITE_MANAGE,
        Permission.DEVICE_READ, Permission.DEVICE_MANAGE, Permission.EVIDENCE_READ,
        Permission.INCIDENT_READ, Permission.INCIDENT_ACKNOWLEDGE, Permission.INCIDENT_MANAGE,
        Permission.MAINTENANCE_READ, Permission.MAINTENANCE_MANAGE, Permission.REPORT_READ,
        Permission.REPORT_EXPORT, Permission.GATEWAY_MANAGE, Permission.SLA_READ,
        Permission.RECOMMENDATION_READ, Permission.RECOMMENDATION_APPROVE, Permission.AUDIT_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
        Permission.NOTIFICATION_MANAGE,
    },
    UserRoleType.NETWORK_ENGINEER: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.DEVICE_MANAGE, Permission.EVIDENCE_READ, Permission.INCIDENT_READ,
        Permission.INCIDENT_ACKNOWLEDGE, Permission.MAINTENANCE_READ, Permission.MAINTENANCE_MANAGE,
        Permission.REPORT_READ, Permission.GATEWAY_MANAGE, Permission.RECOMMENDATION_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
    },
    UserRoleType.NOC_ANALYST: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.EVIDENCE_READ, Permission.INCIDENT_READ, Permission.REPORT_READ,
        Permission.REPORT_EXPORT, Permission.SLA_READ, Permission.RECOMMENDATION_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_COMMENT,
    },
    UserRoleType.SUPPORT_OPERATOR: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.INCIDENT_READ, Permission.INCIDENT_ACKNOWLEDGE, Permission.REPORT_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
    },
    UserRoleType.AUDITOR: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.EVIDENCE_READ, Permission.INCIDENT_READ, Permission.REPORT_READ,
        Permission.REPORT_EXPORT, Permission.SLA_READ, Permission.AUDIT_READ,
        Permission.SUPPORT_READ,
    },
    # Customer Roles
    UserRoleType.CUSTOMER_OWNER: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.SITE_MANAGE,
        Permission.DEVICE_READ, Permission.DEVICE_MANAGE, Permission.INCIDENT_READ,
        Permission.INCIDENT_ACKNOWLEDGE, Permission.MAINTENANCE_READ, Permission.MAINTENANCE_MANAGE,
        Permission.REPORT_READ, Permission.REPORT_EXPORT, Permission.USER_MANAGE,
        Permission.GATEWAY_MANAGE, Permission.SLA_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
        Permission.NOTIFICATION_MANAGE,
    },
    UserRoleType.CUSTOMER_ADMIN: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.SITE_MANAGE,
        Permission.DEVICE_READ, Permission.DEVICE_MANAGE, Permission.INCIDENT_READ,
        Permission.INCIDENT_ACKNOWLEDGE, Permission.MAINTENANCE_READ, Permission.MAINTENANCE_MANAGE,
        Permission.REPORT_READ, Permission.REPORT_EXPORT, Permission.USER_MANAGE,
        Permission.SLA_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
        Permission.NOTIFICATION_MANAGE,
    },
    UserRoleType.CUSTOMER_OPERATOR: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.INCIDENT_READ, Permission.INCIDENT_ACKNOWLEDGE, Permission.MAINTENANCE_READ,
        Permission.REPORT_READ, Permission.SLA_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
        Permission.NOTIFICATION_MANAGE,
    },
    UserRoleType.CUSTOMER_TECHNICIAN: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.INCIDENT_READ, Permission.REPORT_READ, Permission.SLA_READ,
        Permission.SUPPORT_READ, Permission.SUPPORT_CREATE, Permission.SUPPORT_COMMENT,
        Permission.NOTIFICATION_MANAGE,
    },
    UserRoleType.CUSTOMER_VIEWER: {
        Permission.TENANT_READ, Permission.SITE_READ, Permission.DEVICE_READ,
        Permission.INCIDENT_READ, Permission.REPORT_READ, Permission.SLA_READ,
        Permission.SUPPORT_READ,
    },
}


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class DeviceType(str, Enum):
    ROUTER = "ROUTER"
    SWITCH = "SWITCH"
    FIREWALL = "FIREWALL"
    ACCESS_POINT = "ACCESS_POINT"
    SERVER = "SERVER"
    OTHER = "OTHER"


# ===========================================================================
# 2. MULTI-TENANT CORE MODELS (WP 8.1)
# ===========================================================================

@dataclass
class TenantConfiguration:
    """Configurable tenant-level operations parameters."""
    default_timezone: str = "Asia/Jakarta"
    retention_days: int = 90
    auto_incident_creation: bool = True
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    alert_email: Optional[str] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_timezone": self.default_timezone,
            "retention_days": self.retention_days,
            "auto_incident_creation": self.auto_incident_creation,
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "alert_email": self.alert_email,
            "custom_metadata": dict(self.custom_metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TenantConfiguration:
        return cls(
            default_timezone=data.get("default_timezone", "Asia/Jakarta"),
            retention_days=int(data.get("retention_days", 90)),
            auto_incident_creation=bool(data.get("auto_incident_creation", True)),
            quiet_hours_enabled=bool(data.get("quiet_hours_enabled", True)),
            quiet_hours_start=data.get("quiet_hours_start", "22:00"),
            quiet_hours_end=data.get("quiet_hours_end", "07:00"),
            alert_email=data.get("alert_email"),
            custom_metadata=dict(data.get("custom_metadata", {})),
        )


@dataclass
class TenantSubscription:
    """Subscription tier and resource boundaries for a tenant."""
    subscription_id: str
    tenant_id: str
    tier: str = SubscriptionTier.STANDARD.value
    max_sites: int = 10
    max_devices: int = 100
    max_gateways: int = 10
    is_active: bool = True
    valid_until_utc: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "tenant_id": self.tenant_id,
            "tier": self.tier,
            "max_sites": self.max_sites,
            "max_devices": self.max_devices,
            "max_gateways": self.max_gateways,
            "is_active": self.is_active,
            "valid_until_utc": self.valid_until_utc,
            "created_at": self.created_at,
        }


@dataclass
class TenantResourceQuota:
    """Current usage versus allocated quotas for a tenant."""
    tenant_id: str
    current_sites: int = 0
    current_devices: int = 0
    current_gateways: int = 0
    max_sites: int = 10
    max_devices: int = 100
    max_gateways: int = 10

    @property
    def is_site_quota_exceeded(self) -> bool:
        return self.current_sites >= self.max_sites

    @property
    def is_device_quota_exceeded(self) -> bool:
        return self.current_devices >= self.max_devices

    @property
    def is_gateway_quota_exceeded(self) -> bool:
        return self.current_gateways >= self.max_gateways

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "current_sites": self.current_sites,
            "current_devices": self.current_devices,
            "current_gateways": self.current_gateways,
            "max_sites": self.max_sites,
            "max_devices": self.max_devices,
            "max_gateways": self.max_gateways,
            "site_available": max(0, self.max_sites - self.current_sites),
            "device_available": max(0, self.max_devices - self.current_devices),
            "gateway_available": max(0, self.max_gateways - self.current_gateways),
        }


@dataclass
class Tenant:
    """Canonical Tenant entity representing a customer organization."""
    tenant_id: str
    name: str
    slug: str
    status: str = TenantStatus.ACTIVE.value
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    configuration: TenantConfiguration = field(default_factory=TenantConfiguration)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "configuration": self.configuration.to_dict(),
        }


@dataclass
class CustomerProfile:
    """Business and administrative metadata for a customer organization."""
    profile_id: str
    tenant_id: str
    company_name: str
    contact_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    sla_tier: str = "TIER_2_BUSINESS_OPERATIONAL"
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "tenant_id": self.tenant_id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "address": self.address,
            "sla_tier": self.sla_tier,
            "notes": self.notes,
            "created_at": self.created_at,
        }


# ===========================================================================
# 3. IDENTITY, RBAC & ACCESS GOVERNANCE MODELS (WP 8.2)
# ===========================================================================

@dataclass
class User:
    """User account entity. Divided into internal NOC users and customer users."""
    user_id: str
    username: str
    email: str
    password_hash: str
    salt: str
    display_name: Optional[str] = None
    account_enabled: bool = True
    is_internal: bool = False
    tenant_id: Optional[str] = None  # None for global internal NOC users
    is_active: bool = True
    role_type: Optional[str] = None
    last_login_at: Optional[str] = None
    last_activity_at: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        res = {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name or self.username,
            "account_enabled": self.account_enabled,
            "email": self.email,
            "is_internal": self.is_internal,
            "tenant_id": self.tenant_id,
            "is_active": self.is_active,
            "role_type": self.role_type,
            "last_login_at": self.last_login_at,
            "last_activity_at": self.last_activity_at,
            "groups": self.groups,
            "permissions": self.permissions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_secrets:
            res["password_hash"] = self.password_hash
            res["salt"] = self.salt
        return res


@dataclass
class UserRole:
    """Role assignment binding a user to a specific role type."""
    assignment_id: str
    user_id: str
    role_type: str
    granted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "user_id": self.user_id,
            "role_type": self.role_type,
            "granted_at": self.granted_at,
        }


@dataclass
class UserSession:
    """Active authenticated session for an internal or customer user."""
    session_id: str
    user_id: str
    username: str
    tenant_id: Optional[str]
    is_internal: bool
    token: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    status: str = SessionStatus.ACTIVE.value
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    expires_at_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "username": self.username,
            "tenant_id": self.tenant_id,
            "is_internal": self.is_internal,
            "token": self.token,
            "roles": list(self.roles),
            "permissions": list(self.permissions),
            "status": self.status,
            "created_at": self.created_at,
            "expires_at_utc": self.expires_at_utc,
        }


PERMISSION_ALIASES: Dict[str, Set[str]] = {
    # Navigation / View
    "workspace.view": {"ai_assistant.view", "workspace.view"},
    "inventory.view": {"inventory.read", "devices.read", "inventory.device.read", "inventory.view"},
    "topology.view": {"topology.read", "topology.view"},
    "nms.view": {"nms.read", "nms.view"},
    "automations.view": {"playbooks.read", "automations.view"},
    "files.view": {"files.read", "files.view"},
    "models.view": {"models.read", "models.view"},
    "logs.view": {"logs.view", "audit.read", "logs.read"},
    "settings.view": {"settings.view"},
    "admin.view": {"admin.view", "users.read"},

    # Inventory / Device Actions
    "inventory.device.read": {"inventory.read", "devices.read", "inventory.device.read", "inventory.view"},
    "inventory.read": {"inventory.read", "devices.read", "inventory.device.read", "inventory.view"},
    "devices.read": {"inventory.read", "devices.read", "inventory.device.read", "inventory.view"},

    "inventory.device.create": {"inventory.create", "devices.create", "inventory.device.create"},
    "inventory.create": {"inventory.create", "devices.create", "inventory.device.create"},
    "devices.create": {"inventory.create", "devices.create", "inventory.device.create"},

    "inventory.device.update": {"inventory.update", "devices.update", "inventory.device.update"},
    "inventory.update": {"inventory.update", "devices.update", "inventory.device.update"},
    "devices.update": {"inventory.update", "devices.update", "inventory.device.update"},

    "inventory.device.delete": {"inventory.delete", "devices.delete", "inventory.device.delete"},
    "inventory.delete": {"inventory.delete", "devices.delete", "inventory.device.delete"},
    "devices.delete": {"inventory.delete", "devices.delete", "inventory.device.delete"},

    "inventory.device.ssh": {"inventory.device.ssh", "devices.ssh"},
    "devices.ssh": {"inventory.device.ssh", "devices.ssh"},

    # Topology & NMS Actions
    "topology.device.discover": {"topology.discover", "topology.device.discover"},
    "topology.discover": {"topology.discover", "topology.device.discover"},
    "nms.monitoring.read": {"nms.read", "nms.monitoring.read", "nms.view"},
    "nms.read": {"nms.read", "nms.monitoring.read", "nms.view"},
    "nms.monitoring.configure": {"nms.configure", "nms.monitoring.configure"},
    "nms.configure": {"nms.configure", "nms.monitoring.configure"},

    # Audit & Logs
    "audit.read": {"logs.view", "audit.read", "logs.read"},

    # Settings: Memory & Persona
    "settings.memory.view": {"settings.memory.view", "memory.read", "settings.view"},
    "memory.read": {"settings.memory.view", "memory.read", "settings.view"},
    "settings.memory.update": {"settings.memory.update", "memory.write"},
    "memory.write": {"settings.memory.update", "memory.write"},

    "settings.persona.view": {"settings.persona.view", "persona.read", "settings.view"},
    "persona.read": {"settings.persona.view", "persona.read", "settings.view"},
    "settings.persona.update": {"settings.persona.update", "persona.write"},
    "persona.write": {"settings.persona.update", "persona.write"},
}


@dataclass
class TenantContext:
    """
    Resolved security context for a request or background task.
    Enforces tenant scoping across all domain layers.
    """
    user_id: str
    username: str
    is_internal: bool
    tenant_id: Optional[str]
    roles: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    permissions: Set[str] = field(default_factory=set)
    session_id: Optional[str] = None
    account_enabled: bool = True

    def has_permission(self, perm: Any) -> bool:
        perm_str = perm.value if hasattr(perm, "value") else str(perm)
        if "SUPER_ADMIN" in self.groups or "PLATFORM_OWNER" in self.roles or "PLATFORM_SUPER_ADMIN" in self.roles:
            return True
        if perm_str in self.permissions:
            return True
        aliases = PERMISSION_ALIASES.get(perm_str, set())
        return bool(aliases & set(self.permissions))

    def can_access_tenant(self, target_tenant_id: str) -> bool:
        """NOC operators with global access can access any tenant; customer users only access their own."""
        if self.is_internal:
            return True
        return self.tenant_id == target_tenant_id

    def can_perform(
        self,
        action: str,
        resource: str,
        site_id: Optional[str] = None,
    ) -> bool:
        """
        Evaluates granular action (VIEW, CREATE, UPDATE, DELETE, EXECUTE, APPROVE, EXPORT,
        MANAGE_PERMISSIONS, ACCESS_SENSITIVE_DATA) on a resource.
        """
        if "SUPER_ADMIN" in self.groups or "PLATFORM_OWNER" in self.roles or "PLATFORM_SUPER_ADMIN" in self.roles:
            return True
        from core.tenant.permission_simulation import get_permission_simulation_service
        svc = get_permission_simulation_service()
        res = svc.simulate_permission(
            user_id=self.user_id,
            resource=resource,
            action=action,
            site_id=site_id,
        )
        return bool(res.get("allowed"))


# ===========================================================================
# 4. CUSTOMER NETWORK INVENTORY MODELS (WP 8.3)
# ===========================================================================

@dataclass
class Site:
    """Physical or logical customer site."""
    site_id: str
    tenant_id: str
    name: str
    slug: str
    group_id: Optional[str] = None
    address: Optional[str] = None
    timezone: str = "Asia/Jakarta"
    contact_person: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "group_id": self.group_id,
            "address": self.address,
            "timezone": self.timezone,
            "contact_person": self.contact_person,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass
class SiteGroup:
    """Logical grouping of sites (e.g., Regional, Branch, Data Center)."""
    group_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
        }


@dataclass
class TenantDevice:
    """
    Tenant-scoped network device record.
    Overlapping RFC 1918 safe: Scoped by (tenant_id, site_id, management_ip).
    """
    device_id: str
    tenant_id: str
    site_id: str
    name: str
    management_ip: str
    management_port: int = 22
    device_type: str = DeviceType.ROUTER.value
    vendor: str = "MikroTik"
    model: str = ""
    os_version: str = ""
    gateway_id: Optional[str] = None
    status: str = "ACTIVE"
    credential_ref: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "name": self.name,
            "management_ip": self.management_ip,
            "management_port": self.management_port,
            "device_type": self.device_type,
            "vendor": self.vendor,
            "model": self.model,
            "os_version": self.os_version,
            "gateway_id": self.gateway_id,
            "status": self.status,
            "credential_ref": self.credential_ref,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ===========================================================================
# 5. AUDIT LOG MODEL
# ===========================================================================

@dataclass
class AuditEntry:
    """Immutable audit record for operator actions, approvals, and security events."""
    audit_id: str
    tenant_id: Optional[str]
    user_id: Optional[str]
    username: str
    action: str
    resource_type: str
    resource_id: str
    details_json: str = "{}"
    ip_address: Optional[str] = None
    timestamp_utc: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": json.loads(self.details_json) if self.details_json else {},
            "ip_address": self.ip_address,
            "timestamp_utc": self.timestamp_utc,
        }


# ===========================================================================
# 6. CUSTOMER SUPPORT REQUESTS & NOTIFICATIONS (WP 8.9)
# ===========================================================================

class SupportCategory(str, Enum):
    INCIDENT = "INCIDENT"
    SERVICE_REQUEST = "SERVICE_REQUEST"
    BILLING = "BILLING"
    GENERAL = "GENERAL"
    CHANGE = "CHANGE"


class SupportPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SupportStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_CUSTOMER = "WAITING_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


VALID_SUPPORT_TRANSITIONS: Dict[str, Set[str]] = {
    SupportStatus.OPEN.value: {SupportStatus.ACKNOWLEDGED.value, SupportStatus.CLOSED.value},
    SupportStatus.ACKNOWLEDGED.value: {SupportStatus.IN_PROGRESS.value, SupportStatus.WAITING_CUSTOMER.value, SupportStatus.CLOSED.value},
    SupportStatus.IN_PROGRESS.value: {SupportStatus.WAITING_CUSTOMER.value, SupportStatus.RESOLVED.value, SupportStatus.CLOSED.value},
    SupportStatus.WAITING_CUSTOMER.value: {SupportStatus.IN_PROGRESS.value, SupportStatus.RESOLVED.value, SupportStatus.CLOSED.value},
    SupportStatus.RESOLVED.value: {SupportStatus.CLOSED.value, SupportStatus.IN_PROGRESS.value},
    SupportStatus.CLOSED.value: set(),  # Terminal
}


@dataclass
class SupportRequestComment:
    comment_id: str
    request_id: str
    tenant_id: str
    author_id: str
    author_name: str
    message: str
    is_internal: bool = False
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "is_internal": self.is_internal,
            "message": self.message,
            "created_at": self.created_at,
        }


@dataclass
class SupportRequest:
    request_id: str
    tenant_id: str
    requester_id: str
    category: str
    subject: str
    description: str
    priority: str = SupportPriority.MEDIUM.value
    status: str = SupportStatus.OPEN.value
    assigned_operator_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    resolved_at: Optional[str] = None
    comments: List[SupportRequestComment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "requester_id": self.requester_id,
            "category": self.category,
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "assigned_operator_id": self.assigned_operator_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "comments": [c.to_dict() for c in self.comments],
        }


@dataclass
class CustomerNotificationPreferences:
    pref_id: str
    tenant_id: str
    user_id: str
    notify_critical_incidents: bool = True
    notify_major_incidents: bool = True
    notify_service_degradation: bool = True
    notify_gateway_offline: bool = True
    notify_sla_breach: bool = True
    email_notifications: bool = True
    in_app_notifications: bool = True
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pref_id": self.pref_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "notify_critical_incidents": self.notify_critical_incidents,
            "notify_major_incidents": self.notify_major_incidents,
            "notify_service_degradation": self.notify_service_degradation,
            "notify_gateway_offline": self.notify_gateway_offline,
            "notify_sla_breach": self.notify_sla_breach,
            "email_notifications": self.email_notifications,
            "in_app_notifications": self.in_app_notifications,
            "updated_at": self.updated_at,
        }
