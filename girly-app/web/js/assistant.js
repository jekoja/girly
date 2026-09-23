/* Girly 🌸 — assistant chat logic */

const TIP_ICONS = ["local_cafe", "heat", "water_drop", "self_improvement", "hotel", "bed", "directions_walk", "restaurant"];

let ctxInfo = { name: "there", cycle_day: null, phase_label: "" };

document.addEventListener("DOMContentLoaded", async () => {
  const me = await Girly.requireAuth();
  if (!me) return;
  Girly.mountChrome({ active: "assistant", name: me.user.name, avatar: me.user.avatar, role: me.user.role });

  ctxInfo.name = me.user.name.split(" ")[0];
  const c = me.cycle;
  document.getElementById("suggest-label").textContent = c.has_data
    ? `Suggested questions for Day ${c.cycle_day}`
    : "Suggested questions";

  // suggested questions live behind a toggle button that opens a sheet
  const suggestToggle = document.getElementById("suggest-toggle");
  const backdrop = document.getElementById("suggest-backdrop");
  const caret = document.getElementById("suggest-caret");

  const closeSuggestSheet = () => {
    backdrop.classList.remove("open");
    suggestToggle.setAttribute("aria-expanded", "false");
    caret.textContent = "expand_more";
  };

  suggestToggle.addEventListener("click", () => {
    const opening = !backdrop.classList.contains("open");
    backdrop.classList.toggle("open", opening);
    suggestToggle.setAttribute("aria-expanded", String(opening));
    caret.textContent = opening ? "expand_less" : "expand_more";
  });
  document.getElementById("suggest-close").addEventListener("click", closeSuggestSheet);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) closeSuggestSheet();
  });

  renderPromptChips();
  loadHistory(c);

  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");

  document.getElementById("btn-clear-chat").addEventListener("click", () => clearHistory(c));

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    stopDictation();  // else the last words land back in the box after it clears
    sendMessage(chatInput.value.trim());
  });

  // The ask bar is a textarea so a long question wraps onto the next line
  // instead of running off the edge of the field. Enter still sends, the way
  // it did when this was a single-line input; Shift+Enter now adds a line.
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });
  chatInput.addEventListener("input", () => autoGrowInput(chatInput));
  autoGrowInput(chatInput);

  // ---- attachments (photos & documents) ----
  const attachInput = document.getElementById("attachment-input");
  document.getElementById("btn-attach").addEventListener("click", () => {
    attachInput.value = "";
    attachInput.click();
  });
  attachInput.addEventListener("change", uploadSelectedFiles);

  setupDictation(chatInput);

  // arriving from the Learn page "Ask" bar?
  const prefill = new URLSearchParams(window.location.search).get("q");
  if (prefill) sendMessage(prefill);
});

// ---- dictation ----
// Speak the question, read it back in the ask bar, fix anything misheard, then
// press send. Nothing here ever submits: the transcript is a draft the user
// approves, which is the whole point of routing speech through the composer
// instead of straight into sendMessage().
let stopDictation = () => {};  // no-op until setupDictation runs

function setupDictation(input) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById("btn-mic");
  if (!SpeechRecognition) return;  // stays hidden — Firefox has no speech engine

  const icon = document.getElementById("btn-mic-icon");
  // With a speech engine available this button takes over the send button's
  // spot, so the row keeps one round control instead of two.
  document.getElementById("send-button").classList.add("hidden");

  const recog = new SpeechRecognition();
  recog.interimResults = true;   // show words as they're recognised, not after
  recog.continuous = false;      // one question per tap
  recog.lang = document.documentElement.lang || navigator.language || "en-US";

  // Text already in the box when the mic was tapped. Dictation appends to it so
  // a half-typed question isn't lost, and so each interim result replaces only
  // the dictated part.
  let base = "";
  let recording = false;

  const paint = (text) => {
    input.value = text;
    autoGrowInput(input);
    syncButton();
  };

  // Typed text, and nothing else, turns the mic into a send button. Tapping
  // into the field must not: the field is where a dictation lands, so it is the
  // first thing anyone touches on the way to the mic, and swapping the button
  // out from under them there hides the control they came for.
  const wantsSend = () => input.value.trim() !== "";

  // While dictating it is always the stop square. The transcript lands in the
  // field, which would otherwise satisfy wantsSend() and swap the stop button
  // out from under the user mid-sentence.
  function syncButton() {
    if (recording) {
      icon.textContent = "stop";
      btn.title = "Stop dictating";
      btn.setAttribute("aria-label", "Stop dictating");
      return;
    }
    const send = wantsSend();
    icon.textContent = send ? "send" : "mic";
    btn.title = send ? "Send message" : "Dictate your question";
    btn.setAttribute("aria-label", send ? "Send message" : "Dictate your question");
  }

  const setRecording = (on) => {
    recording = on;
    btn.classList.toggle("recording", on);
    btn.setAttribute("aria-pressed", String(on));
    syncButton();
  };

  recog.onresult = (e) => {
    // Rebuilt from the full result list rather than from e.resultIndex: once a
    // chunk is finalised, resultIndex advances past it, and slicing from there
    // would drop the words already spoken.
    let said = "";
    for (let i = 0; i < e.results.length; i++) said += e.results[i][0].transcript;
    said = said.trim();
    paint(base ? `${base} ${said}` : said);
  };

  recog.onerror = (e) => {
    const messages = {
      "not-allowed": "Microphone access is blocked. Allow it in your browser settings to dictate.",
      "service-not-allowed": "Microphone access is blocked. Allow it in your browser settings to dictate.",
      "no-speech": "I didn't catch anything — tap the mic and try again.",
      "audio-capture": "No microphone found on this device.",
      network: "Dictation needs a connection and couldn't reach the speech service.",
    };
    Girly.toast(messages[e.error] || "Dictation stopped unexpectedly.", "mic_off");
  };

  // Fires on natural end as well as on stop(), so this is the single place the
  // button resets — otherwise a recognition that ends on its own leaves the
  // button stuck on "stop".
  recog.onend = () => setRecording(false);

  stopDictation = () => {
    if (recording) recog.stop();
  };

  // Keep the caret in the field when the button is pressed: on a phone that
  // holds the keyboard open across a dictation, and on a desktop it leaves the
  // cursor where the next word goes once the transcript lands.
  btn.addEventListener("mousedown", (e) => e.preventDefault());

  btn.addEventListener("click", () => {
    if (recording) {
      recog.stop();
      return;
    }
    if (wantsSend()) {
      // The button only says "send" when there is text, so there is always
      // something to submit. An attached photo with no text still sends on
      // Enter, which is why the mic is free to mean dictation here.
      document.getElementById("chat-form").requestSubmit();
      return;
    }
    // Audio leaves the device for the browser's speech service (Google or
    // Apple). Said once, then not again.
    if (!localStorage.getItem("girly-dictation-notice")) {
      localStorage.setItem("girly-dictation-notice", "1");
      Girly.toast("Dictation uses your browser's speech service, so what you say is sent to it.", "privacy_tip");
    }
    base = input.value.trim();
    try {
      recog.start();
      setRecording(true);
    } catch (e) {
      // start() throws if a previous session hasn't finished tearing down yet
      setRecording(false);
    }
  });

  // Typing is the only thing that changes the button, and a dictation feeds the
  // field through paint(), so this one event covers both routes to a full box.
  input.addEventListener("input", syncButton);

  btn.classList.remove("hidden");
  syncButton();
}

// ---- attachments ----
let pendingAttachments = [];

const ATTACH_EXT_TYPES = {
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".pdf": "application/pdf",
  ".doc": "application/msword",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("could not read that file"));
    reader.readAsDataURL(file);
  });
}

async function uploadSelectedFiles() {
  const input = document.getElementById("attachment-input");
  const files = [...(input.files || [])];
  for (const file of files) {
    if (file.size > 4 * 1024 * 1024) {
      Girly.toast(`${file.name} is larger than 4 MB`, "error");
      continue;
    }
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const contentType = file.type || ATTACH_EXT_TYPES[ext] || "";
    try {
      const data = await fileToBase64(file);
      const res = await Girly.api("/api/attachments", {
        method: "POST",
        body: JSON.stringify({ name: file.name, content_type: contentType, data }),
      });
      pendingAttachments.push(res.attachment);
    } catch (e) {
      Girly.toast(e.message, "error");
    }
  }
  renderAttachmentTray();
}

function renderAttachmentTray() {
  const tray = document.getElementById("attachment-tray");
  tray.innerHTML = pendingAttachments
    .map(
      (a, i) => `
    <div class="attach-chip">
      <span class="material-symbols-outlined" style="font-size:16px">${a.type.startsWith("image/") ? "image" : "description"}</span>
      <span class="attach-name">${Girly.escapeHtml(a.name)}</span>
      <button class="icon-btn" data-remove="${i}" type="button" style="width:24px;height:24px" aria-label="Remove attachment">
        <span class="material-symbols-outlined" style="font-size:16px">close</span>
      </button>
    </div>`
    )
    .join("");
  tray.querySelectorAll("[data-remove]").forEach((btn) =>
    btn.addEventListener("click", () => {
      pendingAttachments.splice(Number(btn.dataset.remove), 1);
      renderAttachmentTray();
    })
  );
}

function attachmentHTML(attachments) {
  if (!attachments || !attachments.length) return "";
  const items = attachments
    .map((a) =>
      a.type && a.type.startsWith("image/")
        ? `<a href="${a.url}" target="_blank" rel="noopener"><img class="attach-thumb" src="${a.url}" alt="${Girly.escapeHtml(a.name)}"/></a>`
        : `<a class="attach-file" href="${a.url}" target="_blank" rel="noopener">
             <span class="material-symbols-outlined" style="font-size:18px">description</span>
             <span>${Girly.escapeHtml(a.name)}</span>
           </a>`
    )
    .join("");
  return `<div class="stack" style="gap:6px; margin-bottom:4px">${items}</div>`;
}

function renderPromptChips() {
  const chips = [
    ["🍫", "Why am I craving chocolate?"],
    ["🎒", "What should I pack in my bag?"],
    ["🌿", "Explain my fertile window"],
    ["🔮", "How does Girly predict my cycle?"],
    ["🔥", "How do I soothe cramps?"],
    ["🌙", "Why is my mood shifting?"],
  ];
  document.getElementById("prompt-chips").innerHTML = chips
    .map(([emoji, text]) =>
      `<button class="prompt-chip" type="button"><span>${emoji}</span><span>${text}</span></button>`
    ).join("");
  document.querySelectorAll(".prompt-chip").forEach((btn) =>
    btn.addEventListener("click", () => {
      // close the sheet, then send just the question text
      document.getElementById("suggest-backdrop").classList.remove("open");
      document.getElementById("suggest-toggle").setAttribute("aria-expanded", "false");
      document.getElementById("suggest-caret").textContent = "expand_more";
      sendMessage(btn.lastElementChild.textContent.trim());
    })
  );
}

function greet(c) {
  let opening = `Hi ${ctxInfo.name}! 💜 I'm your Girly companion.`;
  if (c.has_data) {
    opening += ` Since you're around <b style="color:var(--primary)">Day ${c.cycle_day}</b> of your cycle (${c.phase_label.toLowerCase()}), `;
    opening += c.phase === "menstrual"
      ? "extra rest and warmth are exactly what your body is asking for."
      : c.phase === "luteal"
        ? "you might be noticing progesterone shifts or gentle pre-period cues."
        : c.phase === "ovulatory"
          ? "you may be feeling energetic and glowing."
          : "your energy is likely on the rise.";
  } else {
    opening += " Ask me anything about periods, symptoms, or cycle basics — no question is too small.";
  }
  opening += " How are you feeling today?";
  appendBot(`<p class="t-body-md" style="margin:0">${opening}</p>`);
}

function userBubble(text, attachments, time) {
  const row = document.createElement("div");
  row.className = "bubble-row user" + (replaying ? "" : " fade-in");
  row.innerHTML = `
    <div class="bubble-col user">
      <div class="bubble user-bubble">
        ${attachmentHTML(attachments)}
        ${text ? `<p class="t-body-md" style="margin:0">${Girly.escapeHtml(text)}</p>` : ""}
      </div>
      <span class="bubble-time">${time || nowTime()}</span>
    </div>`;
  document.getElementById("chat-stream").appendChild(row);
  if (!replaying) scrollStream();
}

function appendBot(html, feedback = true, time) {
  const row = document.createElement("div");
  row.className = "bubble-row" + (replaying ? "" : " fade-in");
  row.innerHTML = `
    <div class="bot-avatar"><span class="material-symbols-outlined" style="font-size:18px">auto_awesome</span></div>
    <div class="bubble-col">
      <div class="bubble bot">${html}</div>
      ${feedback ? `<div class="row" style="justify-content:space-between; padding-inline:4px">
        <span class="bubble-time">${time || nowTime()}</span>
        <div class="row" style="gap:var(--sp-xs)">
          <button class="icon-btn" style="width:28px;height:28px;background:var(--surface-container)" aria-label="Helpful response" type="button"><span class="material-symbols-outlined" style="font-size:15px">thumb_up</span></button>
          <button class="icon-btn" style="width:28px;height:28px;background:var(--surface-container)" aria-label="Save tip" type="button"><span class="material-symbols-outlined" style="font-size:15px">bookmark_border</span></button>
        </div>
      </div>` : ""}
    </div>`;
  row.querySelectorAll(".icon-btn").forEach((btn) =>
    btn.addEventListener("click", () => Girly.toast("Thanks for the feedback 💜", "favorite"))
  );
  document.getElementById("chat-stream").appendChild(row);
  if (!replaying) scrollStream();
}

function thinkingBubble() {
  const row = document.createElement("div");
  row.className = "bubble-row";
  row.id = "bot-thinking";
  row.innerHTML = `
    <div class="bot-avatar" style="animation:pulse 1.2s infinite"><span class="material-symbols-outlined" style="font-size:18px">auto_awesome</span></div>
    <div class="bubble bot typing-dots"><span></span><span></span><span></span></div>`;
  document.getElementById("chat-stream").appendChild(row);
  scrollStream();
}

const MAX_INPUT_LINES = 5;  // keep the max-height in girly.css in step

// Grow the ask bar to fit what's been typed, then scroll inside it past
// MAX_INPUT_LINES so the dock never eats the conversation.
function autoGrowInput(el) {
  const cs = getComputedStyle(el);
  const line = parseFloat(cs.lineHeight) || 20;
  const padding = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const max = line * MAX_INPUT_LINES + padding;

  el.style.height = "auto";
  const needed = el.scrollHeight;
  el.style.height = `${Math.min(needed, max)}px`;
  el.style.overflowY = needed > max ? "auto" : "hidden";
}

// The body of a companion reply. Shared by live answers and replayed history —
// building it in two places is how the two drift apart.
function botHTML(res) {
  let html = `<p class="t-body-md" style="margin:0">${Girly.escapeHtml(res.reply || "")}</p>`;
  if (res.tips?.length) {
    html += `<div class="stack" style="gap:var(--sp-xs); padding-top:var(--sp-sm)">` +
      res.tips.map((tip, i) =>
        `<div class="care-tip"><span class="material-symbols-outlined" style="color:var(--primary); font-size:18px">${TIP_ICONS[i % TIP_ICONS.length]}</span><span>${Girly.escapeHtml(tip)}</span></div>`
      ).join("") + `</div>`;
  }
  if (res.doctor) {
    html += `<div class="doctor-note" style="margin-top:var(--sp-sm)">
      <span class="material-symbols-outlined filled" style="color:var(--primary); font-size:18px; flex-shrink:0">info</span>
      <span><b style="color:var(--primary)">Friendly reminder:</b> if symptoms ever become sharp, unmanageable, or disrupt your movement, please reach out to your doctor or gynecologist.</span>
    </div>`;
  }
  return html;
}

async function sendMessage(query) {
  const input = document.getElementById("chat-input");
  const attachments = pendingAttachments.splice(0);
  renderAttachmentTray();
  if (!query && !attachments.length) return;
  const message = query || "Sent an attachment";
  input.value = "";
  autoGrowInput(input);
  userBubble(query, attachments);
  thinkingBubble();

  try {
    const res = await Girly.api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        attachments: attachments.map(({ name, url, type }) => ({ name, url, type })),
      }),
    });
    document.getElementById("bot-thinking")?.remove();
    appendBot(botHTML(res));
    setHasHistory(true);
  } catch (e) {
    document.getElementById("bot-thinking")?.remove();
    appendBot(`<p class="t-body-md" style="margin:0; color:var(--error)">${Girly.escapeHtml(e.message)}</p>`, false);
  }
}

// ---- saved conversation ----
// Replaying a long transcript should not fade and smooth-scroll once per bubble,
// so both bubble builders check this and scroll once at the end instead.
let replaying = false;

// The clear button only makes sense when there is something to clear.
function setHasHistory(on) {
  document.getElementById("btn-clear-chat").classList.toggle("hidden", !on);
}

// Restore what was said before. Falls back to the greeting when there is
// nothing saved — and also when the request fails, so a broken fetch never
// leaves the user staring at an empty chat.
async function loadHistory(c) {
  let turns = [];
  try {
    const res = await Girly.api("/api/chat/history");
    turns = res.turns || [];
  } catch (e) {
    greet(c);
    return;
  }
  if (!turns.length) {
    greet(c);
    return;
  }

  replaying = true;
  turns.forEach((t) => {
    const time = nowTime(t.time);
    userBubble(t.question, t.attachments, time);
    if (t.reply) appendBot(botHTML(t), true, time);
  });
  replaying = false;
  scrollStream();
  setHasHistory(true);
}

async function clearHistory(c) {
  if (!confirm("Clear your conversation with the companion? This can't be undone.")) return;
  try {
    await Girly.api("/api/chat/clear", { method: "POST" });
  } catch (e) {
    Girly.toast(e.message, "error");
    return;
  }
  document.getElementById("chat-stream").innerHTML = "";
  setHasHistory(false);
  greet(c);
  Girly.toast("Conversation cleared", "delete_sweep");
}

// Formats a stored ISO timestamp, or the current time when given nothing.
function nowTime(iso) {
  const when = iso ? new Date(iso) : new Date();
  if (isNaN(when)) return "";
  return when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function scrollStream() {
  requestAnimationFrame(() =>
    document.getElementById("chat-stream").lastElementChild
      ?.scrollIntoView({ behavior: "smooth", block: "end" })
  );
}
