// Al-Noor HR Assistant chat page. Talks to the same server: GET /health, POST /ask.
"use strict";

const I18N = {
  en: {
    title: "HR Assistant",
    company: "Al-Noor Trading Co.",
    emptyTitle: "How can HR help today?",
    emptyText: "Answers come only from company policies, and every answer names the policy it came from. Ask in Arabic or English.",
    placeholder: "Type your question…",
    send: "Ask",
    newChat: "New chat",
    copy: "Copy",
    copied: "Copied",
    quoteLabel: "Exact text from the policy",
    quoteUnverified: "Related section of the policy",
    disclaimer: "Answers are for guidance. Confirm important decisions with HR.",
    errNetwork: "The assistant didn't respond. Check your connection and ask again.",
    errLimit: "That's many questions in one minute. Wait a moment, then ask again.",
    errServer: "The assistant is unavailable right now. Ask again in a minute.",
    signInTitle: "Sign in",
    signInHelp: "Use the work email and password your HR team gave you.",
    email: "Work email",
    password: "Password",
    signIn: "Sign in",
    forgot: "Forgot password?",
    resetSent: "If this email has an account, a reset link is on its way. Check your inbox.",
    needEmail: "Enter your work email first, then select Forgot password.",
    errWrong: "Email or password is incorrect. Check them and try again.",
    errMany: "Too many attempts. Wait a few minutes, then try again.",
    errDisabled: "This account is turned off. Contact HR.",
    errSignIn: "Sign-in didn't work. Check your connection and try again.",
    sessionExpired: "Your session ended. Sign in again to continue.",
    signOut: "Sign out",
    roleAdmin: "HR admin",
    documents: "Documents",
    switchTo: "العربية",
    themeToDark: "Switch to dark mode",
    themeToLight: "Switch to light mode",
  },
  ar: {
    title: "مساعد الموارد البشرية",
    company: "شركة النور التجارية",
    emptyTitle: "كيف يمكن للموارد البشرية مساعدتك اليوم؟",
    emptyText: "الإجابات من سياسات الشركة فقط، ومع كل إجابة اسم السياسة التي جاءت منها. اسأل بالعربية أو بالإنجليزية.",
    placeholder: "اكتب سؤالك هنا…",
    send: "اسأل",
    newChat: "محادثة جديدة",
    copy: "نسخ",
    copied: "تم النسخ",
    quoteLabel: "النص كما ورد في السياسة",
    quoteUnverified: "الجزء المرتبط من السياسة",
    disclaimer: "الإجابات للاسترشاد. يرجى التأكد من القرارات المهمة مع الموارد البشرية.",
    errNetwork: "لم يصل رد من المساعد. تحقق من الاتصال ثم اسأل مرة أخرى.",
    errLimit: "أسئلة كثيرة خلال دقيقة واحدة. انتظر قليلاً ثم اسأل مرة أخرى.",
    errServer: "المساعد غير متاح الآن. اسأل مرة أخرى بعد دقيقة.",
    signInTitle: "تسجيل الدخول",
    signInHelp: "استخدم بريد العمل وكلمة المرور التي أرسلها لك فريق الموارد البشرية.",
    email: "بريد العمل",
    password: "كلمة المرور",
    signIn: "دخول",
    forgot: "نسيت كلمة المرور؟",
    resetSent: "إذا كان لهذا البريد حساب، فقد أرسلنا رابط إعادة التعيين. تحقق من بريدك.",
    needEmail: "اكتب بريد العمل أولاً، ثم اختر نسيت كلمة المرور.",
    errWrong: "البريد أو كلمة المرور غير صحيحة. تحقق منهما وحاول مرة أخرى.",
    errMany: "محاولات كثيرة. انتظر بضع دقائق ثم حاول مرة أخرى.",
    errDisabled: "هذا الحساب موقوف. تواصل مع الموارد البشرية.",
    errSignIn: "لم يتم تسجيل الدخول. تحقق من الاتصال وحاول مرة أخرى.",
    sessionExpired: "انتهت الجلسة. سجّل الدخول مرة أخرى للمتابعة.",
    signOut: "تسجيل الخروج",
    roleAdmin: "مسؤول الموارد البشرية",
    documents: "المستندات",
    switchTo: "English",
    themeToDark: "التبديل إلى الوضع الداكن",
    themeToLight: "التبديل إلى الوضع الفاتح",
  },
};

// Starter topics: mixed languages on purpose, to show both work.
const TOPICS = [
  { icon: "calendar", en: "Leave", ar: "الإجازات", q: "How many days of annual leave do I get?" },
  { icon: "clock", en: "Attendance", ar: "الدوام", q: "متى أعتبر متأخراً؟" },
  { icon: "plane", en: "Travel", ar: "السفر", q: "What is the hotel limit in Jeddah?" },
  { icon: "crescent", en: "Ramadan", ar: "رمضان", q: "ما هي ساعات العمل في رمضان؟" },
];

const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  getSession(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
  setSession(k, v) { try { v ? sessionStorage.setItem(k, v) : sessionStorage.removeItem(k); } catch { /* ignore */ } },
};

let lang = store.get("lang") || ((navigator.language || "").startsWith("ar") ? "ar" : "en");
let authDisabled = false;     // local development only
let fbAuth = null;            // Firebase Auth instance, once loaded
let fb = {};                  // Firebase Auth functions
let role = "employee";
let busy = false;
const t = (key) => I18N[lang][key];

function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

/* ---------- Theme ---------- */
function currentTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function paintThemeButton() {
  const dark = currentTheme() === "dark";
  const btn = $("theme");
  btn.replaceChildren(icon(dark ? "sun" : "moon"));
  btn.setAttribute("aria-label", t(dark ? "themeToLight" : "themeToDark"));
  btn.title = t(dark ? "themeToLight" : "themeToDark");
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0B1412" : "#F3F5F4";
}
$("theme").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store.set("theme", next);
  paintThemeButton();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paintThemeButton);

/* ---------- Language ---------- */
function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $("q").placeholder = t("placeholder");
  $("lang").textContent = t("switchTo");
  $("lang").setAttribute("lang", lang === "ar" ? "en" : "ar");
  $("new-chat").title = t("newChat");
  document.querySelectorAll(".copy .label").forEach((el) => { el.textContent = t("copy"); });
  document.querySelectorAll(".chip-title").forEach((el) => { el.textContent = el.dataset[lang]; });
  document.querySelectorAll(".excerpt figcaption").forEach((el) => {
    const verified = el.dataset.key === "quoteLabel";
    el.replaceChildren(...(verified ? [icon("check")] : []), document.createTextNode(t(el.dataset.key)));
  });
  document.title = `${t("title")} · ${t("company")}`;
  $("role-badge").textContent = t("roleAdmin");
  const notice = $("signin-notice");
  if (notice && notice.dataset.key && !notice.hidden) notice.textContent = t(notice.dataset.key);
  $("sign-out").title = t("signOut");
  $("sign-out").setAttribute("aria-label", t("signOut"));
  renderTopics();
  paintThemeButton();
}
$("lang").addEventListener("click", () => {
  lang = lang === "ar" ? "en" : "ar";
  store.set("lang", lang);
  applyLang();
});

function renderTopics() {
  const box = $("topics");
  box.replaceChildren();
  TOPICS.forEach((topic) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "topic";
    const head = document.createElement("span");
    head.className = "head";
    head.append(icon(topic.icon), document.createTextNode(topic[lang]));
    const q = document.createElement("span");
    q.className = "q";
    q.dir = "auto";
    q.textContent = topic.q;
    b.append(head, q);
    b.addEventListener("click", () => send(topic.q));
    box.appendChild(b);
  });
}

/* ---------- Messages ---------- */
// "EN-01_Annual_Leave_Policy" -> "Annual Leave Policy"
const prettySource = (name) => name.replace(/^(CONF-)?(EN|AR)-\d+_/, "").replace(/_/g, " ");

function scrollDown() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function addUser(text) {
  const li = document.createElement("li");
  li.className = "msg-user appear";
  li.dir = "auto";
  li.textContent = text;
  $("messages").appendChild(li);
}

function addBot() {
  const li = document.createElement("li");
  li.className = "msg-bot appear";
  const avatar = document.createElement("span");
  avatar.className = "mark avatar";
  avatar.appendChild(icon("lamp"));
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const typing = document.createElement("span");
  typing.className = "typing";
  typing.setAttribute("aria-label", "…");
  typing.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
  bubble.appendChild(typing);
  li.append(avatar, bubble);
  $("messages").appendChild(li);
  scrollDown();
  return li;
}

function setText(li, text) {
  const bubble = li.querySelector(".bubble");
  bubble.replaceChildren();
  const p = document.createElement("p");
  p.className = "text";
  p.dir = "auto";
  p.textContent = text;              // model output is never treated as HTML
  bubble.appendChild(p);
  return bubble;
}

function fillBot(li, data) {
  const bubble = setText(li, data.answer);
  li.classList.add(data.grounded ? "lit" : "deferred");

  if (data.sources && data.sources.length) {
    const box = document.createElement("div");
    box.className = "sources";
    data.sources.forEach((s) => {
      const det = document.createElement("details");
      det.className = "chip";
      const sum = document.createElement("summary");
      const title = (lang === "ar" ? s.title_ar : s.title_en) || prettySource(s.title);
      const label = document.createElement("span");
      label.className = "chip-title";
      label.dataset.en = s.title_en || prettySource(s.title);
      label.dataset.ar = s.title_ar || prettySource(s.title);
      label.textContent = title;
      sum.append(icon("doc"), label);
      const ex = document.createElement("figure");
      ex.className = "excerpt" + (s.verified ? " verified" : "");
      const cap = document.createElement("figcaption");
      cap.dataset.key = s.verified ? "quoteLabel" : "quoteUnverified";
      cap.replaceChildren(...(s.verified ? [icon("check")] : []), document.createTextNode(t(cap.dataset.key)));
      const quote = document.createElement("blockquote");
      quote.dir = "auto";
      quote.textContent = s.snippet;
      ex.append(cap, quote);
      det.append(sum, ex);
      box.appendChild(det);
    });
    bubble.appendChild(box);
  }

  if (data.grounded) {
    const actions = document.createElement("div");
    actions.className = "actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "copy";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = t("copy");
    copy.append(icon("copy"), label);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(data.answer);
        copy.replaceChildren(icon("check"), Object.assign(document.createElement("span"), { className: "label", textContent: t("copied") }));
        setTimeout(() => { copy.replaceChildren(icon("copy"), Object.assign(document.createElement("span"), { className: "label", textContent: t("copy") })); }, 1600);
      } catch { /* clipboard blocked: ignore */ }
    });
    actions.appendChild(copy);
    bubble.appendChild(actions);
  }
  scrollDown();
}

function failBot(li, key) {
  setText(li, t(key));
  li.classList.add("error");
}

async function send(question) {
  question = question.trim();
  if (!question || busy) return;
  busy = true;
  $("send").disabled = true;
  $("empty").hidden = true;
  $("new-chat").hidden = false;
  addUser(question);
  const li = addBot();
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(await authHeader()) },
      body: JSON.stringify({ question }),
    });
    if (res.status === 401) { li.previousElementSibling?.remove(); li.remove(); openSignIn("sessionExpired"); return; }
    if (res.status === 429) return failBot(li, "errLimit");
    if (!res.ok) return failBot(li, "errServer");
    fillBot(li, await res.json());
  } catch {
    failBot(li, "errNetwork");
  } finally {
    busy = false;
    $("send").disabled = false;
    $("q").focus();
  }
}

$("new-chat").addEventListener("click", () => {
  $("messages").replaceChildren();
  $("empty").hidden = false;
  $("new-chat").hidden = true;
  window.scrollTo({ top: 0 });
  $("q").focus();
});

/* ---------- Composer ---------- */
$("ask").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("q").value;
  $("q").value = "";
  $("q").style.height = "";
  send(q);
});
$("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("ask").requestSubmit();
  }
});
$("q").addEventListener("input", (e) => {   // grow with the text
  e.target.style.height = "auto";
  e.target.style.height = `${e.target.scrollHeight}px`;
});

/* ---------- Sign-in (Google Identity Platform) ---------- */
const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/10.12.2";

async function authHeader() {
  if (authDisabled || !fbAuth || !fbAuth.currentUser) return {};
  return { Authorization: `Bearer ${await fbAuth.currentUser.getIdToken()}` }; // refreshed automatically
}

function setNotice(key, isError = true) {
  const box = $("signin-notice");
  box.hidden = !key;
  box.classList.toggle("ok", !isError);
  if (key) { box.dataset.key = key; box.textContent = t(key); }
}

function openSignIn(noticeKey = "") {
  setNotice(noticeKey);
  if (!$("signin").open) $("signin").showModal();
  ($("email").value ? $("password") : $("email")).focus();
}

function errorKey(code = "") {
  if (["auth/invalid-credential", "auth/wrong-password", "auth/user-not-found", "auth/invalid-email"].includes(code)) return "errWrong";
  if (code === "auth/too-many-requests") return "errMany";
  if (code === "auth/user-disabled") return "errDisabled";
  return "errSignIn";
}

async function loadProfile() {
  try {
    const res = await fetch("/me", { headers: await authHeader() });
    if (!res.ok) throw new Error(String(res.status));
    role = (await res.json()).role;
  } catch { role = "employee"; }
  $("role-badge").hidden = role !== "hr_admin";
  $("admin-link").hidden = role !== "hr_admin";
}

function clearChat() {
  $("messages").replaceChildren();
  $("empty").hidden = false;
  $("new-chat").hidden = true;
}

async function initAuth() {
  const cfg = await (await fetch("/config")).json();
  authDisabled = cfg.auth_disabled;
  if (authDisabled) { await loadProfile(); return; }

  const { initializeApp } = await import(`${FIREBASE_SDK}/firebase-app.js`);
  fb = await import(`${FIREBASE_SDK}/firebase-auth.js`);
  fbAuth = fb.getAuth(initializeApp({ apiKey: cfg.api_key, authDomain: cfg.auth_domain }));

  fb.onAuthStateChanged(fbAuth, async (user) => {
    $("sign-out").hidden = !user;
    if (user) {
      $("sign-out").title = `${t("signOut")} (${user.email})`;
      if ($("signin").open) $("signin").close();
      await loadProfile();
      $("q").focus();
    } else {
      role = "employee";
      $("role-badge").hidden = true;
      $("admin-link").hidden = true;
      clearChat();
      openSignIn();
    }
  });
}

$("signin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fbAuth) return;
  const button = $("signin-button");
  button.disabled = true;
  setNotice("");
  try {
    await fb.signInWithEmailAndPassword(fbAuth, $("email").value.trim(), $("password").value);
    $("password").value = "";
  } catch (err) {
    setNotice(errorKey(err.code));
  } finally {
    button.disabled = false;
  }
});

$("forgot").addEventListener("click", async () => {
  const email = $("email").value.trim();
  if (!email) { setNotice("needEmail"); $("email").focus(); return; }
  try { await fb.sendPasswordResetEmail(fbAuth, email); } catch { /* same message either way */ }
  setNotice("resetSent", false); // never reveal whether the account exists
});

$("sign-out").addEventListener("click", () => fbAuth && fb.signOut(fbAuth));
$("signin").addEventListener("cancel", (e) => e.preventDefault()); // sign-in is required

applyLang();
initAuth().catch(() => openSignIn("errSignIn"));
