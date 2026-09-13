(function () {
  var input = document.getElementById("helpSearch");
  if (!input) return;

  var links = Array.prototype.slice.call(document.querySelectorAll("[data-help-topic]"));

  function filterLocal() {
    var q = (input.value || "").trim().toLowerCase();
    var groups = document.querySelectorAll(".help-toc-group");
    links.forEach(function (link) {
      var hay = (link.getAttribute("data-help-text") || link.textContent || "").toLowerCase();
      var show = !q || hay.indexOf(q) !== -1;
      link.classList.toggle("is-hidden", !show);
      var li = link.closest("li");
      if (li) li.hidden = !show;
    });
    groups.forEach(function (group) {
      var visible = group.querySelector("a[data-help-topic]:not(.is-hidden)");
      group.hidden = q && !visible;
    });
  }

  input.addEventListener("input", filterLocal);
})();
