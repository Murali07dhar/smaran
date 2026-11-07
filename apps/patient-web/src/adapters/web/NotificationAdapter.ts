import type { NotificationAdapter } from "../types";

// IMPORTANT (documented in HANDOFF.md "Known gaps"): browsers only reliably
// fire scheduled/background notifications for an *installed* PWA with a
// registered service worker, and even then, delivery while the OS has fully
// killed the app is not guaranteed on all platforms (notably iOS Safari has
// tight limits). `schedule()` here is best-effort via setTimeout while the
// tab/app is open; the full-screen in-app reminder alert is the reliable
// fallback and should always be treated as the primary UX, not this.
const timers = new Map<string, ReturnType<typeof setTimeout>>();

export const webNotificationAdapter: NotificationAdapter = {
  async requestPermission() {
    if (typeof Notification === "undefined") return "denied";
    const perm = await Notification.requestPermission();
    return perm;
  },
  async show(title, body, opts) {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg) {
      await reg.showNotification(title, { body, tag: opts?.tag });
    } else {
      new Notification(title, { body, tag: opts?.tag });
    }
  },
  async schedule(at, title, body, opts) {
    const delay = Math.max(0, at.getTime() - Date.now());
    const tag = opts?.tag ?? crypto.randomUUID();
    const handle = setTimeout(() => {
      void webNotificationAdapter.show(title, body, { tag });
      timers.delete(tag);
    }, delay);
    timers.set(tag, handle);
  },
  async cancel(tag) {
    const handle = timers.get(tag);
    if (handle) {
      clearTimeout(handle);
      timers.delete(tag);
    }
  }
};
