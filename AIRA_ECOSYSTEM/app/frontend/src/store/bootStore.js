/**
 * bootStore.js — status boot AIRA OS (Phase 2.1).
 *
 * hasBootedThisSession -> sessionStorage: reset tiap tab baru/hard
 * refresh, TAPI tetap true selama SPA hidup (App.jsx tidak pernah
 * unmount saat pindah halaman) - inilah yang membuat Boot hanya
 * muncul sekali per "pembukaan aplikasi", bukan tiap ganti menu.
 *
 * hasSeenFirstBoot -> localStorage: persisten lintas sesi, dipakai
 * onboarding FirstBoot yang cuma tampil sekali seumur install.
 */

const SESSION_KEY = "aira_booted_session";
const FIRST_BOOT_KEY = "aira_seen_first_boot";

export function hasBootedThisSession() {
  try {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markBootedThisSession() {
  try {
    sessionStorage.setItem(SESSION_KEY, "1");
  } catch {
    // private mode / storage disabled - boleh boot ulang, tidak fatal
  }
}

export function hasSeenFirstBoot() {
  try {
    return localStorage.getItem(FIRST_BOOT_KEY) === "1";
  } catch {
    return false;
  }
}

export function markFirstBootSeen() {
  try {
    localStorage.setItem(FIRST_BOOT_KEY, "1");
  } catch {
    // abaikan
  }
}

export function resetBootState() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(FIRST_BOOT_KEY);
  } catch {
    // abaikan
  }
}