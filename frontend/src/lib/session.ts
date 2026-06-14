import { useSyncExternalStore } from "react";

// The single frontend credential store: the admin secret the owner pasted at
// /auth, kept in localStorage and attached by `request()` (api/client). Swapping
// the secret for a login flow rewrites this module + the attach point only.
const KEY = "bookrag.adminSecret";
const EVT = "bookrag:auth"; // same-tab change signal (storage event is cross-tab only)

export function getSecret(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setSecret(s: string): void {
  window.localStorage.setItem(KEY, s);
  window.dispatchEvent(new Event(EVT));
}

export function clearSecret(): void {
  window.localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(EVT));
}

export function isAuthed(): boolean {
  return !!getSecret();
}

// Reactive read for components. "Authed" means a secret is present locally, not
// that it is correct — a wrong secret reads as admin until a write returns 403.
export function useAuthed(): boolean {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVT, cb); // same-tab set/clear
      window.addEventListener("storage", cb); // cross-tab
      return () => {
        window.removeEventListener(EVT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    () => isAuthed(), // client snapshot
    () => false, // server snapshot — render as guest, hydrate to truth
  );
}
