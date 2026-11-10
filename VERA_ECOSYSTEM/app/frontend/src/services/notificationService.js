/**
 * services/notificationService.js — Native Desktop Notifications for VERA.
 *
 * Provides a resilient, opt-in notification engine supporting:
 * - Direct window.Notification API (in-tab and background tab)
 * - Service Worker Push & Web Notification integration
 * - Granular deduplication via stable tags
 * - Automatic window/tab focusing on click
 * - User preference storage (localStorage)
 */

const STORAGE_KEY_PREF = "vera_desktop_notifications_enabled";

/**
 * Checks whether the browser supports native desktop notifications.
 */
export function isNotificationSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

/**
 * Gets current notification permission status: "granted" | "denied" | "default" | "unsupported".
 */
export function getNotificationPermission() {
  if (!isNotificationSupported()) return "unsupported";
  return Notification.permission;
}

/**
 * Checks whether desktop notifications are enabled by both permission and user preference.
 */
export function isNotificationEnabled() {
  if (!isNotificationSupported()) return false;
  if (Notification.permission !== "granted") return false;
  return localStorage.getItem(STORAGE_KEY_PREF) !== "false";
}

/**
 * Sets user preference for desktop notifications.
 */
export function setNotificationPreference(enabled) {
  try {
    localStorage.setItem(STORAGE_KEY_PREF, enabled ? "true" : "false");
  } catch {
    // Ignore localStorage write failure in restricted iframe/sandbox
  }
}

/**
 * Requests permission from user with opt-in prompt.
 */
export async function requestNotificationPermission() {
  if (!isNotificationSupported()) {
    return false;
  }

  if (Notification.permission === "granted") {
    setNotificationPreference(true);
    return true;
  }

  if (Notification.permission === "denied") {
    return false;
  }

  try {
    const result = await Notification.requestPermission();
    const granted = result === "granted";
    if (granted) {
      setNotificationPreference(true);
    }
    return granted;
  } catch (err) {
    console.warn("Failed to request notification permission:", err);
    return false;
  }
}

/**
 * Displays a desktop notification with deduplication and focus handling.
 *
 * @param {Object} options
 * @param {string} options.title - Notification title
 * @param {string} [options.body] - Notification message body
 * @param {string} [options.icon] - Icon URL (defaults to /favicon.ico)
 * @param {string} [options.tag] - Deduplication tag
 * @param {Object} [options.data] - Custom data passed to click handler
 * @param {string} [options.url] - Deep-link navigation URL
 * @param {boolean} [options.onlyWhenHidden=true] - Only show if tab is not focused
 * @param {boolean} [options.requireInteraction=false] - Persist notification until dismissed
 */
export async function showDesktopNotification({
  title = "VERA Network Intelligence",
  body = "",
  icon = "/favicon.ico",
  tag = "vera-notification",
  data = {},
  url = "/",
  onlyWhenHidden = true,
  requireInteraction = false,
} = {}) {
  if (!isNotificationSupported() || Notification.permission !== "granted") {
    return null;
  }

  // If configured to show only when tab is in background, check visibilityState
  if (onlyWhenHidden && typeof document !== "undefined" && document.visibilityState === "visible") {
    return null;
  }

  const notificationOptions = {
    body,
    icon,
    badge: icon,
    tag,
    data: { ...data, url },
    requireInteraction,
  };

  // Try Service Worker registration first for background persistence
  if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
    try {
      const reg = await navigator.serviceWorker.ready;
      if (reg && reg.showNotification) {
        await reg.showNotification(title, notificationOptions);
        return true;
      }
    } catch {
      // Fall through to window.Notification
    }
  }

  // Standard window.Notification fallback
  try {
    const notif = new Notification(title, notificationOptions);
    notif.onclick = () => {
      window.focus();
      if (url && window.location.pathname !== url) {
        window.history.pushState(null, "", url);
      }
      notif.close();
    };
    return notif;
  } catch (err) {
    console.warn("Could not dispatch desktop notification:", err);
    return null;
  }
}
