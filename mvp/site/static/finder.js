// Trip finder. Progressive enhancement over server-rendered cards: re-evaluates recency,
// season windows and dated notices for the chosen trip date, adds straight-line distance,
// filters and sorts (logic unchanged from v0.1).
//
// URL state: lives only in the fragment (never a crawlable URL). Nothing is written on page
// load; only criteria the user actually changed are serialised (defaults omitted); returning
// everything to defaults removes the fragment; the brand / "Trip finder" links reset to the
// clean homepage. A shared fragment is restored on load and on hashchange.
var FinderState = {
  KEYS: ["from", "date", "max", "shore", "dock", "hide"],
  serialize: function (state, defaults) {
    var parts = [];
    FinderState.KEYS.forEach(function (k) {
      var v = state[k] == null ? "" : String(state[k]);
      if (v === "" || v === String(defaults[k])) return;
      parts.push(k + "=" + encodeURIComponent(v));
    });
    return parts.join("&");
  },
  parse: function (hash) {
    var out = {};
    (hash || "").replace(/^#/, "").split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("="), k = i < 0 ? kv : kv.slice(0, i), v = i < 0 ? "" : kv.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { return; }
      if (k === "from" && v) out.from = v;
      if (k === "date" && /^\d{4}-\d\d-\d\d$/.test(v)) out.date = v;
      if (k === "max" && /^\d+$/.test(v)) out.max = v;
      if ((k === "shore" || k === "hide") && (v === "0" || v === "1")) out[k] = v;
      if (k === "dock" && /^(any|prefer|require)$/.test(v)) out.dock = v;
    });
    return out;
  }
};
if (typeof module === "object" && module.exports) module.exports = FinderState;

(function () {
  if (typeof document === "undefined") return;
  var $ = function (id) { return document.getElementById(id); };
  var form = $("finder"); if (!form) return;
  var RECENT = 30, MI = 1.609344;
  var places = JSON.parse($("places-data").textContent);
  var dataDate = form.getAttribute("data-data-date");
  var origin = null, originLabel = "";
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card[data-lake]"));
  cards.forEach(function (c) { c._d = JSON.parse(c.getAttribute("data-lake")); });

  function current() {
    return { from: findPlace($("f-place").value) ? findPlace($("f-place").value)[0] : "", date: $("f-date").value,
             max: $("f-max").value, shore: $("f-shore").checked ? "1" : "0", dock: $("f-dock").value,
             hide: $("f-hide-restricted").checked ? "1" : "0" };
  }
  function apply(st) {
    $("f-place").value = st.from || "";
    $("f-date").value = st.date; $("f-max").value = st.max; $("f-shore").checked = st.shore === "1";
    $("f-dock").value = st.dock; $("f-hide-restricted").checked = st.hide === "1";
  }
  var DEFAULTS = (function () {
    var d = { from: "", date: $("f-date").value, max: $("f-max").value, shore: $("f-shore").checked ? "1" : "0",
              dock: $("f-dock").value, hide: $("f-hide-restricted").checked ? "1" : "0" };
    return d;
  })();

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
      rf.textContent = "";
      if (recent.length) {
        recent.sort(function (a, b) { return a - b; });
        var a = recent[0], b = recent[recent.length - 1], strong = document.createElement("strong");
        strong.textContent = total.toLocaleString() + " " + Object.keys(sp).join("/");
        rf.appendChild(strong);
        // same format as the server-rendered card (eligibility.fmt_range): "Oct 26–27", "Sep 30 – Oct 2"
        var range = a.getTime() === b.getTime() ? fmt(a) : (a.getMonth() === b.getMonth() ? fmt(a) + "–" + b.getDate() : fmt(a) + " – " + fmt(b));
        rf.appendChild(document.createTextNode(" stocked " + range));
        rf.className = "c-stock good";
      } else {
        var past = d.catch.filter(function (c) { return day(c[0]) <= trip; });
        rf.textContent = "No catchable-size stocking reported in the 30 days before this date" + (past.length ? " (last: " + fmt(day(past[0][0])) + ")" : "");
        rf.className = "c-stock quiet";
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
    card.querySelectorAll(".flags li:not([data-win])").forEach(function (li) {
      if (!li.hidden) { visible++; if (li.classList.contains("blocking")) blocking = true; }
    });
    var box = card.querySelector('[data-role="before"]');
    if (box) { box.hidden = visible === 0; box.className = "c-before " + (blocking ? "sev-block" : "sev-warn"); }
    var nf = card.querySelector('[data-role="noflags"]'); if (nf) nf.hidden = visible > 0;
    var shoreOk = d.shore === "YES" || d.shore === "LIMITED";
    var dist = origin ? km(origin[0], origin[1], d.lat, d.lon) / MI : null;
    var ds = card.querySelector(".dist"); if (ds) ds.textContent = dist === null ? "" : " · ~" + Math.round(dist) + " mi straight-line";
    return { q: recent.length > 0 && shoreOk, blocking: blocking, dist: dist, last: recent.length ? recent[recent.length - 1] : 0,
             shoreOk: shoreOk, dock: d.dock, restricted: d.restricted };
  }

  function writeHash() {
    var s = FinderState.serialize(current(), DEFAULTS);
    var clean = location.pathname;                  // fragment only; never query parameters
    try { history.replaceState(null, "", s ? clean + "#" + s : clean); } catch (e) {}
  }

  function run(userChanged) {
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
    var no = oth.filter(function (c) { return !c.hidden; }).length;
    $("r-count").textContent = n;
    $("o-count").textContent = no;
    var msg = "For " + trip.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) +
      (origin ? " within " + (max >= 999 ? "any distance" : max + " mi (straight-line, not driving)") + " of " + originLabel :
                ", newest catchable stocking first. Add a starting place to sort by distance (straight-line)") + ".";
    if (dataDate && trip > day(dataDate)) msg += " WDFW stocking data runs through " + fmt(day(dataDate)) + "; later plants are not yet known.";
    if (!n) msg = "No lakes match these criteria. " + msg;
    $("f-status").textContent = msg;
    if (!n && no) $("others-wrap").open = true;
    if (userChanged) {
      writeHash();
      if (window.track) window.track("trip_search", { origin: originLabel || "none", max_mi: max, shore: shore, dock: dock, results: n });
    }
  }

  function restore() {
    var st = FinderState.parse(location.hash), merged = {};
    FinderState.KEYS.forEach(function (k) { merged[k] = st[k] != null ? st[k] : DEFAULTS[k]; });
    apply(merged);
  }

  var timer;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { run(true); }, 350); });
  form.addEventListener("change", function () { clearTimeout(timer); run(true); });
  form.addEventListener("submit", function (e) {
    e.preventDefault(); clearTimeout(timer); run(true);
    var r = $("r-h"); if (r && r.scrollIntoView) r.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("f-geo").addEventListener("click", function () {
    if (!navigator.geolocation) { $("f-status").textContent = "Location is not available in this browser."; return; }
    $("f-status").textContent = "Finding your location (stays on your device)…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      origin = [pos.coords.latitude, pos.coords.longitude]; originLabel = "your location"; $("f-place").value = ""; run(true);
    }, function () { $("f-status").textContent = "Could not get your location. Type a town instead."; }, { maximumAge: 600000, timeout: 10000 });
  });
  window.addEventListener("hashchange", function () { origin = null; originLabel = ""; restore(); run(false); });
  document.querySelectorAll("a[data-home-reset]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      if (location.pathname !== "/") return;          // normal navigation from other pages
      e.preventDefault();
      origin = null; originLabel = ""; apply(DEFAULTS);
      try { history.replaceState(null, "", "/"); } catch (err) {}
      run(false);
      window.scrollTo(0, 0);
    });
  });
  if (location.hash) restore();
  run(false);
})();
