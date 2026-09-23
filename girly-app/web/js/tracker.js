/* Girly 🌸 — tracker dashboard logic */

const MOODS = ["Happy", "Calm", "Energetic", "Tired", "Sensitive", "Irritable", "Sad", "Anxious"];
const SYMPTOMS = ["Cramps", "Backache", "Headache", "Bloating", "Tender breasts", "Acne", "Nausea", "Insomnia", "Cravings"];

let state = { data: null, monthOffset: 0, selectedFlow: "" };

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "tracker", name: me.user.name, avatar: me.user.avatar, role: me.user.role });

  buildChips();
  bindSheets();
  await loadDashboard();

  document.getElementById("btn-checkin").addEventListener("click", () =>
    openSheet("symptom-sheet")
  );
});

async function loadDashboard() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() + state.monthOffset);
  const month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;

  const data = await Girly.api(`/api/dashboard?month=${month}`);
  state.data = data;
  renderCycle(data.cycle);
  renderCalendar(data);
}

/* ---- cycle hub ---- */
function renderCycle(c) {
  const ring = document.getElementById("cycle-ring");
  const circumference = 427;
  const progress = c.has_data
    ? Math.min(c.cycle_day / c.cycle_length, 1)
    : 0.08;
  ring.style.strokeDashoffset = String(circumference * (1 - progress));

  document.getElementById("cycle-day").textContent = c.has_data ? `Day ${c.cycle_day}` : "Day —";
  document.getElementById("cycle-length").textContent = c.cycle_length;

  const pill = document.getElementById("phase-pill");
  const label = document.getElementById("phase-label");
  const pillClass = {
    menstrual: ["pill-period", "water_drop"],
    follicular: ["pill-fertile", "local_florist"],
    ovulatory: ["pill-ovulate", "star"],
    luteal: ["pill-free", "bedtime"],
    learn: ["pill-lilac", "menu_book"],
  }[c.phase] || ["pill-lilac", "spa"];
  pill.className = "pill " + pillClass[0];
  pill.firstElementChild.textContent = pillClass[1];
  label.textContent = c.phase_label;

  document.getElementById("next-period").textContent = c.has_data
    ? (c.days_until_period === 0 ? "Period Expected Today" : `Next Period in ${c.days_until_period} Day${c.days_until_period === 1 ? "" : "s"}`)
    : "Start tracking to see predictions";
  document.getElementById("phase-tip").textContent = c.tip;

  document.getElementById("stat-cycle").textContent = `${c.avg_cycle_length} Days`;
  document.getElementById("stat-cycle-hint").textContent =
    c.cycles_logged > 1 ? `${c.cycles_logged} cycles, ±${c.prediction_window}d window` : "1 cycle logged";
  document.getElementById("stat-duration").textContent = `${c.period_length} Days`;
  document.getElementById("stat-ovulation").textContent = c.has_data
    ? Girly.fmtDate(c.ovulation_date, { month: "short", day: "numeric" })
    : "Day ~14";

  // wellness tip card
  const titles = {
    menstrual: "Nourish & rest",
    follicular: "Energy is rising",
    ovulatory: "Peak glow days",
    luteal: c.days_until_period <= 4 ? "Slow & cozy era" : "Steady self-care",
    learn: "Learn at your pace",
  };
  document.getElementById("tip-title").textContent = titles[c.phase] || "Gentle reminder";
  document.getElementById("tip-body").textContent = c.tip;
}

/* ---- calendar ---- */
function renderCalendar(data) {
  const dows = ["M", "T", "W", "T", "F", "S", "S"];
  document.getElementById("cal-dow").innerHTML = dows
    .map((x) => `<span class="cal-dow">${x}</span>`).join("");

  const [y, m] = data.month.split("-").map(Number);
  document.getElementById("cal-title").textContent =
    new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });

  const daysEl = document.getElementById("cal-days");
  daysEl.innerHTML = data.calendar.map((d) => {
    if (!d.date) return `<button class="cal-day blank" type="button" tabindex="-1"></button>`;
    const classes = ["cal-day"];
    if (d.kind === "logged_period") classes.push("period");
    else if (d.kind === "ovulation") classes.push("ovulation");
    else if (d.kind === "fertile") classes.push("fertile");
    else if (d.kind === "predicted") classes.push("predicted");
    if (d.is_today) classes.push("today");

    let sub = "";
    if (d.is_today) sub = `<span class="cal-sub">Today</span>`;
    else if (d.kind === "logged_period") sub = `<span class="material-symbols-outlined filled mini-drop">water_drop</span>`;
    else if (d.kind === "ovulation") sub = `<span class="material-symbols-outlined filled mini-drop">star</span>`;
    else if (d.is_window) sub = `<span class="cal-sub" style="color:var(--primary)">±2d</span>`;

    const label = d.has_log ? ` — logged` : "";
    return `<button class="${classes.join(" ")}" type="button" data-date="${d.date}"
            aria-label="${Girly.fmtDate(d.date)}${label}" title="${Girly.fmtDate(d.date)}${label}">
            <span>${d.day}</span>${sub}</button>`;
  }).join("");

  daysEl.querySelectorAll(".cal-day:not(.blank)").forEach((btn) =>
    btn.addEventListener("click", () => dayDetail(btn.dataset.date))
  );
}

function dayDetail(date) {
  const log = (state.data.logs || []).find((l) => l.date === date);
  const bits = [];
  if (log) {
    if (log.flow) bits.push(`Flow: ${log.flow}`);
    if (log.moods?.length) bits.push(`Mood: ${log.moods.join(", ")}`);
    if (log.symptoms?.length) bits.push(`Symptoms: ${log.symptoms.join(", ")}`);
    if (log.note) bits.push(`"${log.note}"`);
  }
  Girly.toast(
    bits.length ? `${Girly.fmtDate(date)} — ${bits.join(" · ")}` : `${Girly.fmtDate(date)} — nothing logged`,
    "event"
  );
}

/* ---- sheets ---- */
function bindSheets() {
  document.querySelectorAll(".sheet-backdrop").forEach((bd) => {
    bd.addEventListener("click", (e) => {
      if (e.target === bd) bd.classList.remove("open");
    });
    bd.querySelectorAll("[data-close]").forEach((btn) =>
      btn.addEventListener("click", () => bd.classList.remove("open"))
    );
  });

  document.getElementById("btn-period-modal").addEventListener("click", () => openSheet("period-sheet"));
  document.getElementById("btn-symptom-quick").addEventListener("click", () => openSheet("symptom-sheet"));

  document.querySelectorAll("#flow-options .flow-option").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.selectedFlow = btn.dataset.flow;
      document.querySelectorAll("#flow-options .flow-option").forEach((b) =>
        b.classList.toggle("selected", b === btn)
      );
    })
  );

  document.getElementById("btn-save-flow").addEventListener("click", async () => {
    if (!state.selectedFlow) {
      Girly.toast("Pick a flow level first 💜", "info");
      return;
    }
    try {
      await Girly.api("/api/period", {
        method: "POST",
        body: JSON.stringify({ date: new Date().toISOString().slice(0, 10), flow: state.selectedFlow }),
      });
      closeSheet("period-sheet");
      Girly.toast("Period logged — predictions updated ✨", "favorite");
      await loadDashboard();
    } catch (e) { Girly.toast(e.message, "error"); }
  });

  document.getElementById("btn-save-symptoms").addEventListener("click", async () => {
    const moods = selectedChips("mood-chips");
    const symptoms = selectedChips("symptom-chips");
    const note = document.getElementById("log-note").value.trim();
    if (!moods.length && !symptoms.length && !note) {
      Girly.toast("Tap a mood or symptom first 💜", "info");
      return;
    }
    try {
      await Girly.api("/api/logs", {
        method: "POST",
        body: JSON.stringify({
          date: new Date().toISOString().slice(0, 10),
          moods, symptoms, note,
        }),
      });
      closeSheet("symptom-sheet");
      Girly.toast("Check-in saved — you're doing great 🌸", "check_circle");
      await loadDashboard();
    } catch (e) { Girly.toast(e.message, "error"); }
  });

  document.getElementById("cal-prev").addEventListener("click", () => { state.monthOffset--; loadDashboard(); });
  document.getElementById("cal-next").addEventListener("click", () => { state.monthOffset++; loadDashboard(); });
}

function openSheet(id) { document.getElementById(id).classList.add("open"); }
function closeSheet(id) { document.getElementById(id).classList.remove("open"); }

/* ---- symptom chips ---- */
function buildChips() {
  const mk = (label) =>
    `<button class="chip" type="button" data-value="${label}">
       <span>${label}</span></button>`;
  document.getElementById("mood-chips").innerHTML = MOODS.map(mk).join("");
  document.getElementById("symptom-chips").innerHTML = SYMPTOMS.map(mk).join("");

  document.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      const group = chip.closest("#mood-chips") ? "selected" : "selected-berry";
      chip.classList.toggle(group);
    })
  );
}

function selectedChips(id) {
  return Array.from(document.querySelectorAll(`#${id} .chip.selected, #${id} .chip.selected-berry`))
    .map((c) => c.dataset.value);
}
