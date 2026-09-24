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
  mountChrome({ active, name = "", avatar = "", showLearn = true, role = "", overflow = false, onClearChat = null }) {
    // Mounting twice is a move a page makes on purpose — profile.html re-mounts
    // after a picture change so the header avatar keeps up — so clear out any
    // previous chrome first. Without this the second call leaves two headers
    // stacked and two nav bars, the old one still showing the old picture.
    document.querySelector(".app-header")?.remove();
    document.querySelector(".bottom-nav")?.remove();

    // header
    const header = document.createElement("header");
    header.className = "app-header";
    const avatarContent = avatar
      ? `<img src="${avatar}" alt="Your profile picture"/>`
      : this.escapeHtml(this.initials(name || "G"));

    const avatarBtn = `<button class="icon-btn" id="profile-btn" aria-label="Open your profile" title="Your profile" type="button" style="width:auto;height:auto;padding:2px">
            <span class="avatar">${avatarContent}</span>
          </button>`;

    // Theme and sign out keep their ids in both layouts, so the handlers below
    // never have to know whether they sit in the header row or behind the ⋮.
    let actions;
    if (overflow) {
      // The compact header: logo, ⋮, avatar. Everything else moves into the
      // menu — Clear chat included, which the page hands over as a callback
      // because only it knows what clearing means. That item starts hidden and
      // is revealed once there is a conversation to clear.
      actions = `
          <button class="icon-btn" id="more-btn" type="button" aria-label="More options"
                  aria-haspopup="menu" aria-expanded="false" aria-controls="more-menu">
            <span class="material-symbols-outlined" style="font-size:20px">more_vert</span>
          </button>
          ${avatarBtn}
          <div class="more-menu hidden" id="more-menu" role="menu" aria-labelledby="more-btn">
            ${showLearn ? `<a class="more-item" role="menuitem" href="learn.html">
              <span class="material-symbols-outlined" style="font-size:20px">menu_book</span><span>Learn</span></a>` : ""}
            <button class="more-item" role="menuitem" id="theme-btn" type="button">
              <span class="material-symbols-outlined" style="font-size:20px">routine</span><span>Theme</span>
            </button>
            ${onClearChat ? `<button class="more-item hidden" role="menuitem" id="more-clear" type="button">
              <span class="material-symbols-outlined" style="font-size:20px">delete_sweep</span><span>Clear chat</span>
            </button>` : ""}
            <button class="more-item" role="menuitem" id="logout-btn" type="button">
              <span class="material-symbols-outlined" style="font-size:20px">logout</span><span>Sign out</span>
            </button>
          </div>`;
    } else {
      actions = `
          ${showLearn ? `<a class="header-pill" href="learn.html">
            <span class="material-symbols-outlined" style="font-size:15px">menu_book</span><span>Learn</span></a>` : ""}
          <button class="icon-btn" id="theme-btn" aria-label="Toggle appearance theme" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">routine</span>
          </button>
          <button class="icon-btn" id="logout-btn" aria-label="Sign out of Girly" title="Sign out" type="button">
            <span class="material-symbols-outlined" style="font-size:20px">logout</span>
          </button>
          ${avatarBtn}`;
    }

    header.innerHTML = `
      <div class="app-header-inner">
        <a class="brand" href="tracker.html">
          <img class="brand-logo" src="assets/logo.svg" alt="Girly logo"/>
          <span class="brand-name">Girly</span><span aria-hidden="true" style="font-size:12px">💜</span>
        </a>
        <div class="header-actions">${actions}
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

    // The ⋮ menu opens under its button, and closes on a pick, on a tap
    // outside it, or on Escape. Closing when it is already closed costs
    // nothing, so the handlers don't check first.
    if (overflow) {
      const moreBtn = header.querySelector("#more-btn");
      const menu = header.querySelector("#more-menu");
      const closeMenu = () => {
        menu.classList.add("hidden");
        moreBtn.setAttribute("aria-expanded", "false");
      };
      moreBtn.addEventListener("click", () => {
        const opening = menu.classList.contains("hidden");
        menu.classList.toggle("hidden", !opening);
        moreBtn.setAttribute("aria-expanded", String(opening));
      });
      // Fires on the way up, so the item's own handler still runs.
      menu.addEventListener("click", closeMenu);
      document.addEventListener("click", (e) => {
        if (!header.contains(e.target)) closeMenu();
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeMenu();
      });
      if (onClearChat) header.querySelector("#more-clear").addEventListener("click", onClearChat);
    }

    this.applyTheme();
  },
};

Girly.applyTheme();
