// Relative timestamps ("checked 2 hours ago") from absolute ISO times, plus lightweight
// event tracking. Analytics is a no-op unless gtag is configured (config.json ga4_measurement_id).
(function () {
  function rel(iso) {
    var t = Date.parse(iso); if (isNaN(t)) return null;
    var s = Math.round((Date.now() - t) / 1000);
    if (s < 0) return null;
    if (s < 90) return "just now";
    var m = Math.round(s / 60); if (m < 60) return m + " min ago";
    var h = Math.round(m / 60); if (h < 36) return h + " hour" + (h === 1 ? "" : "s") + " ago";
    var d = Math.round(h / 24); return d + " days ago";
  }
  document.querySelectorAll("time[data-rel]").forEach(function (el) {
    var r = rel(el.getAttribute("datetime"));
    if (r) { el.title = el.textContent; el.textContent = r; }
  });
  window.track = function (name, params) {
    try { if (window.gtag) window.gtag("event", name, params || {}); } catch (e) {}
  };
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a.js-track");
    if (!a) return;
    var card = a.closest(".card");
    window.track(a.getAttribute("data-track") || "click", {
      link_url: a.href, lake: card ? card.getAttribute("data-slug") : (location.pathname.split("/")[2] || null)
    });
  });
})();
