/* Girly 🌸 — shared client helpers: API, session guard, theme, toast */

const Girly = {
  /* ---- API ---- */
  async api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...opts,
    });
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || `request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  },

  /* ---- Session guard ----
     Redirects to the sign-in page when a page requires an account. */
  async requireAuth() {
    try {
      const me = await this.api("/api/me");
      return me;
    } catch (e) {
      if (e.status === 401) {
        window.location.href = "index.html";
        return null;
      }
      throw e;
    }
  },

  /* ---- Toast ---- */
  toast(message, icon = "check_circle") {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.innerHTML = `<span class="material-symbols-outlined" style="font-size:18px;color:var(--primary-fixed)">${icon}</span><span></span>`;
    el.lastElementChild.textContent = message;
    requestAnimationFrame(() => el.classList.add("show"));
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2800);
  },

  /* ---- Theme ---- */
  applyTheme() {
    const saved = localStorage.getItem("girly-theme");
    const dark = saved ? saved === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  },
  toggleTheme() {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("girly-theme", dark ? "dark" : "light");
    return dark;
  },

  /* ---- Helpers ---- */
  /* Passwords must combine letters, numbers, and special characters.
     Returns an error message, or "" when the password passes. */
  passwordError(pw) {
    if (!/[A-Za-z]/.test(pw)) return "Include at least one letter.";
    if (!/\d/.test(pw)) return "Include at least one number.";
    if (!/[^A-Za-z0-9]/.test(pw)) return "Include at least one special character (e.g. ! @ # $).";
    return "";
  },

  escapeHtml(str) {
    return String(str ?? "").replace(/[&<>'"]/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[c]));
  },

  initials(name) {
    return name.split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2)
      .join("").toUpperCase();
  },

  fmtDate(iso, opts) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString(undefined, opts || { month: "short", day: "numeric", year: "numeric" });
  },

  /* ---- Shared chrome (header + bottom nav) ---- */
  mountChrome({ active, name = "", avatar = "", showLearn = true, role = "" }) {
    // header
    const header = document.createElement("header");
    header.className = "app-header";
    const avatarContent = avatar
      ? `<img src="${avatar}" alt="Your profile picture"/>`
      : this.escapeHtml(this.initials(name || "G"));
    header.innerHTML = `
      <div class="app-header-inner">
        <a class="brand" href="tracker.html">
          <img class="brand-logo" src="assets/logo.svg" alt="Girly logo"/>
          <span class="brand-name">Girly</span><span aria-hidden="true" style="font-size:12px">💜</span>
        </a>
        <div class="header-actions">
          ${showLearn ? `<a class="header-pill" href="learn.html">
            <span class="material-symbols-outlined" style="font-size:15px">menu_book</span><span>Learn</span></a>` : ""}
          <button class="icon-btn" id="theme-btn" aria-label="Toggle appearance theme" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">routine</span>
          </button>
          <button class="icon-btn" id="logout-btn" aria-label="Sign out of Girly" title="Sign out" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">logout</span>
          </button>
          <button class="icon-btn" id="profile-btn" aria-label="Open your profile" title="Your profile" type="button" style="width:auto;height:auto;padding:2px">
            <span class="avatar">${avatarContent}</span>
          </button>
        </div>
      </div>`;
    document.body.prepend(header);

    // bottom nav
    const nav = document.createElement("nav");
    nav.className = "bottom-nav";
    // The admin tab is only offered to admins — everyone else would just be
    // bounced by the page's own guard, so there's no reason to show it.
    const items = [
      { id: "profile", icon: "person", label: "Profile", href: "profile.html" },
      { id: "tracker", icon: "calendar_today", label: "Tracker", href: "tracker.html" },
      { id: "learn", icon: "school", label: "Learn", href: "learn.html" },
      { id: "assistant", icon: "auto_awesome", label: "Assistant", href: "assistant.html" },
      ...(role === "admin"
        ? [{ id: "admin", icon: "shield_person", label: "Admin", href: "admin.html" }]
        : []),
    ];
    nav.innerHTML = `<div class="bottom-nav-inner">${items.map((it) => `
      <a class="nav-item ${it.id === active ? "active" : ""}" href="${it.href}" aria-current="${it.id === active ? "page" : "false"}">
        <span class="material-symbols-outlined">${it.icon}</span><span>${it.label}</span>
      </a>`).join("")}</div>`;
    document.body.appendChild(nav);

    // theme button
    header.querySelector("#theme-btn").addEventListener("click", () => {
      const dark = this.toggleTheme();
      this.toast(dark ? "Night mode enabled 💜" : "Light mode restored", dark ? "dark_mode" : "light_mode");
    });

    // profile button → profile page
    header.querySelector("#profile-btn").addEventListener("click", () => {
      window.location.href = "profile.html";
    });

    // sign out (top right, on every page)
    header.querySelector("#logout-btn").addEventListener("click", async () => {
      if (!confirm("Sign out of Girly?")) return;
      await this.api("/api/logout", { method: "POST" });
      window.location.href = "index.html";
    });

    this.applyTheme();
  },
};

Girly.applyTheme();
