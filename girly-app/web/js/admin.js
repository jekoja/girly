/* Girly 🌸 — admin console logic */

let users = [];
let currentFilter = "all";
let resetEmail = "";
let deleteTarget = { name: "", email: "" };

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;

  if (me.user.role !== "admin") {
    Girly.toast("Admin access required — signing you out", "shield");
    setTimeout(() => (window.location.href = "tracker.html"), 1200);
    return;
  }

  document.getElementById("admin-email").textContent = me.user.email;
  Girly.mountChrome({ active: "admin", name: me.user.name, avatar: me.user.avatar, showLearn: false, role: me.user.role });

  document.getElementById("admin-theme").addEventListener("click", () => {
    Girly.toast(Girly.toggleTheme() ? "Dark mode enabled" : "Light mode restored", "dark_mode");
  });
  document.getElementById("admin-refresh").addEventListener("click", () => {
    loadAll();
    Girly.toast("Metrics reloaded", "refresh");
  });
  document.getElementById("confirm-reset").addEventListener("click", doReset);
  document.getElementById("confirm-delete").addEventListener("click", doDelete);
  document.getElementById("copy-cli").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById("cli-snippet").textContent);
      Girly.toast("CLI command copied to clipboard", "content_copy");
    } catch { Girly.toast("Clipboard unavailable", "error"); }
  });
  document.getElementById("export-telemetry").addEventListener("click", exportTelemetry);

  document.querySelectorAll(".modal-backdrop").forEach((bd) =>
    bd.addEventListener("click", (e) => { if (e.target === bd) bd.classList.remove("open"); })
  );

  document.getElementById("user-search").addEventListener("input", renderUsers);
  document.querySelectorAll(".filter-btn").forEach((btn) =>
    btn.addEventListener("click", () => {
      currentFilter = btn.dataset.filter;
      document.querySelectorAll(".filter-btn").forEach((b) =>
        b.style.setProperty("background", b === btn ? "var(--secondary)" : "var(--surface-container)")
      );
      renderUsers();
    })
  );

  await loadAll();
});

async function loadAll() {
  await Promise.all([loadStats(), loadUsers(), loadAudit()]);
}

async function loadStats() {
  const stats = await Girly.api("/api/admin/stats");
  document.getElementById("stat-registered").textContent = stats.registered.toLocaleString();
  document.getElementById("stat-sessions").textContent = stats.active_sessions.toLocaleString();
  document.getElementById("stat-learn").textContent = stats.learn_mode.toLocaleString();
  document.getElementById("stat-tracking").textContent = stats.tracking_mode.toLocaleString();
  const total = Math.max(stats.registered, 1);
  document.getElementById("stat-learn-pct").textContent =
    ((stats.learn_mode / total) * 100).toFixed(1) + "% of member base";
  document.getElementById("stat-tracking-pct").textContent =
    ((stats.tracking_mode / total) * 100).toFixed(1) + "% logging rhythms";

  const okCount = stats.services.filter((s) => s.status === "running").length;
  const badge = document.getElementById("health-badge");
  badge.textContent = `${okCount}/${stats.services.length} Healthy`;
  badge.className = "pill " + (okCount === stats.services.length ? "pill-ok" : "pill-period");

  document.getElementById("services-list").innerHTML = stats.services
    .map((svc) => `
      <div class="row-between card-flat" style="padding:10px">
        <div class="row" style="gap:10px; min-width:0">
          <span class="dot" style="background:${svc.status === "running" ? "var(--ok)" : "var(--error)"}; flex-shrink:0"></span>
          <div style="min-width:0">
            <span class="t-label-md" style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${svc.name}</span>
            <span class="t-body-sm muted">${svc.detail}</span>
          </div>
        </div>
        <span class="pill ${svc.status === "running" ? "pill-ok" : "pill-period"}">${svc.status}</span>
      </div>`)
    .join("");
}

async function loadUsers() {
  const data = await Girly.api("/api/admin/users");
  users = data.users || [];
  renderUsers();
}

function renderUsers() {
  const q = document.getElementById("user-search").value.toLowerCase().trim();
  const list = document.getElementById("user-list");
  const noResults = document.getElementById("no-user-results");

  const matches = users.filter((u) => {
    const bySearch = !q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
    const byFilter =
      currentFilter === "all" ||
      (currentFilter === "active" && u.active) ||
      (currentFilter === "tracking" && u.mode === "tracking") ||
      (currentFilter === "learn" && u.mode === "learn");
    return bySearch && byFilter;
  });

  document.getElementById("user-count-badge").textContent =
    `${matches.length} Account${matches.length === 1 ? "" : "s"}`;

  list.innerHTML = matches.map((u) => `
    <div class="card stack gap-sm" data-email="${Girly.escapeHtml(u.email)}">
      <div class="row" style="align-items:flex-start; gap:10px">
        <div class="avatar" style="width:36px;height:36px">${Girly.escapeHtml(Girly.initials(u.name))}</div>
        <div style="min-width:0">
          <div class="row" style="gap:6px">
            <span class="t-headline-sm" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${Girly.escapeHtml(u.name)}</span>
            ${u.role === "admin" ? `<span class="pill pill-plum">Root Ops</span>` : ""}
            ${u.active
              ? `<span class="pill pill-ok"><span class="dot dot-ok" style="width:6px;height:6px"></span>Active</span>`
              : `<span class="pill pill-neutral">Idle</span>`}
          </div>
          <p class="t-body-sm muted" style="margin:0">${Girly.escapeHtml(u.email)}</p>
          <div class="row" style="gap:8px; margin-top:4px">
            <span class="pill ${u.mode === "learn" ? "pill-lilac" : "pill-period"}">${u.mode === "learn" ? "Learn Mode" : "Tracking Mode"}</span>
            <span class="t-body-sm" style="color:var(--outline)">• ${Girly.fmtDate(u.created_at)}</span>
          </div>
        </div>
      </div>
      <div class="grid-3" style="gap:6px; padding-top:4px">
        <button class="btn btn-ghost user-action" style="min-height:34px; font-size:12px" data-action="reset" data-email="${Girly.escapeHtml(u.email)}" data-name="${Girly.escapeHtml(u.name)}">
          <span class="material-symbols-outlined" style="font-size:16px">lock_reset</span>Reset
        </button>
        <button class="btn btn-ghost user-action" style="min-height:34px; font-size:12px" data-action="revoke" data-email="${Girly.escapeHtml(u.email)}">
          <span class="material-symbols-outlined" style="font-size:16px">logout</span>Revoke
        </button>
        <button class="btn btn-danger-soft user-action" style="min-height:34px; font-size:12px" data-action="delete" data-email="${Girly.escapeHtml(u.email)}" data-name="${Girly.escapeHtml(u.name)}">
          <span class="material-symbols-outlined" style="font-size:16px">delete</span>Delete
        </button>
      </div>
    </div>`).join("");

  // delegate actions (safe against names/emails containing quotes)
  list.querySelectorAll(".user-action").forEach((btn) =>
    btn.addEventListener("click", () => {
      const { action, email, name } = btn.dataset;
      if (action === "reset") openReset(email);
      else if (action === "revoke") doRevoke(email);
      else if (action === "delete") openDelete(name, email);
    })
  );

  noResults.classList.toggle("hidden", matches.length > 0);
}

async function loadAudit() {
  const data = await Girly.api("/api/admin/audit");
  document.getElementById("audit-list").innerHTML = (data.audit || []).slice(0, 30).map((e) => `
    <div class="row card-flat" style="gap:8px; padding:8px 10px; align-items:flex-start">
      <span class="material-symbols-outlined" style="font-size:15px; color:var(--tertiary); flex-shrink:0">history</span>
      <div style="min-width:0">
        <span class="t-label-sm" style="display:block"><b>${Girly.escapeHtml(e.actor)}</b> · ${Girly.escapeHtml(e.action)}</span>
        <span class="t-body-sm muted">${Girly.escapeHtml(e.detail)}</span>
        <span class="t-label-sm" style="color:var(--outline); display:block; margin-top:1px">${new Date(e.time).toLocaleString()}</span>
      </div>
    </div>`).join("");
}

/* ---- actions ---- */
function openModal(id) { document.getElementById(id).classList.add("open"); }
function closeModal(id) { document.getElementById(id).classList.remove("open"); }
window.closeModal = closeModal;

function openReset(email) {
  resetEmail = email;
  document.getElementById("reset-target-email").value = email;
  openModal("reset-modal");
}
window.openReset = openReset;

async function doReset() {
  try {
    const res = await Girly.api("/api/admin/users/reset", {
      method: "POST",
      body: JSON.stringify({ email: resetEmail }),
    });
    closeModal("reset-modal");
    Girly.toast(`Temp password for ${resetEmail}: ${res.temp_password}`, "key");
    loadAll();
  } catch (e) { Girly.toast(e.message, "error"); }
}

async function doRevoke(email) {
  try {
    await Girly.api("/api/admin/users/revoke", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    Girly.toast(`Revoked all active sessions for ${email}`, "logout");
    loadAll();
  } catch (e) { Girly.toast(e.message, "error"); }
}
window.doRevoke = doRevoke;

function openDelete(name, email) {
  deleteTarget = { name, email };
  document.getElementById("delete-target").textContent = `${name} (${email})`;
  openModal("delete-modal");
}
window.openDelete = openDelete;

async function doDelete() {
  try {
    await Girly.api("/api/admin/users/delete", {
      method: "POST",
      body: JSON.stringify({ email: deleteTarget.email }),
    });
    closeModal("delete-modal");
    Girly.toast(`Account for ${deleteTarget.name} deleted`, "delete_forever");
    loadAll();
  } catch (e) { Girly.toast(e.message, "error"); }
}

async function exportTelemetry() {
  try {
    const data = await Girly.api("/api/admin/telemetry");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `girly_anonymous_telemetry_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    Girly.toast("Anonymous counts exported", "download");
  } catch (e) { Girly.toast(e.message, "error"); }
}
