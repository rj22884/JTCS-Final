(function () {
  "use strict";
  var toggle = document.getElementById("themeToggle");
  var key = "jtcs-theme";
  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    if (toggle) {
      var icon = toggle.querySelector("i");
      if (icon) icon.className = theme === "dark" ? "fas fa-sun" : "fas fa-moon";
    }
  }
  var saved = "light";
  try { saved = localStorage.getItem(key) || "light"; } catch (e) {}
  apply(saved);
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = (document.documentElement.getAttribute("data-theme") === "dark") ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(key, next); } catch (e) {}
    });
  }
  var navToggle = document.getElementById("navToggle");
  var menu = document.getElementById("navMenu");
  if (navToggle && menu) {
    navToggle.addEventListener("click", function () {
      var open = menu.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
})();
