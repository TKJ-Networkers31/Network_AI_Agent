// src/context/AuthContext.jsx
// AIRA OS — Identity, Authentication & Guest Session Context
// Manages 5 core states: INITIALIZING, GUEST, AUTHENTICATED, SESSION_EXPIRED, LOGGING_OUT

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { getAuthHeaders } from "../api.js";

export const AuthState = {
  INITIALIZING: "INITIALIZING",
  GUEST: "GUEST",
  AUTHENTICATED: "AUTHENTICATED",
  SESSION_EXPIRED: "SESSION_EXPIRED",
  LOGGING_OUT: "LOGGING_OUT",
};

const AuthContext = createContext(null);

const TOKEN_KEY = "aira_auth_token";
const GUEST_KEY = "aira_guest_id";
const DRAFT_PROMPT_KEY = "aira_draft_prompt";

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(AuthState.INITIALIZING);
  const [user, setUser] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [quota, setQuota] = useState(null);
  const [entitlements, setEntitlements] = useState(null);

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

  // Ensure Guest ID exists
  const getOrCreateGuestId = useCallback(() => {
    try {
      let gid = localStorage.getItem(GUEST_KEY);
      if (!gid) {
        gid = "gst_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
        localStorage.setItem(GUEST_KEY, gid);
      }
      return gid;
    } catch {
      return "guest_fallback";
    }
  }, []);

  // Load guest quota
  const loadGuestQuota = useCallback(async () => {
    try {
      const gid = getOrCreateGuestId();
      const res = await fetch(`/api/v1/auth/guest-quota?guest_id=${encodeURIComponent(gid)}`);
      const data = await res.json();
      if (data.success && data.quota) {
        setQuota(data.quota);
      }
    } catch (err) {
      console.warn("Failed to fetch guest quota:", err);
    }
  }, [getOrCreateGuestId]);

  // Session restoration logic on app mount
  const restoreSession = useCallback(async () => {
    let token = null;
    try {
      token = localStorage.getItem(TOKEN_KEY);
    } catch {}

    if (!token) {
      // Clean Guest Mode — NEVER inject lingga_admin or default identity
      setUser(null);
      setSubscription(null);
      setStatus(AuthState.GUEST);
      await loadGuestQuota();
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
          setSubscription(data.subscription);
          setEntitlements(data.entitlements);
          setQuota(data.quota);
          setStatus(AuthState.AUTHENTICATED);
          return;
        }
      }

      // If token invalid, expired, or revoked
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {}
      setUser(null);
      setSubscription(null);
      setStatus(AuthState.GUEST);
      await loadGuestQuota();
    } catch (err) {
      console.warn("Error restoring user session:", err);
      setUser(null);
      setStatus(AuthState.GUEST);
      await loadGuestQuota();
    }
  }, [loadGuestQuota]);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // Listen for global session expiration event
  useEffect(() => {
    function handleSessionExpired() {
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {}
      setUser(null);
      setSubscription(null);
      setStatus(AuthState.SESSION_EXPIRED);
      loadGuestQuota();
    }

    window.addEventListener("aira:session_expired", handleSessionExpired);
    return () => window.removeEventListener("aira:session_expired", handleSessionExpired);
  }, [loadGuestQuota]);

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

      if (data.mfa_required) {
        return { mfa_required: true, username: data.username };
      }

      if (data.token) {
        try {
          localStorage.setItem(TOKEN_KEY, data.token);
        } catch {}

        setUser(data.user);
        setSubscription(data.subscription);
        setEntitlements(data.entitlements);
        setQuota(data.quota);
        setStatus(AuthState.AUTHENTICATED);

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
        setQuota(data.quota);
        setStatus(AuthState.AUTHENTICATED);

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
      setSubscription(null);
      setEntitlements(null);
      setStatus(AuthState.GUEST);
      await loadGuestQuota();
    }
  }, [loadGuestQuota]);

  // Continue as guest
  const continueAsGuest = useCallback(() => {
    setIsLoginModalOpen(false);
    setIsRegisterModalOpen(false);
    setIsLoginRequiredModalOpen(false);
    if (status !== AuthState.AUTHENTICATED) {
      setStatus(AuthState.GUEST);
    }
  }, [status]);

  // Open login required modal preserving draft prompt
  const requireLogin = useCallback(
    (reason = "Silakan masuk untuk melanjutkan penggunaan AIRA Workspace.", promptToPreserve = "") => {
      if (promptToPreserve) {
        setDraftPrompt(promptToPreserve);
      }
      setLoginRequiredReason(reason);
      setIsLoginRequiredModalOpen(true);
    },
    [setDraftPrompt]
  );

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

  const isGuest = status === AuthState.GUEST || status === AuthState.INITIALIZING || !user;
  const isAdmin =
    Boolean(user?.is_internal) ||
    Boolean(
      user?.roles?.some((r) =>
        ["PLATFORM_OWNER", "SUPERADMIN", "PLATFORM_SUPER_ADMIN", "NOC_ADMIN", "ADMIN"].includes(r)
      )
    );

  const hasNetworkingPlus =
    Boolean(isAdmin) ||
    Boolean(entitlements?.networking_plus) ||
    Boolean(subscription?.has_networking_plus) ||
    subscription?.plan_id === "ENTERPRISE";

  const value = {
    status,
    user,
    subscription,
    quota,
    entitlements,
    isGuest,
    isAdmin,
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
    continueAsGuest,
    requireLogin,
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
