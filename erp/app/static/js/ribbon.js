(function () {
  const topMenu = document.getElementById("jtcsTopMenu");
  const mobileToggle = document.getElementById("jtcsMobileMenuToggle");

  function closeAllTopMenus(except) {
    document.querySelectorAll(".jtcs-top-item.open").forEach(function (item) {
      if (item !== except) {
        item.classList.remove("open");
        const btn = item.querySelector(".jtcs-top-link");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    });
  }

  if (topMenu) {
    topMenu.querySelectorAll(".jtcs-top-item.has-dropdown").forEach(function (item) {
      const trigger = item.querySelector(".jtcs-top-link");
      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        const isOpen = item.classList.contains("open");
        closeAllTopMenus();
        if (!isOpen) {
          item.classList.add("open");
          trigger.setAttribute("aria-expanded", "true");
        }
      });
    });

    topMenu.querySelectorAll(".jtcs-flyout-toggle").forEach(function (toggle) {
      toggle.addEventListener("click", function (event) {
        if (window.innerWidth <= 991) {
          event.preventDefault();
          const parent = toggle.closest(".jtcs-menu-item");
          parent.classList.toggle("open");
        }
      });
    });

    document.addEventListener("click", function (event) {
      if (!event.target.closest(".jtcs-menu-bar")) {
        closeAllTopMenus();
      }
    });

    topMenu.querySelectorAll(".jtcs-top-item.has-dropdown").forEach(function (item) {
      item.addEventListener("mouseenter", function () {
        if (window.innerWidth > 991) {
          closeAllTopMenus(item);
          item.classList.add("open");
          item.querySelector(".jtcs-top-link").setAttribute("aria-expanded", "true");
        }
      });
      item.addEventListener("mouseleave", function () {
        if (window.innerWidth > 991) {
          item.classList.remove("open");
          item.querySelector(".jtcs-top-link").setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  if (mobileToggle && topMenu) {
    mobileToggle.addEventListener("click", function () {
      topMenu.classList.toggle("open");
    });
    topMenu.addEventListener("click", function (event) {
      const link = event.target.closest("a.jtcs-menu-link, a.jtcs-top-link");
      if (!link || link.getAttribute("href") === "#") return;
      if (window.innerWidth <= 991) {
        topMenu.classList.remove("open");
        closeAllTopMenus();
      }
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 991) {
        topMenu.classList.remove("open");
      }
    });
  }

  document.querySelectorAll("[data-ribbon-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      const action = button.getAttribute("data-ribbon-action");
      switch (action) {
        case "refresh":
          window.location.reload();
          break;
        case "print":
          window.print();
          break;
        case "search":
          break;
        case "export-excel":
          document.dispatchEvent(new CustomEvent("jtcs:export-excel"));
          break;
        case "export-pdf":
          document.dispatchEvent(new CustomEvent("jtcs:export-pdf"));
          break;
        case "edit":
          document.dispatchEvent(new CustomEvent("jtcs:edit"));
          break;
        case "delete":
          document.dispatchEvent(new CustomEvent("jtcs:delete"));
          break;
        default:
          break;
      }
    });
  });
})();
