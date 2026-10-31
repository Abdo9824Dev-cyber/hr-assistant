// Al-Noor HR Assistant - analytics dashboard (HR admins only; the server enforces this too).
"use strict";

const I18N = {
  en: {
    title: "HR Assistant", company: "Al-Noor Trading Co.", back: "Chat", documents: "Documents",
    switchTo: "العربية", signOut: "Sign out",
    themeToDark: "Switch to dark mode", themeToLight: "Switch to light mode",
    loading: "Loading the dashboard…", notAdmin: "Only HR admins can see the dashboard.",
    loadError: "The dashboard didn't load. Refresh the page to try again.",
    dashTitle: "What employees ask",
    dashHelp: "Anonymous: questions are recorded without names or emails.",
    days: (n) => `${n} days`,
    demoNote: (n) => `Includes ${n} demo questions created for testing.`,
    kQuestions: "Questions", kAnswered: "Answered from policies", kToHr: "Sent to HR",
    kLatency: "Typical answer time", kLang: "Asked in Arabic",
    ofTotal: (n) => `of ${n} questions`, seconds: (s) => `${s} s`, englishShare: (p) => `${p}% in English`,
    perDay: "Questions per day", answered: "Answered", toHr: "Sent to HR",
    showTable: "Show as a table", date: "Date", total: "Total",
    gapsTitle: "Questions the policies don't answer",
    gapsHelp: "Employees were sent to HR for these. Each one is a candidate for a new or clearer policy.",
    topTitle: "Most asked", sourcesTitle: "Most used policies", deptTitle: "Questions by department",
    times: (n) => (n === 1 ? "1 time" : `${n} times`),
    empty: "No questions in this period yet.", none: "None in this period.",
    depts: { Finance: "Finance", Sales: "Sales", Warehouse: "Warehouse", IT: "IT", HR: "HR", unassigned: "Not set" },
  },
  ar: {
    title: "مساعد الموارد البشرية", company: "شركة النور التجارية", back: "المحادثة", documents: "المستندات",
    switchTo: "English", signOut: "تسجيل الخروج",
    themeToDark: "التبديل إلى الوضع الداكن", themeToLight: "التبديل إلى الوضع الفاتح",
    loading: "جارٍ تحميل لوحة المؤشرات…", notAdmin: "لوحة المؤشرات متاحة لمسؤولي الموارد البشرية فقط.",
    loadError: "لم يتم تحميل لوحة المؤشرات. حدّث الصفحة وحاول مرة أخرى.",
    dashTitle: "ماذا يسأل الموظفون",
    dashHelp: "بيانات مجهولة الهوية: تُسجَّل الأسئلة بدون أسماء أو بريد إلكتروني.",
    days: (n) => `${n} يوماً`,
    demoNote: (n) => `تشمل ${n} سؤالاً تجريبياً أُنشئت للاختبار.`,
    kQuestions: "الأسئلة", kAnswered: "أُجيب عنها من السياسات", kToHr: "أُحيلت إلى الموارد البشرية",
    kLatency: "زمن الإجابة المعتاد", kLang: "طُرحت بالعربية",
    ofTotal: (n) => `من ${n} سؤالاً`, seconds: (s) => `${s} ث`, englishShare: (p) => `${p}% بالإنجليزية`,
    perDay: "الأسئلة يومياً", answered: "أُجيب عنها", toHr: "أُحيلت إلى الموارد البشرية",
    showTable: "عرض كجدول", date: "التاريخ", total: "المجموع",
    gapsTitle: "أسئلة لا تجيب عنها السياسات",
    gapsHelp: "أُحيل الموظفون إلى الموارد البشرية في هذه الأسئلة. كل سؤال منها فرصة لسياسة جديدة أو أوضح.",
    topTitle: "الأكثر سؤالاً", sourcesTitle: "السياسات الأكثر استخداماً", deptTitle: "الأسئلة حسب الإدارة",
    times: (n) => (n === 1 ? "مرة واحدة" : n === 2 ? "مرتان" : `${n} مرات`),
    empty: "لا توجد أسئلة في هذه الفترة بعد.", none: "لا شيء في هذه الفترة.",
    depts: { Finance: "المالية", Sales: "المبيعات", Warehouse: "المستودعات", IT: "تقنية المعلومات", HR: "الموارد البشرية", unassigned: "غير محدد" },
  },
};

const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};
let lang = store.get("lang") || ((navigator.language || "").startsWith("ar") ? "ar" : "en");
let days = Number(store.get("dashDays")) || 30;
const t = (k, ...a) => (typeof I18N[lang][k] === "function" ? I18N[lang][k](...a) : I18N[lang][k]);
const num = (n) => new Intl.NumberFormat(lang === "ar" ? "ar-SA-u-nu-latn" : "en-GB").format(n);
let fbAuth = null, fb = {}, authDisabled = false, data = null;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

/* ---------- Theme + language ---------- */
function currentTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function paintTheme() {
  const dark = currentTheme() === "dark";
  $("theme").replaceChildren(icon(dark ? "sun" : "moon"));
  $("theme").title = t(dark ? "themeToLight" : "themeToDark");
  $("theme").setAttribute("aria-label", $("theme").title);
}
$("theme").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store.set("theme", next);
  paintTheme();
});
function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  document.querySelectorAll("#period button").forEach((b) => {
    b.textContent = t("days", Number(b.dataset.days));
    b.setAttribute("aria-pressed", String(Number(b.dataset.days) === days));
  });
  $("lang").textContent = t("switchTo");
  $("sign-out").title = t("signOut");
  $("sign-out").setAttribute("aria-label", t("signOut"));
  if ($("state").dataset.key) $("state").textContent = t($("state").dataset.key);
  paintTheme();
  if (data) render();
}
$("lang").addEventListener("click", () => { lang = lang === "ar" ? "en" : "ar"; store.set("lang", lang); applyLang(); });
document.querySelectorAll("#period button").forEach((b) => b.addEventListener("click", () => {
  days = Number(b.dataset.days);
  store.set("dashDays", String(days));
  applyLang();
  load();
}));

/* ---------- Auth ---------- */
const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/10.12.2";
async function authHeader() {
  if (authDisabled || !fbAuth || !fbAuth.currentUser) return {};
  return { Authorization: `Bearer ${await fbAuth.currentUser.getIdToken()}` };
}
function setState(key) {
  $("state").dataset.key = key || "";
  $("state").textContent = key ? t(key) : "";
  $("state").hidden = !key;
}
async function start() {
  setState("loading");
  const cfg = await (await fetch("/config")).json();
  authDisabled = cfg.auth_disabled;
  if (authDisabled) { $("sign-out").hidden = true; return load(); }
  const { initializeApp } = await import(`${FIREBASE_SDK}/firebase-app.js`);
  fb = await import(`${FIREBASE_SDK}/firebase-auth.js`);
  fbAuth = fb.getAuth(initializeApp({ apiKey: cfg.api_key, authDomain: cfg.auth_domain }));
  fb.onAuthStateChanged(fbAuth, (user) => { if (!user) location.href = "/"; else load(); });
}
$("sign-out").addEventListener("click", () => fbAuth && fb.signOut(fbAuth));

async function load() {
  try {
    const res = await fetch(`/admin/analytics?days=${days}`, { headers: await authHeader() });
    if (res.status === 403) { setState("notAdmin"); $("panel").hidden = true; return; }
    if (!res.ok) throw new Error(String(res.status));
    data = await res.json();
    setState("");
    $("panel").hidden = false;
    render();
  } catch {
    setState("loadError");
  }
}

/* ---------- Rendering ---------- */
function render() {
  $("demo-note").hidden = !data.demo_records;
  if (data.demo_records) $("demo-note").textContent = t("demoNote", num(data.demo_records));
  renderKpis();
  renderColumns();
  renderRanked($("gaps"), data.unanswered, (r) => r.question, (r) => r.count, "to-hr", true);
  renderRanked($("top"), data.top_questions, (r) => r.question, (r) => r.count, "answered", true);
  renderRanked($("sources"), data.top_sources, (r) => (lang === "ar" ? r.title_ar : r.title_en) || r.name, (r) => r.count, "answered");
  renderRanked($("depts"), data.departments, (r) => t("depts")[r.name] || r.name, (r) => r.count, "answered");
}

function tile(label, value, note) {
  const box = el("div", "kpi");
  box.append(el("span", "kpi-label", label), el("span", "kpi-value", value));
  if (note) box.append(el("span", "kpi-note", note));
  return box;
}

function renderKpis() {
  const k = $("kpis");
  k.replaceChildren();
  const total = data.total;
  const pct = (n) => (total ? Math.round((n / total) * 100) : 0);
  const ar = data.languages.ar || 0;
  k.append(
    tile(t("kQuestions"), num(total)),
    tile(t("kAnswered"), total ? `${pct(data.answered)}%` : "–", total ? t("ofTotal", num(total)) : ""),
    tile(t("kToHr"), num(data.to_hr), total ? `${pct(data.to_hr)}%` : ""),
    tile(t("kLatency"), data.median_latency_ms ? t("seconds", (data.median_latency_ms / 1000).toFixed(1)) : "–"),
    tile(t("kLang"), total ? `${pct(ar)}%` : "–", total ? t("englishShare", 100 - pct(ar)) : ""),
  );
}

function shortDate(iso, withYear = false) {
  const d = new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB",
    withYear ? { day: "numeric", month: "long", year: "numeric" } : { day: "numeric", month: "short" }).format(d);
}

function renderColumns() {
  const box = $("columns");
  box.replaceChildren();
  const series = data.by_day;
  const max = Math.max(1, ...series.map((d) => d.answered + d.to_hr));
  const step = max <= 4 ? 1 : Math.ceil(max / 4);
  const top = step * Math.ceil(max / step);

  const grid = el("div", "col-grid");
  for (let v = top; v >= 0; v -= step) {
    const line = el("div", "gridline");
    line.style.bottom = `${(v / top) * 100}%`;
    line.append(el("span", "gridlabel", num(v)));
    grid.append(line);
  }
  const plot = el("div", "col-plot");
  // Space date labels by the room available (about 64px each), counted back from today so the last day is labelled
  const room = Math.max(1, Math.floor((box.clientWidth || 600) / 64));
  const labelEvery = Math.max(1, Math.ceil(series.length / room));
  series.forEach((d, i) => {
    const total = d.answered + d.to_hr;
    const col = el("div", "col");
    col.tabIndex = 0;
    col.setAttribute("role", "img");
    col.setAttribute("aria-label", `${shortDate(d.date, true)}: ${t("answered")} ${d.answered}, ${t("toHr")} ${d.to_hr}`);
    const stack = el("div", "stack");
    stack.style.height = `${(total / top) * 100}%`;
    if (d.to_hr) { const s = el("div", "seg to-hr"); s.style.flexGrow = d.to_hr; stack.append(s); }
    if (d.answered) { const s = el("div", "seg answered"); s.style.flexGrow = d.answered; stack.append(s); }
    col.append(stack);
    if ((series.length - 1 - i) % labelEvery === 0) col.append(el("span", "xlabel", shortDate(d.date)));
    const show = () => showTip(col, d);
    col.addEventListener("mouseenter", show);
    col.addEventListener("focus", show);
    col.addEventListener("mouseleave", hideTip);
    col.addEventListener("blur", hideTip);
    plot.append(col);
  });
  box.append(grid, plot);

  // the same numbers as a table (screen readers, exact values)
  const table = $("day-table");
  table.replaceChildren();
  const head = el("tr");
  [t("date"), t("answered"), t("toHr"), t("total")].forEach((h) => head.append(el("th", "", h)));
  table.append(head);
  series.filter((d) => d.answered + d.to_hr).forEach((d) => {
    const tr = el("tr");
    [shortDate(d.date, true), num(d.answered), num(d.to_hr), num(d.answered + d.to_hr)].forEach((c) => tr.append(el("td", "", c)));
    table.append(tr);
  });
}

function showTip(col, d) {
  const tip = $("tip");
  tip.replaceChildren(el("strong", "", shortDate(d.date, true)));
  [["answered", d.answered], ["to-hr", d.to_hr]].forEach(([cls, n]) => {
    const row = el("span", "tip-row");
    row.append(el("i", `sw ${cls}`), el("span", "", cls === "answered" ? t("answered") : t("toHr")), el("b", "", num(n)));
    tip.append(row);
  });
  tip.hidden = false;
  const card = col.closest(".card").getBoundingClientRect();
  const c = col.getBoundingClientRect();
  const x = Math.min(Math.max(c.left - card.left + c.width / 2 - tip.offsetWidth / 2, 8), card.width - tip.offsetWidth - 8);
  tip.style.left = `${x}px`;
  tip.style.top = `${c.top - card.top + 8}px`;
}
function hideTip() { $("tip").hidden = true; }

function renderRanked(list, rows, label, value, cls, autoDir = false) {
  list.replaceChildren();
  if (!rows || !rows.length) {
    list.append(el("li", "ranked-empty muted", data.total ? t("none") : t("empty")));
    return;
  }
  const max = Math.max(...rows.map(value));
  rows.forEach((r) => {
    const li = el("li", "rank");
    const name = el("span", "rank-name", label(r));
    if (autoDir) name.dir = "auto";
    const count = el("span", "rank-count", t("times", value(r)));
    const track = el("span", "rank-track");
    const bar = el("span", `rank-bar ${cls}`);
    bar.style.width = `${Math.max(4, (value(r) / max) * 100)}%`;
    track.append(bar);
    li.append(name, count, track);
    list.append(li);
  });
}

applyLang();
start().catch(() => setState("loadError"));

// Redraw the columns when the width changes, so date labels never collide
let resizeTimer, lastWidth = innerWidth;
addEventListener("resize", () => {
  if (innerWidth === lastWidth) return;
  lastWidth = innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (data) renderColumns(); }, 150);
});
