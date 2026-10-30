/* ==========================================================================
   گذرگاه — منطقِ پنل
   بدونِ وابستگیِ بیرونی. همهٔ داده از index.json / health.json /
   Countries/index.json / top100.txt خوانده می‌شود و هر لینک پیش از نمایش
   با safeUrl سنجیده می‌شود.
   ========================================================================== */

(function () {
  "use strict";

  var FALLBACK = { owner: "alireza786786", repo: "ai-driven-v2ray", branch: "main" };
  var NS = "http://www.w3.org/2000/svg";

  var faNum = new Intl.NumberFormat("fa-IR");
  var faPct = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
  var faDate = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" });
  var relFmt = new Intl.RelativeTimeFormat("fa", { numeric: "auto" });
  var regionNames = null;
  try {
    regionNames = new Intl.DisplayNames(["fa"], { type: "region" });
  } catch (e) { /* مرورگرِ قدیمی: نامِ انگلیسیِ داده نمایش داده می‌شود */ }

  var repo = detectRepo();
  var RAW_BASE = "https://raw.githubusercontent.com/" + repo.owner + "/" + repo.repo + "/" + FALLBACK.branch;
  var CDN_BASE = "https://cdn.jsdelivr.net/gh/" + repo.owner + "/" + repo.repo + "@" + FALLBACK.branch;

  var state = {
    index: null,
    health: null,
    countries: null,
    top100: null,
    source: null,
    primary: RAW_BASE,
    mirror: CDN_BASE,
    composer: { tier: "verified", format: "configs_txt", route: "primary", url: null },
    countryQuery: "",
    countryExpanded: false,
    top100Expanded: false,
    qrUrl: "",
    loaded: false
  };

  var TIERS = [
    { key: "verified", label: "تأییدشده" },
    { key: "fast", label: "سریع" },
    { key: "secure", label: "امن" },
    { key: "all", label: "همه" },
    { key: "heavy", label: "انبوه" },
    { key: "light", label: "سبک" }
  ];
  var FORMATS = [
    { key: "configs_txt", label: "متن" },
    { key: "configs_base64", label: "Base64" },
    { key: "clash_yaml", label: "Clash" },
    { key: "singbox_json", label: "Sing-box" }
  ];
  var STATUS_FA = { ok: "سالم", fail: "خطا", empty: "خالی", disabled: "غیرفعال", unknown: "نامعلوم" };
  var TIER_FA = { light: "سبک", heavy: "انبوه" };
  var REASON_FA = {
    unparsable: "تجزیه‌نشده",
    invalid_port: "پورتِ نامعتبر",
    invalid_uuid: "UUIDِ نامعتبر",
    unroutable_server: "مسیرِ نامعتبر",
    invalid_server: "سرورِ نامعتبر",
    duplicate: "تکراری",
    not_expressible: "قابلِ بیان نبود",
    ss_unknown_method: "روشِ ناشناختهٔ SS",
    ss_bad_plugin_mode: "حالتِ افزونهٔ SS",
    reality_bad_public_key: "کلیدِ عمومیِ REALITY"
  };

  var QR = {
    panel: { src: "assets/qr/panel.svg", title: "پنل", url: "https://alireza786786.github.io/ai-driven-v2ray/" },
    top100: { src: "assets/qr/top100.svg", title: "فهرستِ ۱۰۰ برتر", url: RAW_BASE + "/top100.txt" },
    verified: { src: "assets/qr/verified.svg", title: "تأییدشده (Base64)", url: RAW_BASE + "/verified/configs_base64.txt" },
    fast: { src: "assets/qr/fast.svg", title: "سریع (Base64)", url: RAW_BASE + "/fast/configs_base64.txt" },
    secure: { src: "assets/qr/secure.svg", title: "امن (Base64)", url: RAW_BASE + "/secure/configs_base64.txt" },
    all: { src: "assets/qr/all.svg", title: "همهٔ یکتاها (Base64)", url: RAW_BASE + "/all/configs_base64.txt" },
    telegram: { src: "assets/qr/telegram.svg", title: "کانالِ تلگرام", url: "https://t.me/+m4GhEHGLd2k5ZjU0" }
  };

  var copyTimers = new WeakMap();
  var toastTimer = null;

  /* ── ابزارهای پایه ─────────────────────────────────────────────────────── */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function detectRepo() {
    try {
      if (location.hostname.slice(-10) === ".github.io") {
        var owner = location.hostname.split(".")[0];
        var seg = location.pathname.split("/").filter(Boolean);
        return { owner: owner, repo: seg[0] || FALLBACK.repo };
      }
    } catch (e) { /* ignore */ }
    return { owner: FALLBACK.owner, repo: FALLBACK.repo };
  }

  function fmt(value) {
    var n = Number(value);
    return isFinite(n) ? faNum.format(n) : "—";
  }

  function pct(value) {
    var n = Number(value);
    return isFinite(n) ? faPct.format(n) + "٪" : "—";
  }

  function safeUrl(value) {
    if (typeof value !== "string" || !value) return null;
    try {
      var u = new URL(value);
      return (u.protocol === "https:" || u.protocol === "http:") ? u.href : null;
    } catch (e) {
      return null;
    }
  }

  function normalize(value) {
    return String(value || "")
      .replace(/[يى]/g, "ی")
      .replace(/ك/g, "ک")
      .replace(/\u200c/g, " ")
      .toLowerCase();
  }

  function countryName(item) {
    if (!item) return "نامعلوم";
    if (item.code && regionNames) {
      try {
        var name = regionNames.of(String(item.code).toUpperCase());
        if (name && name !== item.code) return name;
      } catch (e) { /* ignore */ }
    }
    return item.name || item.code || "نامعلوم";
  }

  function regionName(code) {
    if (!code) return "";
    if (regionNames) {
      try {
        var name = regionNames.of(String(code).toUpperCase());
        if (name && name !== code) return name;
      } catch (e) { /* ignore */ }
    }
    return String(code).toUpperCase();
  }

  function ccOf(code) {
    var text = String(code || "").toUpperCase();
    return /^[A-Z]{2}$/.test(text) ? text : "";
  }

  function relTime(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return "—";
    var diff = date.getTime() - Date.now();
    var abs = Math.abs(diff);
    var unit = abs < 3600000 ? "minute" : (abs < 172800000 ? "hour" : "day");
    var div = unit === "minute" ? 60000 : (unit === "hour" ? 3600000 : 86400000);
    return relFmt.format(Math.round(diff / div), unit);
  }

  function fmtDate(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return "—";
    return faDate.format(date);
  }

  function fmtDuration(seconds) {
    var s = Math.round(Number(seconds));
    if (!isFinite(s) || s < 0) return "—";
    if (s < 60) return fmt(s) + " ثانیه";
    var m = Math.floor(s / 60);
    var r = s % 60;
    return r ? fmt(m) + " دقیقه و " + fmt(r) + " ثانیه" : fmt(m) + " دقیقه";
  }

  function make(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }

  function icon(name) {
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function guard(label, fn) {
    try {
      fn();
    } catch (err) {
      console.error("[گذرگاه] " + label, err);
    }
  }

  function setText(id, text) {
    var el = typeof id === "string" ? document.getElementById(id) : id;
    if (el) el.textContent = text;
  }

  function setStatus(kind, text) {
    var pill = $("#status");
    if (!pill) return;
    pill.dataset.state = kind;
    setText("status-text", text);
  }

  function toast(message) {
    var el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("show"); }, 2300);
  }

  /* ── کپی ──────────────────────────────────────────────────────────────── */

  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  function flash(btn) {
    if (!btn) return;
    var original = btn.innerHTML;
    clearTimeout(copyTimers.get(btn));
    btn.classList.add("is-copied");
    btn.textContent = "کپی شد";
    var timer = setTimeout(function () {
      btn.classList.remove("is-copied");
      btn.innerHTML = original;
      copyTimers.delete(btn);
    }, 1600);
    copyTimers.set(btn, timer);
  }

  function copyText(text, btn) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        flash(btn);
        toast("در کلیپ‌بورد کپی شد.");
      }).catch(function () {
        if (legacyCopy(text)) {
          flash(btn);
          toast("در کلیپ‌بورد کپی شد.");
        } else {
          toast("کپی ممکن نشد؛ نشانی را دستی انتخاب کن.");
        }
      });
    } else if (legacyCopy(text)) {
      flash(btn);
      toast("در کلیپ‌بورد کپی شد.");
    } else {
      toast("کپی ممکن نشد؛ نشانی را دستی انتخاب کن.");
    }
  }

  /* ── واکشی ────────────────────────────────────────────────────────────── */

  function fetchWithTimeout(url, kind) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 15000);
    return fetch(url, { cache: "no-store", signal: controller.signal })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return kind === "text" ? res.text() : res.json();
      })
      .then(function (data) {
        clearTimeout(timer);
        return data;
      })
      .catch(function (err) {
        clearTimeout(timer);
        throw err;
      });
  }

  function bust(url) {
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "_=" + Date.now();
  }

  function fetchIndex() {
    var attempts = [
      { url: bust(RAW_BASE + "/index.json"), source: "raw" },
      { url: bust(CDN_BASE + "/index.json"), source: "mirror" }
    ];
    var i = 0;
    function next() {
      if (i >= attempts.length) return Promise.reject(new Error("index.json در دسترس نیست"));
      var a = attempts[i++];
      return fetchWithTimeout(a.url, "json").then(function (data) {
        if (!data || typeof data !== "object") throw new Error("index.json نامعتبر است");
        return { data: data, source: a.source };
      }).catch(next);
    }
    return next();
  }

  function fetchFrom(primary, mirror, kind) {
    var attempts = [];
    if (safeUrl(primary)) attempts.push({ url: bust(primary), source: "raw" });
    if (safeUrl(mirror)) attempts.push({ url: bust(mirror), source: "mirror" });
    if (!attempts.length) return Promise.reject(new Error("نشانیِ معتبر نیست"));
    var i = 0;
    function next() {
      if (i >= attempts.length) return Promise.reject(new Error("همهٔ مسیرها ناموفق بودند"));
      var a = attempts[i++];
      return fetchWithTimeout(a.url, kind || "json").then(function (data) {
        return { data: data, source: a.source };
      }).catch(next);
    }
    return next();
  }

  /* ── حالت و تازگی ─────────────────────────────────────────────────────── */

  function freshness() {
    if (!state.index) return "error";
    var date = new Date(state.index.updated_at);
    if (isNaN(date.getTime())) return "error";
    var ageMin = (Date.now() - date.getTime()) / 60000;
    var interval = Number(state.index.update_interval_minutes) || 45;
    if (ageMin <= Math.max(interval * 2, 90)) return "live";
    if (ageMin <= Math.max(interval * 6, 240)) return "waiting";
    return "stale";
  }

  function updateFreshness() {
    if (!state.index) return;
    var status = freshness();
    var updated = state.index.updated_at;
    var relative = relTime(updated);
    var labels = {
      live: "زنده · " + relative,
      waiting: "در انتظار · " + relative,
      stale: "کهنه · " + relative,
      error: "اتصال برقرار نشد"
    };
    setStatus(status, labels[status] || labels.error);

    var banner = $("#stale-banner");
    var bannerText = $("#stale-text");
    if (banner && bannerText) {
      if (status === "stale") {
        banner.hidden = false;
        bannerText.textContent = "این نسخه از داده‌ها " + relative + " ساخته شده است؛ اجرای تازه هنوز منتشر نشده. فایل‌ها در دسترس‌اند، ولی تازگیِ کانفیگ‌ها تضمین نمی‌شود.";
      } else if (status === "error") {
        banner.hidden = false;
        bannerText.textContent = "خواندنِ index.json ممکن نشد؛ گزارشِ تازگی در دسترس نیست.";
      } else {
        banner.hidden = true;
      }
    }

    setText("pass-updated", "آخرین اجرا " + fmtDate(updated));
    var passDot = $("#pass-updated");
    if (passDot && passDot.parentElement) {
      var dot = passDot.parentElement.querySelector(".dot");
      if (dot) dot.className = "dot " + (status === "live" ? "dot-ok" : "dot-warn");
    }

    var next = state.index.next_update_eta ? new Date(state.index.next_update_eta) : null;
    setText("pass-next", next && !isNaN(next.getTime()) && next.getTime() > Date.now()
      ? "اجرای بعدی " + relTime(state.index.next_update_eta)
      : "در انتظارِ اجرای تازه");

    var sourceLabel = state.source === "mirror" ? "آینهٔ jsDelivr" : "raw";
    setText("foot-meta", "دادهٔ زنده از index.json · آخرین اجرا " + fmtDate(updated) + " · خوانده‌شده از " + sourceLabel);
  }

  /* ── رندرِ قهرمان و مسیرها ─────────────────────────────────────────────── */

  function animateCount(el, value) {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      el.textContent = fmt(value);
      return;
    }
    var start = performance.now();
    var end = Number(value) || 0;
    function frame(now) {
      var t = Math.min(1, (now - start) / 900);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(Math.round(end * eased));
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function renderHero() {
    var index = state.index;
    var all = index.categories && index.categories.all ? index.categories.all.unique : 0;
    var verified = getTier("verified") ? getTier("verified").unique : 0;
    var countries = index.countries ? index.countries.count : 0;
    var top = index.top100 ? index.top100.count : 0;

    animateCount($("#stat-unique"), all);
    animateCount($("#stat-verified"), verified);
    animateCount($("#stat-countries"), countries);
    animateCount($("#stat-top100"), top);
    setText("pass-verified", fmt(verified));
    var stats = $("#hero-stats");
    if (stats) stats.setAttribute("aria-busy", "false");

    var heroBtn = $("#hero-copy-top100");
    if (heroBtn && index.top100 && safeUrl(index.top100.url)) {
      heroBtn.disabled = false;
      heroBtn.addEventListener("click", function () {
        copyText(index.top100.url, heroBtn);
      });
    }
  }

  function getTier(name) {
    if (!state.index) return null;
    if (state.index.categories && state.index.categories[name]) return state.index.categories[name];
    if (state.index.cascade_categories && state.index.cascade_categories[name]) return state.index.cascade_categories[name];
    return null;
  }

  function makeChip(label, url, iconName) {
    var link = safeUrl(url);
    if (!link) return null;
    var el = make("a", "chip");
    el.href = link;
    el.target = "_blank";
    el.rel = "noopener";
    if (iconName) el.appendChild(icon(iconName));
    el.appendChild(make("span", null, label));
    return el;
  }

  function makeCopyChip(label, url, iconName) {
    var link = safeUrl(url);
    if (!link) return null;
    var el = make("button", "chip");
    el.type = "button";
    el.dataset.copyValue = link;
    el.setAttribute("aria-label", "کپیِ " + label);
    if (iconName) el.appendChild(icon(iconName));
    el.appendChild(make("span", null, label));
    return el;
  }

  function renderRoutes() {
    var grid = $("#route-grid");
    if (!grid) return;
    grid.innerHTML = "";
    var index = state.index;
    var verified = getTier("verified");
    var all = getTier("all");

    var routes = [];
    if (index.top100 && safeUrl(index.top100.url)) {
      routes.push({
        title: "۱۰۰ برتر",
        kicker: "پیشنهادِ اول",
        badge: "سریع‌ترین شروع",
        badgeClass: "",
        accent: "var(--emerald)",
        count: index.top100.count,
        criterion: "تأییدشده‌ها، مرتب بر اساسِ میانهٔ تأخیر؛ هیچ ردیفِ آزمون‌نشده‌ای به فهرست اضافه نمی‌شود.",
        qr: "top100",
        primary: { label: "کپیِ نشانی", url: index.top100.url },
        extra: [
          makeChip("باز کردنِ فایل", index.top100.url, "external"),
          makeChip("آینه", index.top100.url_mirror, "external")
        ]
      });
    }
    if (verified && verified.files) {
      routes.push({
        title: "تأییدشده",
        kicker: "پایهٔ مطمئن",
        badge: "هر ۳ دور",
        badgeClass: "",
        accent: "var(--ink-soft)",
        count: verified.unique,
        criterion: "در هر سه دورِ اجرا، یک درخواستِ واقعی از داخلِ پروکسی پاسخ داده است؛ فهرستِ پیشنهادی برای استفادهٔ روزمره.",
        qr: "verified",
        primary: { label: "کپیِ Base64", url: verified.files.configs_base64 },
        extra: [
          makeChip("متن", verified.files.configs_txt, "external"),
          makeChip("آینه", verified.files.configs_base64_mirror, "external")
        ]
      });
    }
    if (all && all.files) {
      routes.push({
        title: "همهٔ یکتاها",
        kicker: "بزرگ‌ترین فهرست",
        badge: "بدونِ آزمون",
        badgeClass: "badge-quiet",
        accent: "var(--amber)",
        count: all.unique,
        criterion: "هر چه پس از غربالِ ساختاری و یکتاسازی مانده؛ بزرگ‌ترین فهرست و کمترین شواهد. برای آزمونِ دستی یا فهرستِ پشتیبان.",
        qr: "all",
        primary: { label: "کپیِ متن", url: all.files.configs_txt },
        extra: [
          makeChip("Base64", all.files.configs_base64, "external"),
          makeChip("Clash", all.files.clash_yaml, "external"),
          makeChip("آینه", all.files.configs_txt_mirror, "external")
        ]
      });
    }

    if (!routes.length) {
      grid.appendChild(fatalCard("داده‌های index.json ناقص است و مسیرِ آماده‌ای پیدا نشد."));
      grid.setAttribute("aria-busy", "false");
      return;
    }

    routes.forEach(function (route) {
      var card = make("article", "route");
      card.style.setProperty("--accent", route.accent);

      var top = make("div", "route-top");
      var head = make("div");
      head.appendChild(make("h3", null, route.title));
      head.appendChild(make("span", "route-kicker", route.kicker));
      var badge = make("span", "badge " + route.badgeClass, route.badge);
      head.appendChild(badge);
      top.appendChild(head);

      if (route.qr && QR[route.qr]) {
        var qrBtn = make("button", "route-qr");
        qrBtn.type = "button";
        qrBtn.dataset.qr = route.qr;
        qrBtn.setAttribute("aria-label", "نمایشِ بزرگِ کیوآرکدِ " + route.title);
        var qrImg = document.createElement("img");
        qrImg.src = QR[route.qr].src;
        qrImg.alt = "کیوآرکدِ " + route.title;
        qrImg.width = 54;
        qrImg.height = 54;
        qrBtn.appendChild(qrImg);
        top.appendChild(qrBtn);
      }
      card.appendChild(top);

      var count = make("div", "count", fmt(route.count));
      count.appendChild(make("small", null, "کانفیگ"));
      card.appendChild(count);
      card.appendChild(make("p", null, route.criterion));

      var actions = make("div", "route-actions");
      if (route.primary && safeUrl(route.primary.url)) {
        var copyBtn = make("button", "btn btn-primary btn-sm");
        copyBtn.type = "button";
        copyBtn.appendChild(icon("copy"));
        copyBtn.appendChild(make("span", null, route.primary.label));
        copyBtn.dataset.copyValue = route.primary.url;
        actions.appendChild(copyBtn);
      }
      route.extra.forEach(function (el) { if (el) actions.appendChild(el); });
      card.appendChild(actions);
      grid.appendChild(card);
    });
    grid.setAttribute("aria-busy", "false");
  }

  function fatalCard(message) {
    var card = make("article", "route");
    card.style.setProperty("--accent", "var(--danger)");
    card.appendChild(make("h3", null, "داده در دسترس نیست"));
    card.appendChild(make("p", null, message));
    var actions = make("div", "route-actions");
    var retry = make("button", "btn btn-primary btn-sm", "تلاش دوباره");
    retry.type = "button";
    retry.addEventListener("click", function () { location.reload(); });
    actions.appendChild(retry);
    var raw = makeChip("باز کردنِ index.json", RAW_BASE + "/index.json", "external");
    if (raw) actions.appendChild(raw);
    card.appendChild(actions);
    return card;
  }

  /* ── نردبان ───────────────────────────────────────────────────────────── */

  function renderLadder() {
    var index = state.index;
    var all = getTier("all");
    var base = all ? all.unique : 0;

    ["all", "verified", "fast", "secure"].forEach(function (tier) {
      var block = getTier(tier);
      var countEl = $('[data-tier-count="' + tier + '"]');
      var barEl = $('[data-tier-bar="' + tier + '"]');
      var linksEl = $('[data-tier-links="' + tier + '"]');
      if (countEl) countEl.textContent = fmt(block ? block.unique : 0);
      if (barEl) {
        var share = base && block ? Math.max(block.unique ? 1.2 : 0, (block.unique / base) * 100) : 0;
        barEl.style.setProperty("--w", "0%");
        requestAnimationFrame(function () {
          barEl.style.setProperty("--w", share.toFixed(2) + "%");
        });
      }
      if (linksEl) {
        linksEl.innerHTML = "";
        if (block && block.files) {
          [
            makeCopyChip("کپیِ متن", block.files.configs_txt, "copy"),
            makeCopyChip("کپیِ Base64", block.files.configs_base64, "copy"),
            makeChip("Clash", block.files.clash_yaml, "external"),
            makeChip("Sing-box", block.files.singbox_json, "external")
          ].forEach(function (el) { if (el) linksEl.appendChild(el); });
        }
        if (!linksEl.children.length) {
          linksEl.appendChild(make("span", "footnote", "برای این پله فایلی منتشر نشده است."));
        }
      }
    });

    var ladder = $("#ladder");
    if (ladder) ladder.setAttribute("aria-busy", "false");
    var note = $("#ladder-note");
    if (note && all) {
      note.textContent = "درصدِ هر پله نسبت به " + fmt(all.unique) + " کانفیگِ یکتای همین اجرا سنجیده می‌شود؛ «سریع» و «امن» دو محورِ مستقل‌اند.";
    }
  }

  /* ── سازندهٔ لینک ─────────────────────────────────────────────────────── */

  function buildComposerControls() {
    var tierBox = $("#composer-tier");
    var formatBox = $("#composer-format");
    if (!tierBox || !formatBox) return;

    TIERS.forEach(function (tier) {
      var btn = make("button", null, tier.label);
      btn.type = "button";
      btn.dataset.tier = tier.key;
      btn.setAttribute("aria-pressed", String(state.composer.tier === tier.key));
      btn.addEventListener("click", function () {
        state.composer.tier = tier.key;
        syncComposerControls();
        updateComposer();
      });
      tierBox.appendChild(btn);
    });

    FORMATS.forEach(function (format) {
      var btn = make("button", null, format.label);
      btn.type = "button";
      btn.dataset.format = format.key;
      btn.setAttribute("aria-pressed", String(state.composer.format === format.key));
      btn.addEventListener("click", function () {
        if (btn.disabled) return;
        state.composer.format = format.key;
        syncComposerControls();
        updateComposer();
      });
      formatBox.appendChild(btn);
    });

    $all("#composer-route button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.composer.route = btn.dataset.route;
        syncComposerControls();
        updateComposer();
      });
    });
  }

  function syncComposerControls() {
    $all("#composer-tier button").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.dataset.tier === state.composer.tier));
    });
    $all("#composer-route button").forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(btn.dataset.route === state.composer.route));
    });
    var block = getTier(state.composer.tier);
    var files = block && block.files ? block.files : {};
    $all("#composer-format button").forEach(function (btn) {
      var available = !!(files[btn.dataset.format] || files[btn.dataset.format + "_mirror"]);
      btn.disabled = !available;
      btn.title = available ? "" : "این قالب در این دور منتشر نشده است";
      btn.setAttribute("aria-pressed", String(btn.dataset.format === state.composer.format));
    });
  }

  function updateComposer() {
    var block = getTier(state.composer.tier);
    var files = block && block.files ? block.files : null;
    var format = state.composer.format;
    var route = state.composer.route;
    var key = format + (route === "mirror" ? "_mirror" : "");
    var url = files ? safeUrl(files[key]) : null;
    var note = $("#composer-note");
    var out = $("#composer-url");
    var copyBtn = $("#composer-copy");
    var openBtn = $("#composer-open");

    if (files && !url && route === "mirror") {
      url = safeUrl(files[format]);
    }
    state.composer.url = url;

    if (out) out.textContent = url || "—";
    if (copyBtn) copyBtn.disabled = !url;
    if (openBtn) {
      if (url) {
        openBtn.href = url;
        openBtn.removeAttribute("aria-disabled");
      } else {
        openBtn.href = "#";
        openBtn.setAttribute("aria-disabled", "true");
      }
    }

    var countEl = $("#composer-count");
    if (countEl) {
      var tierLabel = TIERS.filter(function (t) { return t.key === state.composer.tier; })[0];
      countEl.textContent = block
        ? fmt(block.unique) + " کانفیگ · " + (tierLabel ? tierLabel.label : state.composer.tier)
        : "—";
    }

    if (note) {
      var parts = [];
      if (!url) {
        parts.push("این ترکیب در دادهٔ فعلی موجود نیست.");
      } else if (route === "mirror") {
        parts.push("آینهٔ jsDelivr کشِ بلندتری دارد؛ برای تازگی، مسیرِ اصلی را ترجیح بده.");
      } else {
        parts.push("مسیرِ اصلیِ raw کشِ کوتاه‌تری دارد (حدودِ ۵ دقیقه).");
      }
      if (state.composer.tier === "fast") {
        var threshold = getThreshold();
        parts.push(threshold ? "آستانهٔ سریع در این اجرا: " + fmt(threshold) + " میلی‌ثانیه." : "آستانهٔ سریع در گزارشِ همین اجرا تعریف می‌شود.");
      }
      if (state.composer.tier === "secure") {
        parts.push("شرطِ امن: forward secrecy و بدونِ غیرفعال‌کردنِ اعتبارسنجیِ گواهی.");
      }
      note.textContent = parts.join(" ");
    }
    syncComposerControls();
  }

  function getThreshold() {
    try {
      var n = Number(state.health.cascade.buckets.fast_threshold_ms);
      return isFinite(n) && n > 0 ? n : null;
    } catch (e) {
      return null;
    }
  }

  function setupComposerActions() {
    var copyBtn = $("#composer-copy");
    var openBtn = $("#composer-open");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        if (state.composer.url) copyText(state.composer.url, copyBtn);
      });
    }
    if (openBtn) {
      openBtn.addEventListener("click", function (ev) {
        if (!state.composer.url) ev.preventDefault();
      });
    }
  }

  /* ── کشورها ───────────────────────────────────────────────────────────── */

  function countryUrl(file) {
    var path = String(file || "").replace(/^\/+/, "");
    if (!path) return null;
    var primary = state.primary || RAW_BASE;
    return safeUrl(primary.replace(/\/+$/, "") + "/" + path);
  }

  function renderCountries() {
    var list = $("#country-grid");
    if (!list) return;
    var items = (state.countries || []).slice().sort(function (a, b) { return b.count - a.count; });
    var query = normalize(state.countryQuery);
    var matches = items.filter(function (item) {
      if (!query) return true;
      return normalize(countryName(item)).indexOf(query) !== -1 ||
        normalize(item.name).indexOf(query) !== -1 ||
        normalize(item.code).indexOf(query) !== -1;
    });
    var visible = query || state.countryExpanded ? matches : matches.slice(0, 12);

    list.innerHTML = "";
    visible.forEach(function (item) {
      var li = make("li", "country");
      var code = make("span", "country-cc", ccOf(item.code) || "··");
      code.setAttribute("aria-hidden", "true");
      li.appendChild(code);
      li.appendChild(make("span", "country-name", countryName(item)));
      li.appendChild(make("span", "country-count", fmt(item.count)));
      var actions = make("div", "country-actions");
      var url = countryUrl(item.file);
      if (url) {
        var copyBtn = make("button", "icon-btn");
        copyBtn.type = "button";
        copyBtn.dataset.copyValue = url;
        copyBtn.setAttribute("aria-label", "کپیِ لینکِ " + countryName(item));
        copyBtn.title = "کپیِ لینک";
        copyBtn.appendChild(icon("copy"));
        actions.appendChild(copyBtn);

        var open = make("a", "icon-btn");
        open.href = url;
        open.target = "_blank";
        open.rel = "noopener";
        open.setAttribute("aria-label", "باز کردنِ فایلِ " + countryName(item));
        open.title = "باز کردن";
        open.appendChild(icon("external"));
        actions.appendChild(open);
      }
      li.appendChild(actions);
      list.appendChild(li);
    });

    var empty = $("#country-empty");
    if (empty) empty.hidden = matches.length > 0;
    var countEl = $("#country-count");
    if (countEl) {
      countEl.textContent = query
        ? fmt(matches.length) + " از " + fmt(items.length) + " کشور"
        : fmt(items.length) + " کشور · " + fmt(items.reduce(function (sum, c) { return sum + (Number(c.count) || 0); }, 0)) + " کانفیگ";
    }

    var toggle = $("#country-toggle");
    if (toggle) {
      var needed = !query && items.length > 12;
      toggle.hidden = !needed;
      if (needed) {
        toggle.textContent = state.countryExpanded ? "نمایشِ کمتر" : "نمایشِ همهٔ کشورها";
        toggle.setAttribute("aria-expanded", String(state.countryExpanded));
      }
    }
    list.setAttribute("aria-busy", "false");
  }

  function renderCountrySkeleton() {
    var list = $("#country-grid");
    if (!list) return;
    list.innerHTML = "";
    for (var i = 0; i < 6; i++) {
      var li = make("li", "country");
      var sk = make("span", "sk");
      sk.style.width = "100%";
      sk.style.height = "14px";
      li.appendChild(sk);
      list.appendChild(li);
    }
  }

  function loadCountries() {
    var c = state.index && state.index.countries;
    if (!c) { finishCountriesError(); return; }
    renderCountrySkeleton();
    fetchFrom(c.index, c.index_mirror, "json").then(function (res) {
      var data = res.data;
      if (!data || !Array.isArray(data.countries)) throw new Error("countries نامعتبر است");
      state.countries = data.countries;
      state.countrySource = res.source;
      renderCountries();
    }).catch(function (err) {
      console.error("[گذرگاه] countries", err);
      finishCountriesError();
    });
  }

  function finishCountriesError() {
    var list = $("#country-grid");
    if (list) {
      list.innerHTML = "";
      var li = make("li", "empty-note", "فهرستِ کشورها در این لحظه خوانده نشد.");
      li.style.gridColumn = "1 / -1";
      list.appendChild(li);
      list.setAttribute("aria-busy", "false");
    }
    var empty = $("#country-empty");
    if (empty) empty.hidden = true;
    var countEl = $("#country-count");
    if (countEl) countEl.textContent = "—";
    var toggle = $("#country-toggle");
    if (toggle) toggle.hidden = true;
  }

  /* ── پروتکل‌ها ────────────────────────────────────────────────────────── */

  function renderProtocols() {
    var list = $("#protocol-list");
    if (!list) return;
    var protocols = (state.index && state.index.protocols) || {};
    var files = (state.index && state.index.protocol_files) || {};
    var files64 = (state.index && state.index.protocol_files_base64) || {};
    var entries = Object.keys(protocols)
      .filter(function (name) { return Number(protocols[name]) > 0; })
      .sort(function (a, b) { return protocols[b] - protocols[a]; });
    var max = entries.length ? Number(protocols[entries[0]]) : 0;

    list.innerHTML = "";
    entries.forEach(function (name) {
      var li = make("li", "protocol");
      li.appendChild(make("span", "protocol-name", name.toUpperCase()));
      var bar = make("span", "protocol-bar");
      var fill = make("i");
      fill.style.setProperty("--w", "0%");
      bar.appendChild(fill);
      li.appendChild(bar);
      li.appendChild(make("span", "protocol-count", fmt(protocols[name])));
      var actions = make("div", "protocol-actions");
      var url = safeUrl(files[name]);
      var url64 = safeUrl(files64[name]);
      if (url) {
        var copy = make("button", "micro-btn");
        copy.type = "button";
        copy.dataset.copyValue = url;
        copy.setAttribute("aria-label", "کپیِ لینکِ " + name);
        copy.title = "کپیِ متن";
        copy.appendChild(icon("copy"));
        copy.appendChild(make("span", null, "TXT"));
        actions.appendChild(copy);
      }
      if (url64) {
        var copy64 = make("button", "micro-btn");
        copy64.type = "button";
        copy64.dataset.copyValue = url64;
        copy64.setAttribute("aria-label", "کپیِ Base64 برای " + name);
        copy64.title = "کپیِ Base64";
        copy64.appendChild(icon("copy"));
        copy64.appendChild(make("span", null, "B64"));
        actions.appendChild(copy64);
      }
      li.appendChild(actions);
      list.appendChild(li);
      if (max) {
        var share = Math.max(1.5, (Number(protocols[name]) / max) * 100);
        requestAnimationFrame(function () { fill.style.setProperty("--w", share.toFixed(2) + "%"); });
      }
    });

    if (!entries.length) {
      var note = make("li", "empty-note", "در این دور هیچ کانفیگی از پروتکل‌ها ثبت نشده است.");
      note.style.listStyle = "none";
      list.appendChild(note);
    }
    list.setAttribute("aria-busy", "false");
  }

  /* ── ۱۰۰ برتر ─────────────────────────────────────────────────────────── */

  function decodeBase64Utf8(text) {
    try {
      var clean = String(text || "").replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
      var pad = (4 - (clean.length % 4)) % 4;
      var bin = atob(clean + "=".repeat(pad));
      var bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new TextDecoder("utf-8").decode(bytes);
    } catch (e) {
      return "";
    }
  }

  function remarkOf(line) {
    var hash = line.indexOf("#");
    if (hash !== -1) {
      try {
        return decodeURIComponent(line.slice(hash + 1));
      } catch (e) {
        return line.slice(hash + 1);
      }
    }
    if (line.indexOf("vmess://") === 0) {
      var json = decodeBase64Utf8(line.slice(8));
      if (json) {
        try {
          var obj = JSON.parse(json);
          if (obj && typeof obj.ps === "string") return obj.ps;
        } catch (e) { /* ignore */ }
      }
    }
    return "";
  }

  function cleanLabel(raw, proto) {
    var text = String(raw || "")
      .replace(/\s*\|\s*@Goodbaye_filtering\s*\|\s*/gi, " · ")
      .replace(/\s*\|\s*/g, " · ")
      .replace(/[\u{1F1E6}-\u{1F1FF}]/gu, "")
      .replace(/\s+/g, " ")
      .trim();
    return text || proto.toUpperCase();
  }

  function splitCountry(text) {
    var m = String(text || "").match(/^([A-Za-z]{2})(?:\s*[·•|:\-–]\s*|\s+)/u);
    if (!m) return { code: "", label: String(text || "").trim() };
    var rest = String(text).slice(m[0].length).trim();
    return rest ? { code: m[1].toUpperCase(), label: rest } : { code: "", label: String(text || "").trim() };
  }

  function renderTop100() {
    var list = $("#top100-list");
    if (!list) return;
    var lines = (state.top100 || []).slice(0, 100);
    var visible = state.top100Expanded ? lines : lines.slice(0, 10);
    list.innerHTML = "";
    visible.forEach(function (line, i) {
      var proto = (line.split("://")[0] || "").replace(/[^a-z0-9]/gi, "").toLowerCase();
      var li = make("li", "top-item");
      var parts = splitCountry(cleanLabel(remarkOf(line), proto));
      li.appendChild(make("span", "top-rank", fmt(i + 1)));
      li.appendChild(make("span", "top-proto", proto || "—"));
      var label = make("span", "top-label");
      if (parts.code) label.appendChild(make("span", "top-cc", parts.code));
      label.appendChild(make("span", "top-name", parts.label));
      li.appendChild(label);
      var copy = make("button", "icon-btn");
      copy.type = "button";
      copy.dataset.copyValue = line;
      copy.setAttribute("aria-label", "کپیِ کانفیگِ ردیفِ " + fmt(i + 1));
      copy.title = "کپیِ کانفیگ";
      copy.appendChild(icon("copy"));
      li.appendChild(copy);
      list.appendChild(li);
    });
    var meta = $("#top100-meta");
    if (meta) meta.textContent = fmt(lines.length) + " مورد · مرتب بر اساسِ میانهٔ تأخیر";
    var empty = $("#top100-empty");
    if (empty) empty.hidden = lines.length > 0;
    var toggle = $("#top100-toggle");
    if (toggle) {
      toggle.hidden = lines.length <= 10;
      toggle.textContent = state.top100Expanded ? "نمایشِ کمتر" : "نمایشِ همهٔ " + fmt(lines.length);
      toggle.setAttribute("aria-expanded", String(state.top100Expanded));
    }
    list.setAttribute("aria-busy", "false");
  }

  function loadTop100() {
    var top = state.index && state.index.top100;
    if (!top) return;
    var list = $("#top100-list");
    if (list) {
      list.innerHTML = "";
      var loading = make("li", "empty-note", "در حال خواندنِ فهرست…");
      loading.style.gridColumn = "1 / -1";
      list.appendChild(loading);
    }
    fetchFrom(top.url, top.url_mirror, "text").then(function (res) {
      var lines = String(res.data || "").split(/\r?\n/).map(function (line) {
        return line.trim();
      }).filter(function (line) {
        return line && line.charAt(0) !== "#" && line.indexOf("://") !== -1;
      });
      state.top100 = lines;
      renderTop100();
    }).catch(function (err) {
      console.error("[گذرگاه] top100", err);
      if (list) {
        list.innerHTML = "";
        var note = make("li", "empty-note", "فهرستِ ۱۰۰ برتر در این لحظه خوانده نشد؛ از دکمهٔ کپیِ بالای صفحه استفاده کن.");
        note.style.gridColumn = "1 / -1";
        list.appendChild(note);
        list.setAttribute("aria-busy", "false");
      }
      var empty = $("#top100-empty");
      if (empty) empty.hidden = false;
    });
  }

  /* ── سلامت و شفافیت ───────────────────────────────────────────────────── */

  function renderHealth() {
    var health = state.health;
    if (!health) return;
    var summary = health.summary || {};
    var total = Number(summary.total) || 0;
    var ok = Number(summary.ok) || 0;
    setText("health-sources-count", total ? fmt(ok) + " از " + fmt(total) : "—");

    var l3 = health.cascade && health.cascade.layers ? health.cascade.layers.l3 : null;
    setText("health-flaky", l3 && isFinite(Number(l3.flaky_pct)) ? pct(l3.flaky_pct) : "—");
    setText("health-duration", fmtDuration(health.cascade ? health.cascade.total_seconds : health.elapsed_seconds));

    var exit = health.cascade ? health.cascade.exit_country : null;
    if (exit && exit.loc) {
      var name = regionName(exit.loc);
      setText("health-exit", (name + (exit.colo ? " · " + exit.colo : "")).trim());
    } else {
      setText("health-exit", "نامعلوم");
    }

    var threshold = getThreshold();
    if (threshold) {
      setText("fast-threshold", fmt(threshold) + " میلی‌ثانیه");
      var note = $("#ladder-note");
      if (note) {
        note.textContent = "آستانهٔ «سریع» در این اجرا " + fmt(threshold) + " میلی‌ثانیه بود؛ درصدِ هر پله نسبت به استخرِ یکتای همین اجرا سنجیده می‌شود.";
      }
    }

    renderLayers(health);
    renderSources(health);
    renderConverters(health);
  }

  function renderLayers(health) {
    var list = $("#health-layers");
    if (!list) return;
    var layers = health.cascade ? health.cascade.layers : null;
    list.innerHTML = "";
    if (!layers) {
      var note = make("li", "empty-note", "گزارشِ لایه‌ها در این اجرا ثبت نشده است.");
      note.style.listStyle = "none";
      list.appendChild(note);
      list.setAttribute("aria-busy", "false");
      return;
    }
    var definitions = [
      { key: "l0_l1", name: "غربالِ ساختاری · L0/L1", hint: "تجزیه، اعتبارسنجی و یکتاسازی" },
      { key: "l2", name: "دست‌دادنِ TCP · L2", hint: "باز بودنِ مسیر تا سرور" },
      { key: "l3", name: "ترافیکِ واقعی · L3", hint: "عبورِ درخواست از داخلِ پروکسی" }
    ];
    definitions.forEach(function (def) {
      var data = layers[def.key];
      if (!data) return;
      var input = Number(data.unique) || Number(data.in) || 0;
      if (def.key === "l0_l1") input = Number(data.in) || 0;
      var output = def.key === "l3" ? Number(data.stable) || 0 : Number(data.out) || 0;
      var share = input ? Math.min(100, (output / input) * 100) : 0;

      var li = make("li", "layer");
      var top = make("div", "layer-top");
      top.appendChild(make("span", "layer-name", def.name));
      top.appendChild(make("span", "layer-flow", "ورودی " + fmt(input) + " · خروجی " + fmt(output)));
      li.appendChild(top);
      var bar = make("div", "layer-bar");
      var fill = make("i");
      fill.style.setProperty("--w", "0%");
      bar.appendChild(fill);
      li.appendChild(bar);

      var noteText = def.hint + " · ";
      if (def.key === "l0_l1") {
        var dropped = data.dropped || {};
        var reasons = Object.keys(dropped).filter(function (k) { return Number(dropped[k]) > 0; })
          .sort(function (a, b) { return dropped[b] - dropped[a]; }).slice(0, 3)
          .map(function (k) { return (REASON_FA[k] || k) + " " + fmt(dropped[k]); });
        noteText += reasons.length ? "حذف‌شده: " + reasons.join("، ") : "چیزی حذف نشد";
      } else if (def.key === "l2") {
        noteText += "باز بودن " + pct(data.open_pct);
        if (Number(data.dns_failed) > 0) noteText += " · DNS ناموفق " + fmt(data.dns_failed);
      } else {
        var rounds = data.per_run_ok || [];
        noteText += "دورها " + fmt(rounds.length || data.rounds || 0);
        if (rounds.length) noteText += " · در هر دور " + rounds.map(fmt).join("، ");
        if (Number(data.flaky_pct) > 0) noteText += " · لرزان " + pct(data.flaky_pct);
      }
      li.appendChild(make("p", "layer-note", noteText));
      list.appendChild(li);
      requestAnimationFrame(function () { fill.style.setProperty("--w", share.toFixed(2) + "%"); });
    });
    list.setAttribute("aria-busy", "false");
  }

  function renderSources(health) {
    var table = $("#health-sources");
    if (!table) return;
    var tbody = table.querySelector("tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    var sources = (health.sources || []).slice().sort(function (a, b) {
      var rank = { fail: 0, empty: 1, unknown: 2, disabled: 3, ok: 4 };
      var ra = rank[a.status] === undefined ? 5 : rank[a.status];
      var rb = rank[b.status] === undefined ? 5 : rank[b.status];
      return ra - rb;
    });
    sources.forEach(function (src) {
      var tr = document.createElement("tr");
      var tdSource = document.createElement("td");
      tdSource.className = "source";
      tdSource.dataset.label = "منبع";
      var host = make("span", "source-host");
      var urlText = src.url || "";
      try {
        var u = new URL(urlText);
        host.textContent = u.hostname + u.pathname;
      } catch (e) {
        host.textContent = urlText;
      }
      host.title = urlText;
      tdSource.appendChild(host);
      tr.appendChild(tdSource);

      var tdTier = make("td", "source-tier", TIER_FA[src.tier] || src.tier || "—");
      tdTier.dataset.label = "لایه";
      tr.appendChild(tdTier);

      var tdStatus = document.createElement("td");
      tdStatus.dataset.label = "وضعیت";
      var badge = make("span", "status-badge");
      badge.dataset.status = src.status || "unknown";
      badge.appendChild(make("span", null, STATUS_FA[src.status] || src.status || "نامعلوم"));
      tdStatus.appendChild(badge);
      if (src.http_code) tdStatus.title = "HTTP " + src.http_code;
      tr.appendChild(tdStatus);

      var tdCount = make("td", "num", fmt(src.count || 0));
      tdCount.dataset.label = "کانفیگ";
      tr.appendChild(tdCount);

      var tdLatency = make("td", "num", src.latency_ms !== undefined && src.latency_ms !== null ? fmt(src.latency_ms) : "—");
      tdLatency.dataset.label = "تأخیر · ms";
      tr.appendChild(tdLatency);

      tbody.appendChild(tr);
    });
    if (!sources.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 5;
      td.className = "empty-note";
      td.textContent = "گزارشی از منابع ثبت نشده است.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
    table.setAttribute("aria-busy", "false");
  }

  function renderConverters(health) {
    var box = $("#health-converters");
    if (!box) return;
    box.innerHTML = "";
    var converters = health.converters || {};
    var entries = Object.keys(converters).filter(function (key) {
      return key === "clash" || key === "singbox";
    });
    if (!entries.length) {
      var note = make("p", "empty-note", "گزارشِ مبدل‌ها در این اجرا ثبت نشده است.");
      note.style.gridColumn = "1 / -1";
      box.appendChild(note);
      return;
    }
    entries.forEach(function (key) {
      var data = converters[key] || {};
      var card = make("div", "converter");
      card.appendChild(make("h4", null, key === "clash" ? "Clash / mihomo" : "Sing-box"));
      card.appendChild(make("span", "converter-total", fmt(data.total || 0) + " کانفیگ در این قالب قابلِ بیان نبود"));
      var reasons = data.by_reason || {};
      var keys = Object.keys(reasons).filter(function (k) { return Number(reasons[k]) > 0; })
        .sort(function (a, b) { return reasons[b] - reasons[a]; });
      var max = keys.length ? Number(reasons[keys[0]]) : 0;
      var ul = document.createElement("ul");
      keys.forEach(function (reason) {
        var li = document.createElement("li");
        var left = document.createElement("div");
        left.appendChild(make("span", null, REASON_FA[reason] || reason));
        var bar = make("div", "reason-bar");
        var fill = make("i");
        fill.style.setProperty("--w", max ? ((Number(reasons[reason]) / max) * 100).toFixed(2) + "%" : "0%");
        bar.appendChild(fill);
        left.appendChild(bar);
        li.appendChild(left);
        li.appendChild(make("span", "num", fmt(reasons[reason])));
        ul.appendChild(li);
      });
      card.appendChild(ul);
      var protocols = data.by_protocol || {};
      var protoKeys = Object.keys(protocols).filter(function (k) { return Number(protocols[k]) > 0; })
        .sort(function (a, b) { return protocols[b] - protocols[a]; }).slice(0, 3);
      if (protoKeys.length) {
        card.appendChild(make("p", "converter-total", "بیشترین: " + protoKeys.map(function (k) {
          return k.toUpperCase() + " " + fmt(protocols[k]);
        }).join(" · ")));
      }
      box.appendChild(card);
    });
  }

  function loadHealth() {
    var s = state.index && state.index.sources;
    if (!s || !s.health_url) { renderHealthError(); return; }
    fetchFrom(s.health_url, s.health_url_mirror, "json").then(function (res) {
      state.health = res.data;
      renderHealth();
    }).catch(function (err) {
      console.error("[گذرگاه] health", err);
      renderHealthError();
    });
  }

  function renderHealthError() {
    setText("health-sources-count", "—");
    setText("health-flaky", "—");
    setText("health-duration", "—");
    setText("health-exit", "—");
    var list = $("#health-layers");
    if (list) {
      list.innerHTML = "";
      var li = make("li", "empty-note", "گزارشِ سلامت در این لحظه خوانده نشد؛ لینکِ health.json در دسترس است.");
      li.style.listStyle = "none";
      list.appendChild(li);
      list.setAttribute("aria-busy", "false");
    }
    var table = $("#health-sources");
    if (table) {
      var tbody = table.querySelector("tbody");
      if (tbody) {
        tbody.innerHTML = "";
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = 5;
        td.className = "empty-note";
        td.textContent = "فهرستِ منابع در دسترس نیست.";
        tr.appendChild(td);
        tbody.appendChild(tr);
      }
      table.setAttribute("aria-busy", "false");
    }
    var box = $("#health-converters");
    if (box) {
      box.innerHTML = "";
      var note = make("p", "empty-note", "گزارشِ مبدل‌ها در دسترس نیست.");
      note.style.gridColumn = "1 / -1";
      box.appendChild(note);
    }
  }

  /* ── راهنمای اتصال ────────────────────────────────────────────────────── */

  function guideButton(label, url) {
    if (!safeUrl(url)) return null;
    var btn = make("button", "chip");
    btn.type = "button";
    btn.dataset.copyValue = url;
    btn.setAttribute("aria-label", "کپیِ " + label);
    btn.appendChild(icon("copy"));
    btn.appendChild(make("span", null, label));
    return btn;
  }

  function renderGuide() {
    var verified = getTier("verified");
    if (!verified || !verified.files) return;
    var files = verified.files;
    var maps = {
      hiddify: [guideButton("Base64", files.configs_base64), guideButton("متن", files.configs_txt), makeChip("آینه", files.configs_base64_mirror, "external")],
      clash: [guideButton("clash.yaml", files.clash_yaml), makeChip("باز کردن", files.clash_yaml, "external")],
      singbox: [guideButton("singbox.json", files.singbox_json), makeChip("باز کردن", files.singbox_json, "external")]
    };
    Object.keys(maps).forEach(function (key) {
      var box = document.querySelector('[data-guide-links="' + key + '"]');
      if (!box) return;
      box.innerHTML = "";
      maps[key].forEach(function (el) { if (el) box.appendChild(el); });
    });
  }

  /* ── QR ───────────────────────────────────────────────────────────────── */

  function openQr(key) {
    var item = QR[key];
    var dialog = $("#qr-dialog");
    if (!item || !dialog) return;
    state.qrUrl = item.url;
    var img = $("#qr-img");
    if (img) {
      img.src = item.src;
      img.alt = "کیوآرکدِ " + item.title;
    }
    setText("qr-title", item.title);
    setText("qr-url", item.url);
    var open = $("#qr-open");
    if (open) open.href = item.url;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function setupQr() {
    document.addEventListener("click", function (ev) {
      var trigger = ev.target.closest("[data-qr]");
      if (trigger) {
        ev.preventDefault();
        openQr(trigger.dataset.qr);
      }
    });
    var copy = $("#qr-copy");
    if (copy) {
      copy.addEventListener("click", function () {
        if (state.qrUrl) copyText(state.qrUrl, copy);
      });
    }
    var dialog = $("#qr-dialog");
    if (dialog) {
      dialog.addEventListener("click", function (ev) {
        if (ev.target === dialog) dialog.close();
      });
    }
  }

  /* ── پوسته و تعامل‌های سراسری ─────────────────────────────────────────── */

  function setupTheme() {
    var btn = $("#theme-toggle");
    if (!btn) return;
    function apply(theme) {
      document.documentElement.dataset.theme = theme;
      btn.setAttribute("aria-pressed", String(theme === "dark"));
      btn.setAttribute("aria-label", theme === "dark" ? "تغییر به پوستهٔ روشن" : "تغییر به پوستهٔ تیره");
    }
    apply(document.documentElement.dataset.theme || "light");
    btn.addEventListener("click", function () {
      var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      apply(next);
      try { localStorage.setItem("passage-theme", next); } catch (e) { /* ignore */ }
    });
  }

  function setupCopy() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-copy-value], [data-copy-text]");
      if (!btn) return;
      var value = btn.dataset.copyValue || btn.dataset.copyText;
      if (value) {
        ev.preventDefault();
        copyText(value, btn);
      }
    });
  }

  function setupCountriesUi() {
    var search = $("#country-search");
    if (search) {
      var timer = null;
      search.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          state.countryQuery = search.value;
          if (state.countries) renderCountries();
        }, 120);
      });
    }
    var toggle = $("#country-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        state.countryExpanded = !state.countryExpanded;
        renderCountries();
      });
    }
    var topToggle = $("#top100-toggle");
    if (topToggle) {
      topToggle.addEventListener("click", function () {
        state.top100Expanded = !state.top100Expanded;
        renderTop100();
      });
    }
  }

  function setupReveal() {
    var nodes = $all(".reveal");
    if (!nodes.length) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof IntersectionObserver === "undefined") {
      nodes.forEach(function (node) { node.classList.add("in"); });
      return;
    }
    document.body.classList.add("reveal-ready");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    nodes.forEach(function (node) { observer.observe(node); });
  }

  /* ── راه‌اندازی داده ──────────────────────────────────────────────────── */

  function applyIndex(index, source) {
    state.index = index;
    state.source = source;
    state.primary = index.primary_base || RAW_BASE;
    state.mirror = index.mirror_base || CDN_BASE;
    state.loaded = true;

    if (index.top100 && safeUrl(index.top100.url)) QR.top100.url = index.top100.url;
    var verified = getTier("verified");
    var fast = getTier("fast");
    var secure = getTier("secure");
    var all = getTier("all");
    if (verified && verified.files) {
      QR.verified.url = verified.files.configs_base64 || QR.verified.url;
    }
    if (fast && fast.files) QR.fast.url = fast.files.configs_base64 || QR.fast.url;
    if (secure && secure.files) QR.secure.url = secure.files.configs_base64 || QR.secure.url;
    if (all && all.files) QR.all.url = all.files.configs_base64 || QR.all.url;

    guard("hero", renderHero);
    guard("freshness", updateFreshness);
    guard("routes", renderRoutes);
    guard("ladder", renderLadder);
    guard("composer", function () {
      buildComposerControls();
      syncComposerControls();
      updateComposer();
    });
    guard("protocols", renderProtocols);
    guard("guide", renderGuide);
    guard("countries", loadCountries);
    guard("top100", loadTop100);
    guard("health", loadHealth);
  }

  function showFatal(err) {
    console.error("[گذرگاه] index", err);
    setStatus("error", "اتصال به داده برقرار نشد");
    var banner = $("#stale-banner");
    var bannerText = $("#stale-text");
    if (banner && bannerText) {
      banner.hidden = false;
      bannerText.textContent = "خواندنِ index.json از مسیرِ اصلی و آینه ممکن نشد. صفحه ساختارش را حفظ کرده، ولی دادهٔ زنده در دسترس نیست.";
    }
    var grid = $("#route-grid");
    if (grid) {
      grid.innerHTML = "";
      grid.appendChild(fatalCard("اتصال به index.json برقرار نشد. اتصالِ شبکه را بررسی کن یا دوباره تلاش کن."));
      grid.setAttribute("aria-busy", "false");
    }
    ["stat-unique", "stat-verified", "stat-countries", "stat-top100", "pass-verified",
      "health-sources-count", "health-flaky", "health-duration", "health-exit"].forEach(function (id) {
      setText(id, "—");
    });
    var stats = $("#hero-stats");
    if (stats) stats.setAttribute("aria-busy", "false");
    setText("pass-updated", "داده در دسترس نیست");
    setText("foot-meta", "خواندنِ index.json ممکن نشد.");
    var ladder = $("#ladder");
    if (ladder) ladder.setAttribute("aria-busy", "false");
    var composerNote = $("#composer-note");
    if (composerNote) composerNote.textContent = "برای ساختنِ لینک، ابتدا باید index.json خوانده شود.";
    var copy = $("#composer-copy");
    if (copy) copy.disabled = true;
    var topList = $("#top100-list");
    if (topList) {
      topList.innerHTML = "";
      topList.setAttribute("aria-busy", "false");
    }
    var empty = $("#top100-empty");
    if (empty) empty.hidden = false;
    renderCountrySkeleton();
    finishCountriesError();
    renderHealthError();
  }

  function initData() {
    setStatus("loading", "در حال خواندنِ دادهٔ زنده…");
    var banner = $("#stale-banner");
    if (banner) banner.hidden = true;
    fetchIndex().then(function (res) {
      applyIndex(res.data, res.source);
    }).catch(function (err) {
      showFatal(err);
    });
  }

  function init() {
    setupTheme();
    setupCopy();
    setupQr();
    setupCountriesUi();
    setupComposerActions();
    setupReveal();
    initData();
    setInterval(function () {
      if (state.index) updateFreshness();
    }, 60000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
