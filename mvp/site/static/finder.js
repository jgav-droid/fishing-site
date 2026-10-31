// Trip finder. Progressive enhancement over server-rendered cards: re-evaluates recency,
// season windows and dated notices for the chosen trip date, adds straight-line distance,
// filters and sorts. State lives in the URL fragment (#...), so no crawlable parameter URLs.
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var form = $("finder"); if (!form) return;
  var RECENT = 30, MI = 1.609344;
  var places = JSON.parse($("places-data").textContent);
  var dataDate = form.getAttribute("data-data-date");
  var origin = null, originLabel = "";
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card[data-lake]"));
  cards.forEach(function (c) { c._d = JSON.parse(c.getAttribute("data-lake")); });

  function km(a, b, c, d) { var x = (a - c) * 111, y = (b - d) * 111 * Math.cos(a * Math.PI / 180); return Math.sqrt(x * x + y * y); }
  function day(s) { return new Date(s + "T12:00:00"); }
  function fmt(d) { return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
  function inWin(ws, t) { return ws.some(function (w) { return day(w.start) <= t && t <= day(w.end); }); }
  function findPlace(name) {
    name = (name || "").trim().toLowerCase(); if (!name) return null;
    for (var i = 0; i < places.length; i++) if (places[i][0].toLowerCase() === name) return places[i];
    return null;
  }

  function evaluate(card, trip) {
    var d = card._d, recent = [], total = 0, sp = {};
    d.catch.forEach(function (c) {
      var t = day(c[0]), age = (trip - t) / 864e5;
      if (age >= 0 && age <= RECENT) { recent.push(t); total += c[1]; sp[c[2].toLowerCase()] = 1; }
    });
    var rf = card.querySelector('[data-role="recent"]');
    if (rf) {
      var strong = rf.querySelector("strong");
      if (recent.length) {
        recent.sort(function (a, b) { return a - b; });
        var a = recent[0], b = recent[recent.length - 1];
        strong.textContent = total.toLocaleString() + " " + Object.keys(sp).join("/") + " · " + (a.getTime() === b.getTime() ? fmt(a) : fmt(a) + " – " + fmt(b));
        rf.className = "fact yes";
      } else {
        var past = d.catch.filter(function (c) { return day(c[0]) <= trip; });
        strong.textContent = "No catchable-size stocking reported in the 30 days before this date" + (past.length ? " (last: " + fmt(day(past[0][0])) + ")" : "");
        rf.className = "fact unknown";
      }
    }
    var blocking = false, visible = 0;
    d.windows.forEach(function (w, i) {
      var li = card.querySelector('[data-win="' + i + '"]'); if (!li) return;
      var inside = inWin(w.windows, trip), lvl, txt;
      if (w.season) { lvl = inside ? "ok" : w.out_level; txt = inside ? w.label_in : w.label_out; }
      else { lvl = inside ? w.in_level : "inactive"; txt = w.text; }
      var show = lvl === "blocking" || lvl === "warn";
      li.hidden = !show; li.className = "flag " + lvl + " cat-" + w.cat;
      li.querySelector(".t").textContent = txt;
      if (show) visible++; if (lvl === "blocking") blocking = true;
    });
    card.querySelectorAll(".flags li:not([data-win]):not([data-role])").forEach(function (li) { if (!li.hidden) visible++; });
    var nf = card.querySelector('[data-role="noflags"]'); if (nf) nf.hidden = visible > 0;
    var shoreOk = d.shore === "YES" || d.shore === "LIMITED";
    var why = card.querySelector('[data-role="why"]');
    var q = recent.length > 0 && shoreOk;
    if (why) why.textContent = q ? "Why it appears: catchable trout reported stocked within 30 days of this date; documented public shore access (" + d.shore.toLowerCase() + ")" : "";
    var dist = origin ? km(origin[0], origin[1], d.lat, d.lon) / MI : null;
    var ds = card.querySelector(".dist"); if (ds) ds.textContent = dist === null ? "" : " · ~" + Math.round(dist) + " mi straight-line";
    return { q: q, blocking: blocking, dist: dist, last: recent.length ? recent[recent.length - 1] : 0, shoreOk: shoreOk, dock: d.dock, restricted: d.restricted };
  }

  function run(trackIt) {
    var trip = day($("f-date").value || form.getAttribute("data-trip"));
    var p = findPlace($("f-place").value);
    if (p) { origin = [p[1], p[2]]; originLabel = p[0]; }
    else if (originLabel !== "your location") { origin = null; originLabel = ""; }
    var max = +$("f-max").value, shore = $("f-shore").checked, dock = $("f-dock").value, hide = $("f-hide-restricted").checked;
    var res = [], oth = [];
    cards.forEach(function (c) {
      var r = evaluate(c, trip); c._r = r;
      var ok = (!origin || r.dist <= max) && (!shore || r.shoreOk) && (dock !== "require" || r.dock === "YES") && !(hide && r.restricted);
      c.hidden = !ok;
      (r.q ? res : oth).push(c);
    });
    function cmp(a, b) {
      var x = a._r, y = b._r;
      if (x.blocking !== y.blocking) return x.blocking ? 1 : -1;
      if (dock === "prefer" && (x.dock === "YES") !== (y.dock === "YES")) return x.dock === "YES" ? -1 : 1;
      if (origin) return x.dist - y.dist;
      return (y.last || 0) - (x.last || 0);
    }
    res.sort(cmp); oth.sort(cmp);
    res.forEach(function (c) { $("results").appendChild(c); });
    oth.forEach(function (c) { $("others").appendChild(c); });
    var n = res.filter(function (c) { return !c.hidden; }).length;
    $("r-count").textContent = "(" + n + ")";
    var msg = n + " lake" + (n === 1 ? "" : "s") + " with recent catchable stocking and shore access for " +
      trip.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) +
      (origin ? " within " + (max >= 999 ? "any distance" : max + " straight-line mi") + " of " + originLabel : "") + ".";
    if (dataDate && trip > day(dataDate)) msg += " WDFW stocking data runs through " + fmt(day(dataDate)) + "; later plants are not yet known.";
    $("f-status").textContent = msg;
    var h = "from=" + encodeURIComponent(originLabel === "your location" ? "" : originLabel) + "&date=" + $("f-date").value + "&max=" + max +
      "&shore=" + (shore ? 1 : 0) + "&dock=" + dock + "&hide=" + (hide ? 1 : 0);
    try { history.replaceState(null, "", "#" + h); } catch (e) {}
    if (trackIt && window.track) window.track("trip_search", { origin: originLabel || "none", max_mi: max, shore: shore, dock: dock, results: n });
  }

  function restore() {
    var h = location.hash.replace(/^#/, ""); if (!h) return;
    h.split("&").forEach(function (kv) {
      var p = kv.split("="), v = decodeURIComponent(p[1] || "");
      if (p[0] === "from") $("f-place").value = v;
      if (p[0] === "date" && /^\d{4}-\d\d-\d\d$/.test(v)) $("f-date").value = v;
      if (p[0] === "max") $("f-max").value = v;
      if (p[0] === "shore") $("f-shore").checked = v === "1";
      if (p[0] === "dock") $("f-dock").value = v;
      if (p[0] === "hide") $("f-hide-restricted").checked = v === "1";
    });
  }

  var timer;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { run(true); }, 350); });
  form.addEventListener("change", function () { run(true); });
  $("f-geo").addEventListener("click", function () {
    if (!navigator.geolocation) { $("f-status").textContent = "Location is not available in this browser."; return; }
    $("f-status").textContent = "Finding your location (stays on your device)…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      origin = [pos.coords.latitude, pos.coords.longitude]; originLabel = "your location"; $("f-place").value = ""; run(true);
    }, function () { $("f-status").textContent = "Could not get your location. Type a town instead."; }, { maximumAge: 600000, timeout: 10000 });
  });
  restore(); run(false);
})();
