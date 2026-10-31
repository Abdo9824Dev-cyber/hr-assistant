// Al-Noor HR Assistant - document admin page (HR admins only; the server enforces this too).
"use strict";

const I18N = {
  en: {
    title: "HR Assistant", company: "Al-Noor Trading Co.", back: "Chat", dashboard: "Dashboard",
    switchTo: "العربية", signOut: "Sign out",
    themeToDark: "Switch to dark mode", themeToLight: "Switch to light mode",
    loading: "Loading documents…",
    notAdmin: "Only HR admins can manage documents.",
    loadError: "The document list didn't load. Refresh the page to try again.",
    uploadTitle: "Add a policy",
    uploadHelp: "Upload a PDF, a scan or a text file. The assistant reads it (Arabic or English) and can answer from it a few minutes later.",
    chooseFile: "Choose a file or drop it here",
    fileTypes: "PDF, PNG, JPG, TIFF or TXT, up to 10 MB and 15 pages",
    whoCanSee: "Who can get answers from it",
    allEmployees: "All employees",
    hrOnly: "HR admins only",
    titleEn: "Title in English", titleAr: "Title in Arabic",
    uploadBtn: "Upload and add", uploading: "Reading the document…",
    uploaded: "Added. It will be ready to answer questions in a few minutes.",
    tooBig: "The file is larger than 10 MB. Split it into smaller files.",
    uploadFailed: "The upload didn't work. Check your connection and try again.",
    docsTitle: "Documents",
    countsText: (all, hr) => `${all} for all employees, ${hr} HR only`,
    empty: "No documents yet. Add the first policy above.",
    ready: "Ready", indexing: "Getting ready…", failed: "Failed",
    by: "Added by", initialImport: "Initial import", delete: "Delete",
    confirmDelete: (t) => `Delete "${t}"? The assistant will stop answering from it. This can't be undone.`,
    deleteFailed: "The document wasn't deleted. Try again.",
  },
  ar: {
    title: "مساعد الموارد البشرية", company: "شركة النور التجارية", back: "المحادثة", dashboard: "لوحة المؤشرات",
    switchTo: "English", signOut: "تسجيل الخروج",
    themeToDark: "التبديل إلى الوضع الداكن", themeToLight: "التبديل إلى الوضع الفاتح",
    loading: "جارٍ تحميل المستندات…",
    notAdmin: "إدارة المستندات متاحة لمسؤولي الموارد البشرية فقط.",
    loadError: "لم يتم تحميل قائمة المستندات. حدّث الصفحة وحاول مرة أخرى.",
    uploadTitle: "إضافة سياسة",
    uploadHelp: "ارفع ملف PDF أو مستنداً ممسوحاً أو ملفاً نصياً. يقرأه المساعد (بالعربية أو الإنجليزية) ويمكنه الإجابة منه بعد دقائق.",
    chooseFile: "اختر ملفاً أو أفلته هنا",
    fileTypes: "PDF أو PNG أو JPG أو TIFF أو TXT، حتى 10 ميجابايت و15 صفحة",
    whoCanSee: "من يمكنه الحصول على إجابات منه",
    allEmployees: "جميع الموظفين",
    hrOnly: "مسؤولو الموارد البشرية فقط",
    titleEn: "العنوان بالإنجليزية", titleAr: "العنوان بالعربية",
    uploadBtn: "رفع وإضافة", uploading: "جارٍ قراءة المستند…",
    uploaded: "تمت الإضافة. سيكون جاهزاً للإجابة خلال دقائق.",
    tooBig: "حجم الملف أكبر من 10 ميجابايت. قسّمه إلى ملفات أصغر.",
    uploadFailed: "لم يكتمل الرفع. تحقق من الاتصال وحاول مرة أخرى.",
    docsTitle: "المستندات",
    countsText: (all, hr) => `${all} لجميع الموظفين، ${hr} للموارد البشرية فقط`,
    empty: "لا توجد مستندات بعد. أضف أول سياسة من الأعلى.",
    ready: "جاهز", indexing: "جارٍ التجهيز…", failed: "فشل",
    by: "أضافه", initialImport: "استيراد أولي", delete: "حذف",
    confirmDelete: (t) => `حذف "${t}"؟ سيتوقف المساعد عن الإجابة منه. لا يمكن التراجع عن ذلك.`,
    deleteFailed: "لم يتم حذف المستند. حاول مرة أخرى.",
  },
};

const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};
let lang = store.get("lang") || ((navigator.language || "").startsWith("ar") ? "ar" : "en");
const t = (k, ...a) => (typeof I18N[lang][k] === "function" ? I18N[lang][k](...a) : I18N[lang][k]);

let fbAuth = null, fb = {}, authDisabled = false;
let docs = [];
let pollTimer = null;
const MAX_BYTES = 10 * 1024 * 1024;

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
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $("lang").textContent = t("switchTo");
  $("sign-out").title = t("signOut");
  $("sign-out").setAttribute("aria-label", t("signOut"));
  const f = $("file").files[0];
  if (f) $("file-label").textContent = f.name;
  const msg = $("upload-msg");
  if (!msg.hidden && msg.dataset.key) msg.textContent = t(msg.dataset.key);
  if ($("state").dataset.key) $("state").textContent = t($("state").dataset.key);
  paintTheme();
  renderDocs();
}
$("lang").addEventListener("click", () => {
  lang = lang === "ar" ? "en" : "ar";
  store.set("lang", lang);
  applyLang();
});

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
  if (authDisabled) { $("sign-out").hidden = true; return enter(); }
  const { initializeApp } = await import(`${FIREBASE_SDK}/firebase-app.js`);
  fb = await import(`${FIREBASE_SDK}/firebase-auth.js`);
  fbAuth = fb.getAuth(initializeApp({ apiKey: cfg.api_key, authDomain: cfg.auth_domain }));
  fb.onAuthStateChanged(fbAuth, (user) => {
    if (!user) { location.href = "/"; return; }   // sign in on the chat page, then come back
    enter();
  });
}
$("sign-out").addEventListener("click", () => fbAuth && fb.signOut(fbAuth));

async function enter() {
  const me = await fetch("/me", { headers: await authHeader() });
  const role = me.ok ? (await me.json()).role : "employee";
  if (role !== "hr_admin") { setState("notAdmin"); $("panel").hidden = true; return; }
  await loadDocs();
}

/* ---------- Documents ---------- */
async function loadDocs() {
  try {
    const res = await fetch("/admin/documents", { headers: await authHeader() });
    if (res.status === 403) { setState("notAdmin"); return; }
    if (!res.ok) throw new Error(String(res.status));
    docs = (await res.json()).documents;
    setState("");
    $("panel").hidden = false;
    renderDocs();
    schedulePoll();
  } catch {
    setState("loadError");
  }
}

function schedulePoll() {
  clearTimeout(pollTimer);
  if (docs.some((d) => d.status === "indexing")) pollTimer = setTimeout(loadDocs, 8000);
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    // Gregorian calendar with Western digits in both languages (HR dates are Gregorian)
    return new Intl.DateTimeFormat(lang === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB",
      { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  } catch { return ""; }
}

function renderDocs() {
  const list = $("docs");
  if (!list) return;
  list.replaceChildren();
  const all = docs.filter((d) => d.store === "policies").length;
  $("counts").textContent = docs.length ? t("countsText", all, docs.length - all) : "";
  if (!docs.length) {
    const li = document.createElement("li");
    li.className = "doc-empty muted";
    li.textContent = t("empty");
    list.appendChild(li);
    return;
  }
  docs.forEach((d) => {
    const li = document.createElement("li");
    li.className = "doc";
    const ico = document.createElement("span");
    ico.className = "doc-icon" + (d.store === "confidential" ? " locked" : "");
    ico.appendChild(icon(d.store === "confidential" ? "lock" : "doc"));

    const main = document.createElement("div");
    main.className = "doc-main";
    const title = document.createElement("span");
    title.className = "doc-title";
    title.dir = "auto";
    title.textContent = lang === "ar" ? d.title_ar : d.title_en;
    const meta = document.createElement("span");
    meta.className = "doc-meta muted";
    [t(d.store === "confidential" ? "hrOnly" : "allEmployees"),
      d.uploaded_by === "initial import" ? t("initialImport") : (d.uploaded_by ? `${t("by")} ${d.uploaded_by}` : ""),
      formatDate(d.updated_at)].filter(Boolean).forEach((part) => {
      const span = document.createElement("span");
      span.dir = "auto";
      span.textContent = part;
      meta.appendChild(span);
    });
    main.append(title, meta);

    const status = document.createElement("span");
    status.className = `status ${d.status}`;
    status.textContent = t(d.status) || d.status;

    const del = document.createElement("button");
    del.type = "button";
    del.className = "icon-btn round danger";
    del.title = `${t("delete")}: ${title.textContent}`;
    del.setAttribute("aria-label", del.title);
    del.appendChild(icon("trash"));
    del.addEventListener("click", () => removeDoc(d, title.textContent, del));

    li.append(ico, main, status, del);
    list.appendChild(li);
  });
}

async function removeDoc(d, title, button) {
  if (!confirm(t("confirmDelete", title))) return;
  button.disabled = true;
  try {
    const res = await fetch(`/admin/documents/${encodeURIComponent(d.id)}`,
      { method: "DELETE", headers: await authHeader() });
    if (!res.ok && res.status !== 404) throw new Error(String(res.status));
    docs = docs.filter((x) => x.id !== d.id);
    renderDocs();
  } catch {
    button.disabled = false;
    alert(t("deleteFailed"));
  }
}

/* ---------- Upload ---------- */
function showMsg(key, ok = false, text = "") {
  const box = $("upload-msg");
  box.hidden = !key && !text;
  box.dataset.key = key || "";
  box.classList.toggle("ok", ok);
  box.textContent = text || (key ? t(key) : "");
}

$("file").addEventListener("change", () => {
  const f = $("file").files[0];
  $("file-label").textContent = f ? f.name : t("chooseFile");
  $("drop").classList.toggle("has-file", Boolean(f));
  showMsg("");
});
["dragover", "dragenter"].forEach((ev) => $("drop").addEventListener(ev, (e) => { e.preventDefault(); $("drop").classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => $("drop").addEventListener(ev, () => $("drop").classList.remove("over")));
$("drop").addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) {
    $("file").files = e.dataTransfer.files;
    $("file").dispatchEvent(new Event("change"));
  }
});

$("upload").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = $("file").files[0];
  if (!f) return;
  if (f.size > MAX_BYTES) { showMsg("tooBig"); return; }
  const form = new FormData();
  form.append("file", f);
  form.append("store", document.querySelector('input[name="store"]:checked').value);
  form.append("title_en", $("title-en").value.trim());
  form.append("title_ar", $("title-ar").value.trim());

  const btn = $("upload-btn");
  btn.disabled = true;
  btn.textContent = t("uploading");
  showMsg("");
  try {
    const res = await fetch("/admin/documents", { method: "POST", headers: await authHeader(), body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof body.detail === "string" ? body.detail : "";
      showMsg(detail ? "" : "uploadFailed", false, detail);  // server messages are written for the admin
      return;
    }
    $("upload").reset();
    $("file").dispatchEvent(new Event("change"));
    showMsg("uploaded", true);
    docs = docs.filter((x) => x.id !== body.id).concat(body);
    renderDocs();
    schedulePoll();
  } catch {
    showMsg("uploadFailed");
  } finally {
    btn.disabled = false;
    btn.textContent = t("uploadBtn");
  }
});

applyLang();
start().catch(() => setState("loadError"));
