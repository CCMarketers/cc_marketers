/**
 * notifications.js  (v2 — no Tailwind dependency)
 * -------------------------------------------------
 * Structural visibility uses style.display directly.
 * Toasts use inline styles — no external CSS framework needed.
 */

(function () {
  "use strict";

  // ─── Config ────────────────────────────────────────────────────────────────
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/notifications/`;
  const API_LIST     = "/notifications/api/list/";
  const API_MARK_READ = (id) => `/notifications/api/mark-read/${id}/`;
  const API_MARK_ALL = "/notifications/api/mark-all-read/";
  const TOAST_DURATION = 4000;
  const RECONNECT_DELAY = 3000;

  // ─── State ─────────────────────────────────────────────────────────────────
  let socket = null;
  let unreadCount = 0;
  let dropdownOpen = false;

  // ─── DOM refs ──────────────────────────────────────────────────────────────
  let badge, list, emptyMsg, toastContainer;

  // ─── Boot ──────────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    badge          = document.getElementById("notif-badge");
    list           = document.getElementById("notif-list");
    emptyMsg       = document.getElementById("notif-empty");
    toastContainer = document.getElementById("notif-toast-container");

    if (!badge) return; // Not logged in / bell not rendered

    fetchInitialNotifications();
    connectWebSocket();

    // Close on outside click
    document.addEventListener("click", (e) => {
      const wrapper = document.getElementById("notif-bell-wrapper");
      if (wrapper && !wrapper.contains(e.target)) closeDropdown();
    });
  });

  // ─── WebSocket ─────────────────────────────────────────────────────────────
  function connectWebSocket() {
    socket = new WebSocket(WS_URL);

    socket.onopen  = () => console.debug("[Notif] WS connected");
    socket.onclose = () => {
      console.debug("[Notif] WS closed — reconnecting in 3s");
      setTimeout(connectWebSocket, RECONNECT_DELAY);
    };
    socket.onerror = () => socket.close();

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "new_notification") handleIncomingNotification(data.notification);
        else if (data.type === "unread_count")   setUnreadCount(data.count);
      } catch (e) {
        console.warn("[Notif] Bad WS message", e);
      }
    };
  }

  // ─── Initial REST fetch ────────────────────────────────────────────────────
  function fetchInitialNotifications() {
    fetch(API_LIST, { credentials: "same-origin" })
      .then((r) => r.json())
      .then(({ notifications, unread_count }) => {
        setUnreadCount(unread_count);
        if (!notifications.length) return;
        if (emptyMsg) emptyMsg.remove();
        notifications.forEach((n) => {
          if (!document.getElementById(`nd-${n.id}`)) {
            list.appendChild(buildDropdownItem(n));
          }
        });
      })
      .catch((e) => console.warn("[Notif] fetch failed", e));
  }

  // ─── Real-time handler ─────────────────────────────────────────────────────
  function handleIncomingNotification(n) {
    setUnreadCount(unreadCount + 1);
    if (emptyMsg && emptyMsg.parentNode) emptyMsg.remove();
    list.prepend(buildDropdownItem(n));
    showToast(n);
  }

  // ─── Badge — uses style.display, not Tailwind 'hidden' ────────────────────
  function setUnreadCount(count) {
    unreadCount = count;
    if (!badge) return;
    badge.textContent = count > 99 ? "99+" : count;
    badge.style.display = count > 0 ? "flex" : "none";
  }

  // ─── Toast — fully inline-styled, matches your color scheme ───────────────
  const TOAST_COLORS = {
    green:  { bg: "#f0fdf4", border: "#86efac", text: "#166534", icon: "#16a34a" },
    red:    { bg: "#fef2f2", border: "#fca5a5", text: "#991b1b", icon: "#dc2626" },
    yellow: { bg: "#fefce8", border: "#fde047", text: "#854d0e", icon: "#ca8a04" },
    blue:   { bg: "#eff6ff", border: "#93c5fd", text: "#1e3a8a", icon: "#2563eb" },
  };
  const TYPE_COLOR = {
    submission_approved: "green",
    wallet_credit:       "green",   // model: WALLET_CREDIT
    wallet_withdrawal:   "yellow",  // model: WALLET_WITHDRAWAL
    submission_rejected: "red",
    chat_message:        "blue",    // model: CHAT_MESSAGE
    new_submission:      "blue",
    referral_signup:     "blue",    // model: REFERRAL_SIGNUP
  };

  function showToast(n) {
    if (!toastContainer) return;

    const c = TOAST_COLORS[TYPE_COLOR[n.type] || "blue"];

    const toast = document.createElement("div");
    Object.assign(toast.style, {
      pointerEvents:   "auto",
      display:         "flex",
      alignItems:      "center",
      justifyContent:  "space-between",
      gap:             "12px",
      maxWidth:        "360px",
      width:           "100%",
      padding:         "14px 16px",
      borderRadius:    "10px",
      border:          `1px solid ${c.border}`,
      background:      c.bg,
      color:           c.text,
      boxShadow:       "0 4px 20px rgba(0,0,0,0.10)",
      animation:       "notifFadeDown 0.3s ease-out",
      transition:      "opacity 0.4s, transform 0.4s",
      cursor:          n.link ? "pointer" : "default",
    });

    toast.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;min-width:0;flex:1">
        <svg style="flex-shrink:0;width:18px;height:18px;color:${c.icon}" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" clip-rule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0
               1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0
               100-2v-3a1 1 0 00-1-1H9z"/>
        </svg>
        <div style="min-width:0">
          <p style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            ${escHtml(n.title)}
          </p>
          <p style="font-size:12px;opacity:0.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px">
            ${escHtml(n.message)}
          </p>
        </div>
      </div>
      <button
        aria-label="Dismiss"
        style="flex-shrink:0;background:none;border:none;cursor:pointer;padding:2px;color:${c.icon};opacity:0.7"
        onclick="this.closest('[data-notif-toast]').remove()"
      >
        <svg width="14" height="14" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" clip-rule="evenodd"
            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1
               0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414
               1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414
               L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
        </svg>
      </button>
    `;

    toast.dataset.notifToast = "1";

    if (n.link) {
      toast.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        window.location.href = n.link;
      });
    }

    toastContainer.prepend(toast);

    // Auto-dismiss after TOAST_DURATION
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-8px)";
      setTimeout(() => toast.remove(), 450);
    }, TOAST_DURATION);
  }

  // Inject the keyframe animation once
  if (!document.getElementById("notif-keyframes")) {
    const style = document.createElement("style");
    style.id = "notif-keyframes";
    style.textContent = `
      @keyframes notifFadeDown {
        from { opacity: 0; transform: translateY(-10px); }
        to   { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }

  // ─── Dropdown item builder — uses notif-item CSS classes from bell template ─
  function buildDropdownItem(n) {
    const li = document.createElement("li");
    li.id = `nd-${n.id}`;
    li.className = `notif-item${n.is_read ? "" : " unread"}`;

    const iconBg   = n.is_read ? "#f3f4f6" : "#dbeafe";
    const iconColor = n.is_read ? "#9ca3af" : "#3b82f6";

    li.innerHTML = `
      <div class="notif-icon" style="background:${iconBg}">
        <svg width="14" height="14" fill="${iconColor}" viewBox="0 0 20 20">
          <path d="M10 2a6 6 0 00-6 6v1H2l1 9h14l1-9h-2V8a6 6 0 00-6-6z"/>
        </svg>
      </div>
      <div class="notif-body">
        <p class="notif-title">${escHtml(n.title)}</p>
        <p class="notif-msg">${escHtml(n.message)}</p>
        <p class="notif-time">${timeAgo(n.created_at)}</p>
      </div>
      ${!n.is_read ? '<span class="notif-dot"></span>' : ""}
    `;

    li.addEventListener("click", () => {
      markRead(n.id, li);
      if (n.link) window.location.href = n.link;
    });

    return li;
  }

  // ─── Mark single read ──────────────────────────────────────────────────────
  function markRead(id, liEl) {
    fetch(API_MARK_READ(id), {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCsrf() },
    }).catch(() => {});

    // Optimistic
    liEl.classList.remove("unread");
    liEl.querySelector(".notif-dot")?.remove();
    setUnreadCount(Math.max(0, unreadCount - 1));
  }

  // ─── Mark all read (called from bell template button) ─────────────────────
  window.markAllRead = function () {
    fetch(API_MARK_ALL, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCsrf() },
    })
      .then(() => {
        setUnreadCount(0);
        document.querySelectorAll(".notif-item.unread").forEach((li) => {
          li.classList.remove("unread");
          li.querySelector(".notif-dot")?.remove();
        });
      })
      .catch(() => {});
  };

  // ─── Dropdown toggle (called from bell template onclick) ──────────────────
  window.toggleNotifDropdown = function () {
    const dropdown = document.getElementById("notif-dropdown");
    if (!dropdown) return;
    dropdownOpen = !dropdownOpen;
    // Use style.display — works regardless of CSS framework
    dropdown.style.display = dropdownOpen ? "flex" : "none";
  };

  function closeDropdown() {
    const dropdown = document.getElementById("notif-dropdown");
    if (dropdown) dropdown.style.display = "none";
    dropdownOpen = false;
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────
  function getCsrf() {
    return (
      document.cookie
        .split("; ")
        .find((r) => r.startsWith("csrftoken="))
        ?.split("=")[1] || ""
    );
  }

  function escHtml(str) {
    const d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
  }

  function timeAgo(isoString) {
    const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (diff < 60)    return "just now";
    if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }
})();