(function () {
  "use strict";

  var DATE_TYPES = {
    date: true,
    "datetime-local": true,
    month: true,
    time: true,
    week: true
  };

  function inputType(el) {
    return (el.getAttribute("type") || "text").toLowerCase();
  }

  function isNumberInput(el) {
    if (!el || el.nodeType !== 1 || el.tagName !== "INPUT") return false;
    var type = inputType(el);
    if (DATE_TYPES[type]) return false;
    return type === "number";
  }

  function isZeroish(value) {
    if (value == null) return true;
    var text = String(value).trim();
    if (text === "") return true;
    if (!/^[+-]?(?:\d+|\d*\.\d+)$/.test(text)) return false;
    var number = Number(text);
    return number === 0;
  }

  function blankNumberInput(el) {
    if (!isNumberInput(el)) return;
    if (el.getAttribute("data-jtcs-keep-zero") === "1") return;
    if (isZeroish(el.value) && el.value !== "") {
      originalValue.set.call(el, "");
    }
    var placeholder = el.getAttribute("placeholder");
    if (placeholder && isZeroish(placeholder)) {
      el.setAttribute("placeholder", "");
    }
  }

  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    if (isNumberInput(root)) blankNumberInput(root);
    if (!root.querySelectorAll) return;
    var nodes = root.querySelectorAll('input[type="number"]');
    for (var i = 0; i < nodes.length; i++) blankNumberInput(nodes[i]);
  }

  var originalValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  if (originalValue && originalValue.get && originalValue.set) {
    Object.defineProperty(HTMLInputElement.prototype, "value", {
      configurable: true,
      enumerable: originalValue.enumerable,
      get: function () {
        return originalValue.get.call(this);
      },
      set: function (next) {
        if (isNumberInput(this) && this.getAttribute("data-jtcs-keep-zero") !== "1" && isZeroish(next)) {
          originalValue.set.call(this, "");
          return;
        }
        originalValue.set.call(this, next);
      }
    });
  }

  function scrollableParent(el) {
    var node = el.parentElement;
    while (node && node !== document.body) {
      var style = window.getComputedStyle(node);
      var overflowY = style.overflowY;
      var overflowX = style.overflowX;
      var canScrollY = (overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight;
      var canScrollX = (overflowX === "auto" || overflowX === "scroll") && node.scrollWidth > node.clientWidth;
      if (canScrollY || canScrollX) return node;
      node = node.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  }

  document.addEventListener("wheel", function (event) {
    var target = event.target;
    if (!isNumberInput(target)) return;
    event.preventDefault();
    var parent = scrollableParent(target);
    if (!parent) return;
    parent.scrollTop += event.deltaY;
    parent.scrollLeft += event.deltaX;
  }, { capture: true, passive: false });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    if (!isNumberInput(event.target)) return;
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    event.preventDefault();
  }, true);

  function start() {
    scan(document.body);
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var mutation = mutations[i];
        if (mutation.type === "childList") {
          for (var j = 0; j < mutation.addedNodes.length; j++) scan(mutation.addedNodes[j]);
        } else if (mutation.type === "attributes" && isNumberInput(mutation.target)) {
          blankNumberInput(mutation.target);
        }
      }
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["value", "placeholder"]
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
