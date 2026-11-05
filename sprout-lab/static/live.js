// Live prices shared by every SPROUT page: one quote store polled every 10s, a scrolling price strip,
// price flashes when a quote changes, a market-session chip and "updated Xs ago" counters.
// Prices are real (Yahoo, including pre-market and after-hours); nothing here is simulated.
(function () {
  "use strict";
  var Q = {}, watched = {}, asOf = 0, session = "", POLL = 10000;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var SESS = {
    pre: ["Pre-market", "#e5b25b"], regular: ["Market open", "#2fbf71"], post: ["After hours", "#e5b25b"],
    overnight: ["Overnight", "#7f9bef"], weekend: ["Weekend", "#9aa7b6"]
  };
  var usd = function (v) { return "$" + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
  var chg = function (q) { return q && q.prevClose ? q.price / q.prevClose - 1 : 0; };
  var pct = function (v) { var s = Math.abs(v * 100).toFixed(2); return (+s === 0 ? "" : v > 0 ? "+" : "−") + s + "%"; };

  function label(s) { return (SESS[s] || ["Live", "#2fbf71"])[0]; }
  function note(s) {
    return s === "regular" ? "US market open" : s === "pre" ? "Pre-market trading" : s === "post" ? "After-hours trading"
      : s === "overnight" ? "Last US trade shown · pre-market opens 4am New York" : s === "weekend" ? "Markets reopen Sunday 8pm New York" : "";
  }
  function ago(t) { if (!t) return "…"; var s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 60 ? s + "s ago" : s < 3600 ? Math.floor(s / 60) + "m ago" : Math.floor(s / 3600) + "h ago"; }

  function poll() {
    var syms = Object.keys(watched); if (!syms.length) syms = ["SPY"]; // the session chip still needs a quote
    fetch("/api/prices?symbols=" + syms.join(",")).then(function (r) { return r.json(); }).then(function (j) {
      var changed = [];
      Object.keys(j.prices || {}).forEach(function (s) { var p = j.prices[s]; if (!p.price) return; var old = Q[s]; Q[s] = p; if (old && old.price !== p.price) changed.push([s, p.price > old.price ? 1 : -1]); if (p.session) session = p.session; });
      asOf = j.asOf; paint(changed);
      window.dispatchEvent(new CustomEvent("sprout:live", { detail: { prices: Q, changed: changed } }));
    }).catch(function () {});
  }
  function paint(changed) {
    document.querySelectorAll("[data-lv-p]").forEach(function (el) { var q = Q[el.dataset.lvP]; if (q) el.textContent = usd(q.price); });
    document.querySelectorAll("[data-lv-c]").forEach(function (el) { var q = Q[el.dataset.lvC]; if (!q) return; var c = chg(q); el.textContent = (c >= 0 ? "▲ " : "▼ ") + pct(c); el.className = "lv-c " + (c >= 0 ? "up" : "dn"); });
    (changed || []).forEach(function (x) { document.querySelectorAll('[data-lv-p="' + x[0] + '"], [data-lv-flash="' + x[0] + '"]').forEach(function (el) { flash(el, x[1]); }); });
    document.querySelectorAll("[data-lv-status]").forEach(function (el) { el.innerHTML = statusInner(); });
  }
  function flash(el, dir) { el.classList.remove("lv-fu", "lv-fd"); void el.offsetWidth; el.classList.add(dir > 0 ? "lv-fu" : "lv-fd"); }
  function statusInner() {
    var c = (SESS[session] || ["", "#2fbf71"])[1];
    return '<i class="lv-dot" style="background:' + c + ';box-shadow:0 0 0 0 ' + c + '"></i><b>' + (session ? label(session) : "Live") + '</b><span class="lv-ago" data-lv-ago>' + (asOf ? "updated " + ago(asOf) : "connecting…") + '</span>';
  }

  // items: [{ s: "AAPL", n: "Apple" }]; opts.tickers shows the symbol next to the name.
  function strip(items, opts) {
    opts = opts || {}; items.forEach(function (x) { watched[x.s] = 1; });
    var one = items.map(function (x) { var q = Q[x.s], c = chg(q);
      return '<span class="lv-i" data-lv-flash="' + x.s + '">' + (opts.logo ? opts.logo(x.s) : "") + '<span class="lv-n">' + x.n + (opts.tickers ? ' <small>' + x.s + '</small>' : "") + '</span><b class="lv-p" data-lv-p="' + x.s + '">' + (q ? usd(q.price) : "…") + '</b><span class="lv-c ' + (c >= 0 ? "up" : "dn") + '" data-lv-c="' + x.s + '">' + (q ? (c >= 0 ? "▲ " : "▼ ") + pct(c) : "") + '</span></span>'; }).join("");
    return '<div class="lv-strip' + (opts.dark ? " dark" : "") + '">' + (opts.status === false ? "" : '<span class="lv-status" data-lv-status title="' + note(session) + '">' + statusInner() + '</span>') +
      '<div class="lv-view"><div class="lv-track">' + one + one + '</div></div></div>';
  }
  function status() { return '<span class="lv-status" data-lv-status>' + statusInner() + '</span>'; }

  // One clock drives every strip, so a strip re-rendered by its page keeps its place instead of jumping.
  var SPEED = 38; // px per second
  function frame(now) {
    if (!reduce) document.querySelectorAll(".lv-track").forEach(function (t) { var w = t.scrollWidth / 2; if (w > 0) t.style.transform = "translateX(" + (-((now / 1000 * SPEED) % w)) + "px)"; });
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  setInterval(function () { document.querySelectorAll("[data-lv-ago]").forEach(function (el) { el.textContent = asOf ? "updated " + ago(asOf) : "connecting…"; }); }, 1000);

  var css = document.createElement("style");
  css.textContent = [
    ".lv-strip{display:flex;align-items:center;gap:0;overflow:hidden;border:1px solid rgba(0,30,65,.1);border-radius:10px;background:rgba(255,255,255,.7);font-size:.82rem;min-width:0}",
    ".lv-strip.dark{background:rgba(255,255,255,.04);border-color:rgba(255,255,255,.12);color:#e8eef7}",
    ".lv-status{display:inline-flex;align-items:center;gap:7px;padding:8px 12px;white-space:nowrap;border-right:1px solid rgba(0,30,65,.1);font-size:.76rem;flex:none}",
    ".lv-strip.dark .lv-status{border-color:rgba(255,255,255,.12)}",
    ".lv-status b{font-weight:700}.lv-ago{opacity:.65;font-variant-numeric:tabular-nums}",
    ".lv-dot{width:8px;height:8px;border-radius:50%;display:inline-block;animation:lvpulse 1.8s ease-out infinite}",
    "@keyframes lvpulse{0%{box-shadow:0 0 0 0 currentColor;opacity:1}70%{box-shadow:0 0 0 7px transparent;opacity:.7}100%{box-shadow:0 0 0 0 transparent;opacity:1}}",
    ".lv-view{overflow:hidden;flex:1;min-width:0;-webkit-mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}",
    ".lv-track{display:flex;width:max-content;will-change:transform}",
    ".lv-i{display:inline-flex;align-items:center;gap:7px;padding:8px 16px;white-space:nowrap;border-radius:6px}",
    ".lv-n{font-weight:600}.lv-n small{opacity:.55;font-weight:500;margin-left:2px}.lv-p{font-variant-numeric:tabular-nums;font-weight:600}",
    ".lv-c{font-size:.74rem;font-weight:600;font-variant-numeric:tabular-nums}.lv-c.up{color:#0a8f55}.lv-c.dn{color:#c8372d}",
    ".lv-strip.dark .lv-c.up{color:#5fd49b}.lv-strip.dark .lv-c.dn{color:#ff8a80}",
    ".lv-fu{animation:lvfu 1.3s ease-out}.lv-fd{animation:lvfd 1.3s ease-out}",
    "@keyframes lvfu{0%{background:rgba(47,191,113,.35)}100%{background:transparent}}@keyframes lvfd{0%{background:rgba(200,55,45,.3)}100%{background:transparent}}",
    "@media (prefers-reduced-motion:reduce){.lv-view{overflow-x:auto}.lv-dot{animation:none}.lv-fu,.lv-fd{animation:none}}"
  ].join("\n");
  document.head.appendChild(css);

  window.SproutLive = { strip: strip, status: status, watch: function (s) { s.forEach(function (x) { watched[x] = 1; }); }, get: function (s) { return Q[s]; },
    session: function () { return session; }, label: label, note: note, ago: ago, flash: flash, poll: poll };
  setTimeout(poll, 50); setInterval(poll, POLL);
})();
