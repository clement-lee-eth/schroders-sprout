// One view switcher on every SPROUT page: website, app, admin console.
// Same corner everywhere; Alt+1 to Alt+3 jump between views. (/brief stays reachable by its address only.)
(function () {
  "use strict";
  if (window.top !== window || document.querySelector(".vsw")) return;
  var views = [["/", "Website", "What investors see first"], ["/app", "App", "The investor's SPROUT app"], ["/console", "Admin console", "Schroders portfolio managers"]];
  var p = location.pathname, cur = p.indexOf("/console") === 0 ? 2 : p.indexOf("/app") === 0 ? 1 : 0;
  var el = document.createElement("div");
  el.className = "vsw";
  el.innerHTML = '<div class="vsw-menu" role="menu" aria-label="Switch view" hidden>' + views.map(function (v, i) {
    return '<a role="menuitem" href="' + v[0] + '" class="' + (i === cur ? "on" : "") + '"' + (i === cur ? ' aria-current="page"' : "") + '><span><b>' + v[1] + '</b><small>' + v[2] + '</small></span><kbd>Alt ' + (i + 1) + '</kbd></a>';
  }).join("") + '</div><button type="button" class="vsw-btn" aria-expanded="false" aria-haspopup="menu"><span class="vsw-ic" aria-hidden="true">⇄</span><span>' + views[cur][1] + '</span></button>';
  document.body.appendChild(el);
  var btn = el.querySelector(".vsw-btn"), menu = el.querySelector(".vsw-menu");
  function set(open) { menu.hidden = !open; btn.setAttribute("aria-expanded", String(open)); }
  btn.addEventListener("click", function (e) { e.stopPropagation(); set(menu.hidden); });
  document.addEventListener("click", function (e) { if (!el.contains(e.target)) set(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") set(false);
    if (e.altKey && !e.metaKey && !e.ctrlKey && /^Digit[1-3]$/.test(e.code)) { var i = +e.code.slice(5) - 1; if (i !== cur) { e.preventDefault(); location.href = views[i][0]; } }
  });
})();
