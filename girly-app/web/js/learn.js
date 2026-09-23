/* Girly 🌸 — learn mode logic */

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "learn", name: me.user.name, avatar: me.user.avatar, role: me.user.role });

  // "My period has started" → switch to tracking mode
  document.getElementById("btn-period-arrived").addEventListener("click", async () => {
    const feedback = document.getElementById("celebration-feedback");
    feedback.classList.remove("hidden");
    try {
      await Girly.api("/api/mode", {
        method: "POST",
        body: JSON.stringify({ mode: "tracking", last_period_date: new Date().toISOString().slice(0, 10) }),
      });
      setTimeout(() => (window.location.href = "tracker.html"), 1200);
    } catch (e) {
      feedback.classList.add("hidden");
      Girly.toast(e.message, "error");
    }
  });

  // Ask bar → jump to the assistant with the question prefilled
  const ask = () => {
    const q = document.getElementById("learn-ask").value.trim();
    if (!q) {
      Girly.toast("Type a question first 💜", "info");
      return;
    }
    window.location.href = "assistant.html?q=" + encodeURIComponent(q);
  };
  document.getElementById("learn-ask-btn").addEventListener("click", ask);
  document.getElementById("learn-ask").addEventListener("keydown", (e) => {
    if (e.key === "Enter") ask();
  });

  // checklist persistence (localStorage — tiny & private)
  document.querySelectorAll(".kit-item").forEach((cb, i) => {
    const key = "girly-kit-" + i;
    cb.checked = localStorage.getItem(key) === "1";
    cb.addEventListener("change", () => localStorage.setItem(key, cb.checked ? "1" : "0"));
  });
});
