/* Girly 🌸 — registration & sign-in page logic */

(function () {
  // If already signed in, hop straight into the app.
  fetch("/api/me", { credentials: "same-origin" })
    .then((r) => (r.ok ? (window.location.href = "tracker.html") : null))
    .catch(() => {});

  // ---- toggle between register / sign-in ----
  const registerForm = document.getElementById("register-form");
  const signinForm = document.getElementById("signin-form");
  const formTitle = document.getElementById("form-title");

  document.getElementById("show-signin").addEventListener("click", () => {
    registerForm.classList.add("hidden");
    signinForm.classList.remove("hidden");
    formTitle.textContent = "Welcome Back";
    signinForm.classList.add("fade-in");
  });
  document.getElementById("show-register").addEventListener("click", () => {
    signinForm.classList.add("hidden");
    registerForm.classList.remove("hidden");
    formTitle.textContent = "Create Your Private Account";
    registerForm.classList.add("fade-in");
  });

  // ---- password visibility ----
  function bindPasswordToggle(inputId, toggleId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    document.getElementById(toggleId).addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      icon.textContent = show ? "visibility_off" : "visibility";
    });
  }
  bindPasswordToggle("password", "toggle-password", "eye-icon");
  bindPasswordToggle("signin-password", "toggle-signin-password", "signin-eye-icon");

  // ---- period started? expand sub-questions ----
  const subContainer = document.getElementById("cycle-questions");
  function handlePeriodSelection() {
    const started = document.getElementById("status-started").checked;
    subContainer.classList.toggle("hidden", !started);
  }
  document.querySelectorAll('input[name="period_status"]').forEach((el) =>
    el.addEventListener("change", handlePeriodSelection)
  );
  handlePeriodSelection();

  // default last period date → today
  const lastPeriodInput = document.getElementById("lastPeriodDate");
  lastPeriodInput.value = new Date().toISOString().slice(0, 10);

  // ---- period length slider + quick pills ----
  const slider = document.getElementById("periodLengthInput");
  const lengthValue = document.getElementById("periodLengthValue");
  const pills = document.querySelectorAll(".period-day-btn");

  function updateLength(val) {
    lengthValue.textContent = val + " Days";
    pills.forEach((btn) => {
      const on = btn.getAttribute("data-days") === String(val);
      btn.classList.toggle("pill-blush", on);
      btn.classList.toggle("pill-neutral", !on);
    });
  }
  slider.addEventListener("input", () => updateLength(slider.value));
  pills.forEach((btn) =>
    btn.addEventListener("click", () => {
      slider.value = btn.getAttribute("data-days");
      updateLength(slider.value);
    })
  );

  // ---- register ----
  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("form-error");
    errEl.textContent = "";
    const btn = document.getElementById("submitBtn");
    btn.disabled = true;

    try {
      const password = document.getElementById("password").value;
      if (password.length < 8) {
        errEl.textContent = "Your password must be at least 8 characters.";
        btn.disabled = false;
        return;
      }
      const policyErr = Girly.passwordError(password);
      if (policyErr) {
        errEl.textContent = policyErr;
        btn.disabled = false;
        return;
      }
      const res = await Girly.api("/api/register", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("fullName").value.trim(),
          email: document.getElementById("email").value.trim(),
          password: password,
          dob: document.getElementById("dob").value,
          bio_sex: document.querySelector('input[name="bio_sex"]:checked').value,
          period_status: document.querySelector('input[name="period_status"]:checked').value,
          last_period_date: lastPeriodInput.value,
          period_length: parseInt(slider.value, 10),
        }),
      });
      window.location.href = res.mode === "learn" ? "learn.html" : "tracker.html";
    } catch (err) {
      errEl.textContent = err.message;
      btn.disabled = false;
    }
  });

  // ---- sign in ----
  signinForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("signin-error");
    errEl.textContent = "";
    try {
      const me = await Girly.api("/api/login", {
        method: "POST",
        body: JSON.stringify({
          email: document.getElementById("signin-email").value.trim(),
          password: document.getElementById("signin-password").value,
        }),
      });
      window.location.href = me.role === "admin" ? "admin.html" : "tracker.html";
    } catch (err) {
      errEl.textContent = err.message;
    }
  });
})();
