/* Girly 🌸 — profile page: picture, password change, sign out */

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "profile", name: me.user.name, avatar: me.user.avatar, role: me.user.role });

  const user = me.user;

  // ---- render profile ----
  function renderAvatar() {
    const img = document.getElementById("avatar-img");
    const initials = document.getElementById("avatar-initials");
    // Nothing to remove until a picture is set — the avatar itself is the
    // control for adding or changing one, so its label follows suit.
    document.getElementById("btn-remove-photo").classList.toggle("hidden", !user.avatar);
    document.getElementById("profile-avatar").setAttribute(
      "aria-label", user.avatar ? "Change profile picture" : "Add a profile picture");
    document.getElementById("avatar-edit-icon").textContent =
      user.avatar ? "photo_camera" : "add_a_photo";
    if (user.avatar) {
      img.src = user.avatar;
      img.classList.remove("hidden");
      initials.classList.add("hidden");
    } else {
      img.classList.add("hidden");
      initials.classList.remove("hidden");
      initials.textContent = Girly.initials(user.name || "G");
    }
  }
  renderAvatar();

  // ---- render cover photo ----
  // Mirrors renderAvatar: the banner holds the picture or the invitation to add
  // one, and the badge follows whichever state it is in.
  //
  // The strip's shape is the picture's shape, so the whole photo fits and
  // nothing is cropped to a band through the middle. Only a shape at the far
  // ends of the range is clamped — a portrait would otherwise stand the banner
  // as tall as it is wide, and a panorama would flatten it to a hairline.
  const COVER_RATIO_MIN = 1.5;
  const COVER_RATIO_MAX = 4;

  function renderCover() {
    const strip = document.getElementById("cover");
    const img = document.getElementById("cover-img");
    const empty = document.getElementById("cover-empty");
    // Nothing to remove until there is a banner to remove.
    document.getElementById("btn-remove-cover").classList.toggle("hidden", !user.cover);
    strip.setAttribute(
      "aria-label", user.cover ? "Change cover photo" : "Add a cover photo");
    document.getElementById("cover-edit-icon").textContent =
      user.cover ? "photo_camera" : "add_a_photo";
    if (user.cover) {
      // Measured once the image has decoded — naturalWidth is 0 before that.
      img.onload = () => {
        const ratio = img.naturalWidth / img.naturalHeight;
        if (!isFinite(ratio) || ratio <= 0) return;
        strip.style.aspectRatio = String(
          Math.min(COVER_RATIO_MAX, Math.max(COVER_RATIO_MIN, ratio)));
      };
      img.src = user.cover;
      img.classList.remove("hidden");
      empty.classList.add("hidden");
    } else {
      img.onload = null;
      img.removeAttribute("src");
      img.classList.add("hidden");
      empty.classList.remove("hidden");
      strip.style.aspectRatio = "";  // back to the 3:1 empty state
    }
  }
  renderCover();

  document.getElementById("profile-name").textContent = user.name;
  document.getElementById("profile-email").textContent = user.email;
  document.getElementById("profile-mode").lastElementChild.textContent =
    user.mode === "tracking" ? "Tracking Mode" : "Learn Mode";
  document.getElementById("profile-since").textContent = user.created_at
    ? `Member since ${Girly.fmtDate(user.created_at)}`
    : "";

  // ---- change picture ----
  // Client-side resize keeps uploads tiny: the picture is squashed to a
  // 256px JPEG before it ever leaves the browser. The banner is a different
  // shape, so it gets its own, larger cap — a 3:1 source lands at 1024×341,
  // comfortably inside the server's 512 KiB ceiling at this quality.
  const COVER_MAX_SIDE = 1024;

  function resizeImage(file, max = 256) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("could not read that image — try a PNG or JPEG"));
      };
      img.src = url;
    });
  }

  const fileInput = document.getElementById("avatar-input");
  async function pickPicture() {
    fileInput.value = "";
    fileInput.click();
  }
  document.getElementById("profile-avatar").addEventListener("click", pickPicture);
  document.getElementById("profile-avatar").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickPicture(); }
  });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    try {
      const avatar = await resizeImage(file);
      const res = await Girly.api("/api/profile/avatar", {
        method: "POST",
        body: JSON.stringify({ avatar }),
      });
      user.avatar = res.avatar;
      renderAvatar();
      Girly.mountChrome({ active: "profile", name: user.name, avatar: user.avatar, role: user.role });
      Girly.toast("Profile picture updated 💜", "favorite");
    } catch (e) {
      Girly.toast(e.message, "error");
    }
  });

  document.getElementById("btn-remove-photo").addEventListener("click", async () => {
    try {
      await Girly.api("/api/profile/avatar", {
        method: "POST",
        body: JSON.stringify({ avatar: "" }),
      });
      user.avatar = "";
      renderAvatar();
      Girly.mountChrome({ active: "profile", name: user.name, avatar: "", role: user.role });
      Girly.toast("Profile picture removed");
    } catch (e) {
      Girly.toast(e.message, "error");
    }
  });

  // ---- change cover photo ----
  // The same shape as the avatar: one hidden file input, the strip as the
  // control, and a quiet button that only exists once there is something to
  // remove. A banner change does not touch the header, so unlike the avatar it
  // has no chrome to re-mount.
  const coverInput = document.getElementById("cover-input");
  function pickCover() {
    coverInput.value = "";
    coverInput.click();
  }
  document.getElementById("cover").addEventListener("click", pickCover);
  document.getElementById("cover").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickCover(); }
  });

  coverInput.addEventListener("change", async () => {
    const file = coverInput.files && coverInput.files[0];
    if (!file) return;
    try {
      const cover = await resizeImage(file, COVER_MAX_SIDE);
      const res = await Girly.api("/api/profile/cover", {
        method: "POST",
        body: JSON.stringify({ cover }),
      });
      user.cover = res.cover;
      renderCover();
      Girly.toast("Cover photo updated 💜", "favorite");
    } catch (e) {
      Girly.toast(e.message, "error");
    }
  });

  document.getElementById("btn-remove-cover").addEventListener("click", async () => {
    try {
      await Girly.api("/api/profile/cover", {
        method: "POST",
        body: JSON.stringify({ cover: "" }),
      });
      user.cover = "";
      renderCover();
      Girly.toast("Cover photo removed");
    } catch (e) {
      Girly.toast(e.message, "error");
    }
  });

  // ---- password visibility toggles ----
  function bindToggle(inputId, toggleId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    document.getElementById(toggleId).addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      icon.textContent = show ? "visibility_off" : "visibility";
    });
  }
  bindToggle("current-password", "toggle-current-password", "current-eye-icon");
  bindToggle("new-password", "toggle-new-password", "new-eye-icon");

  // ---- change password ----
  document.getElementById("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("password-error");
    errEl.textContent = "";
    const current = document.getElementById("current-password").value;
    const next = document.getElementById("new-password").value;
    const confirm = document.getElementById("confirm-password").value;

    if (next.length < 8) {
      errEl.textContent = "The new password must be at least 8 characters.";
      return;
    }
    const policyErr = Girly.passwordError(next);
    if (policyErr) {
      errEl.textContent = policyErr;
      return;
    }
    if (next !== confirm) {
      errEl.textContent = "The new passwords don't match.";
      return;
    }

    const btn = document.getElementById("btn-save-password");
    btn.disabled = true;
    try {
      await Girly.api("/api/profile/password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      document.getElementById("password-form").reset();
      Girly.toast("Password updated 💜", "check_circle");
    } catch (err) {
      errEl.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });
});
