// src/context/AuthContext.jsx
// AIRA OS — Identity, Authentication & Group RBAC Context (Phase F.1)
// Mandatory Authentication: No anonymous or guest access.

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { getAuthHeaders } from "../api.js";

export const AuthState = {
  INITIALIZING: "INITIALIZING",
  UNAUTHENTICATED: "UNAUTHENTICATED",
  AUTHENTICATED: "AUTHENTICATED",
  SESSION_EXPIRED: "SESSION_EXPIRED",
  LOGGING_OUT: "LOGGING_OUT",
};

const AuthContext = createContext(null);

const TOKEN_KEY = "aira_auth_token";
const DRAFT_PROMPT_KEY = "aira_draft_prompt";

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(AuthState.INITIALIZING);
  const [user, setUser] = useState(null);

  // Modals
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isLoginRequiredModalOpen, setIsLoginRequiredModalOpen] = useState(false);
  const [loginRequiredReason, setLoginRequiredReason] = useState("");

  // Prompt preservation
  const [draftPrompt, setDraftPromptState] = useState(() => {
    try {
      return sessionStorage.getItem(DRAFT_PROMPT_KEY) || "";
    } catch {
      return "";
    }
  });

  const setDraftPrompt = useCallback((prompt) => {
    setDraftPromptState(prompt);
    try {
      if (prompt) {
        sessionStorage.setItem(DRAFT_PROMPT_KEY, prompt);
      } else {
        sessionStorage.removeItem(DRAFT_PROMPT_KEY);
      }
    } catch {}
  }, []);

  // Session restoration logic on app mount
  const restoreSession = useCallback(async () => {
    let token = null;
    try {
      token = localStorage.getItem(TOKEN_KEY);
    } catch {}

    if (!token) {
      setUser(null);
      setStatus(AuthState.UNAUTHENTICATED);
      setIsLoginModalOpen(true);
      return;
    }

    try {
      const res = await fetch("/api/v1/auth/me", {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        if (data.success && data.user) {
          setUser(data.user);
          setStatus(AuthState.AUTHENTICATED);
          window.dispatchEvent(new CustomEvent("aira:auth_success", { detail: data.user }));
          return;
        }
      }

      // If token invalid, expired, or revoked
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {}
      setUser(null);
      setStatus(AuthState.UNAUTHENTICATED);
      setIsLoginModalOpen(true);
    } catch (err) {
      console.warn("Error restoring user session:", err);
      setUser(null);
      setStatus(AuthState.UNAUTHENTICATED);
      setIsLoginModalOpen(true);
    }
  }, []);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // Periodic heartbeat reporting when authenticated (every 30 seconds)
  useEffect(() => {
    if (status !== AuthState.AUTHENTICATED) return;

    const heartbeatTimer = setInterval(async () => {
      try {
        const headers = getAuthHeaders();
        if (headers.Authorization) {
          await fetch("/api/v1/auth/heartbeat", {
            method: "POST",
            headers,
          });
        }
      } catch {
        // Heartbeat failure ignored gracefully
      }
    }, 30000);

    return () => clearInterval(heartbeatTimer);
  }, [status]);

  // Listen for global session expiration event
  useEffect(() => {
    function handleSessionExpired() {
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {}
      setUser(null);
      setStatus(AuthState.SESSION_EXPIRED);
      setIsLoginModalOpen(true);
    }

    window.addEventListener("aira:session_expired", handleSessionExpired);
    return () => window.removeEventListener("aira:session_expired", handleSessionExpired);
  }, []);

  // Login handler
  const login = useCallback(
    async ({ usernameOrEmail, password, totpCode = null, adminOnly = false }) => {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username_or_email: usernameOrEmail,
          password,
          totp_code: totpCode,
          admin_only: adminOnly,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || data.message || "Gagal masuk. Periksa kembali kredensial Anda.");
      }

      if (data.token) {
        try {
          localStorage.setItem(TOKEN_KEY, data.token);
        } catch {}

        setUser(data.user);
        setStatus(AuthState.AUTHENTICATED);
        window.dispatchEvent(new CustomEvent("aira:auth_success", { detail: data.user }));

        // Close auth modals
        setIsLoginModalOpen(false);
        setIsRegisterModalOpen(false);
        setIsLoginRequiredModalOpen(false);
      }

      return data;
    },
    []
  );

  // Register handler
  const register = useCallback(
    async ({ username, email, password, organizationName = null }) => {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          email,
          password,
          organization_name: organizationName,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || data.message || "Pendaftaran gagal.");
      }

      if (data.token) {
        try {
          localStorage.setItem(TOKEN_KEY, data.token);
        } catch {}

        setUser(data.user);
        setStatus(AuthState.AUTHENTICATED);
        window.dispatchEvent(new CustomEvent("aira:auth_success", { detail: data.user }));

        setIsLoginModalOpen(false);
        setIsRegisterModalOpen(false);
        setIsLoginRequiredModalOpen(false);
      }

      return data;
    },
    []
  );

  // Complete Logout handler (server-side token revocation + storage cleanup)
  const logout = useCallback(async () => {
    setStatus(AuthState.LOGGING_OUT);
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      if (token) {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });
      }
    } catch (err) {
      console.warn("Server-side logout revocation failed:", err);
    } finally {
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {}
      setUser(null);
      setStatus(AuthState.UNAUTHENTICATED);
      setIsLoginModalOpen(true);
    }
  }, []);

  const openLogin = useCallback(() => {
    setIsRegisterModalOpen(false);
    setIsLoginRequiredModalOpen(false);
    setIsLoginModalOpen(true);
  }, []);

  const openRegister = useCallback(() => {
    setIsLoginModalOpen(false);
    setIsLoginRequiredModalOpen(false);
    setIsRegisterModalOpen(true);
  }, []);

  const isGuest = false; // Guest Mode completely eliminated in Phase F.1
  const isAdmin =
    Boolean(user?.is_internal) ||
    Boolean(user?.groups?.includes("SUPER_ADMIN")) ||
    Boolean(user?.groups?.includes("ADMIN")) ||
    Boolean(user?.roles?.some((r) => ["PLATFORM_OWNER", "SUPERADMIN", "PLATFORM_SUPER_ADMIN"].includes(r)));

  const hasPermission = useCallback(
    (permissionId) => {
      if (!user) return false;
      if (user.groups?.includes("SUPER_ADMIN")) return true;
      if (!Array.isArray(user.permissions)) return false;

      // Direct check
      if (user.permissions.includes(permissionId)) return true;

      // Canonical aliases mapping (Phase F.2)
      const ALIASES = {
        "workspace.view": ["ai_assistant.view", "dashboard.read"],
        "ai_assistant.view": ["workspace.view", "dashboard.read"],
        "inventory.view": ["inventory.read", "devices.read"],
        "topology.view": ["topology.read"],
        "nms.view": ["nms.read"],
        "automations.view": ["playbooks.read", "automation.read"],
        "files.view": ["workspace.view"],
        "models.view": ["settings.read"],
        "logs.view": ["audit.read"],
        "settings.view": ["settings.read", "settings.write"],
        "settings.memory.view": ["settings.view", "settings.read"],
        "settings.memory.update": ["settings.write"],
        "settings.persona.view": ["settings.view", "settings.read"],
        "settings.persona.update": ["settings.write"],
        "inventory.device.create": ["devices.create", "inventory.create"],
        "inventory.device.read": ["devices.read", "inventory.read"],
        "inventory.device.update": ["devices.update", "inventory.update"],
        "inventory.device.delete": ["devices.delete", "inventory.delete"],
        "inventory.device.ssh": ["devices.read", "devices.diagnostics"],
      };

      const equivalents = ALIASES[permissionId] || [];
      return equivalents.some((eq) => user.permissions.includes(eq));
    },
    [user]
  );

  const hasNetworkingPlus = true; // All authenticated users can access networking features based on RBAC permissions

  const value = {
    status,
    user,
    isGuest,
    isAdmin,
    hasPermission,
    hasNetworkingPlus,
    draftPrompt,
    setDraftPrompt,
    isLoginModalOpen,
    setIsLoginModalOpen,
    isRegisterModalOpen,
    setIsRegisterModalOpen,
    isLoginRequiredModalOpen,
    setIsLoginRequiredModalOpen,
    loginRequiredReason,
    login,
    register,
    logout,
    openLogin,
    openRegister,
    refreshProfile: restoreSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
