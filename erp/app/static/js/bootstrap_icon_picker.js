/**
 * Bootstrap Icon Picker — reusable picker with preview, search, favorites & recent.
 * Requires Bootstrap 5, Bootstrap Icons CSS, and bootstrap-icons.json (loaded once).
 */
(function (global) {
  "use strict";

  const STORAGE_FAVORITES = "jtcs_bi_favorites";
  const STORAGE_RECENT = "jtcs_bi_recent";
  const MAX_RECENT = 10;
  const FALLBACK_ICON = "bi-question-circle";

  let iconSlugs = null;
  let iconSlugSet = null;
  let iconsLoadPromise = null;
  let gridBuilt = false;

  function normalizeIconClass(raw) {
    let value = (raw || "").trim();
    if (!value) return "";
    if (value.includes(" ")) {
      const part = value.split(/\s+/).find(function (p) {
        return p.indexOf("bi-") === 0;
      });
      value = part || value;
    }
    if (value.indexOf("bi-") !== 0) {
      value = "bi-" + value.replace(/^bi-?/, "");
    }
    return value;
  }

  function slugFromClass(className) {
    return normalizeIconClass(className).replace(/^bi-/, "");
  }

  function readJsonList(key) {
    try {
      const raw = localStorage.getItem(key);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function writeJsonList(key, list) {
    try {
      localStorage.setItem(key, JSON.stringify(list));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function loadIcons(iconsUrl) {
    if (iconSlugs) return Promise.resolve(iconSlugs);
    if (iconsLoadPromise) return iconsLoadPromise;
    iconsLoadPromise = fetch(iconsUrl, { headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("Unable to load Bootstrap Icons list.");
        return res.json();
      })
      .then(function (data) {
        iconSlugs = Object.keys(data).sort();
        iconSlugSet = new Set(iconSlugs);
        return iconSlugs;
      })
      .catch(function () {
        iconSlugs = [
          "circle", "house", "gear", "person", "folder", "cash", "list", "grid",
          "pencil", "trash", "plus-lg", "search", "bell", "bank", "file-earmark",
        ];
        iconSlugSet = new Set(iconSlugs);
        return iconSlugs;
      });
    return iconsLoadPromise;
  }

  function isValidIcon(className) {
    if (!iconSlugSet) return false;
    const slug = slugFromClass(className);
    return !!slug && iconSlugSet.has(slug);
  }

  function BootstrapIconPicker(options) {
    this.options = options || {};
    this.input = document.getElementById(this.options.inputId || "MenuIcon");
    this.previewIcon = document.getElementById(this.options.previewId || "biPickerPreviewIcon");
    this.browseBtn = document.getElementById(this.options.browseBtnId || "biPickerBrowseBtn");
    this.warningEl = document.getElementById(this.options.warningId || "biPickerWarning");
    this.modalEl = document.getElementById(this.options.modalId || "biPickerModal");
    this.searchInput = document.getElementById(this.options.searchId || "biPickerSearch");
    this.gridEl = document.getElementById(this.options.gridId || "biPickerGrid");
    this.favoritesEl = document.getElementById(this.options.favoritesId || "biPickerFavorites");
    this.recentEl = document.getElementById(this.options.recentId || "biPickerRecent");
    this.emptyEl = document.getElementById(this.options.emptyId || "biPickerEmpty");
    this.modal = this.modalEl && global.bootstrap ? new global.bootstrap.Modal(this.modalEl) : null;
    this.focusIndex = -1;
    this.visibleItems = [];

    if (!this.input) return;
    this.bind();
  }

  BootstrapIconPicker.prototype.bind = function () {
    const self = this;
    this.input.addEventListener("input", function () {
      self.updatePreview();
    });
    this.input.addEventListener("blur", function () {
      self.updatePreview();
    });
    this.browseBtn?.addEventListener("click", function () {
      self.openModal();
    });
    this.searchInput?.addEventListener("input", function () {
      self.applyFilter();
    });
    this.modalEl?.addEventListener("shown.bs.modal", function () {
      self.refreshQuickSections();
      self.applyFilter();
      self.searchInput?.focus();
    });
    this.modalEl?.addEventListener("keydown", function (event) {
      self.handleModalKeydown(event);
    });
    this.gridEl?.addEventListener("click", function (event) {
      self.handleGridClick(event);
    });
    this.favoritesEl?.addEventListener("click", function (event) {
      self.handleQuickClick(event, "favorites");
    });
    this.recentEl?.addEventListener("click", function (event) {
      self.handleQuickClick(event, "recent");
    });

    loadIcons(this.options.iconsUrl).then(function () {
      self.buildMainGrid();
      self.updatePreview();
    });
  };

  BootstrapIconPicker.prototype.getDisplayClass = function (raw) {
    const normalized = normalizeIconClass(raw);
    if (!normalized) return FALLBACK_ICON;
    return isValidIcon(normalized) ? normalized : FALLBACK_ICON;
  };

  BootstrapIconPicker.prototype.updatePreview = function () {
    const raw = this.input.value;
    const normalized = normalizeIconClass(raw);
    const valid = normalized && isValidIcon(normalized);
    const displayClass = this.getDisplayClass(raw);

    if (this.previewIcon) {
      this.previewIcon.className = "bi " + displayClass;
    }
    if (this.warningEl) {
      if (raw.trim() && !valid) {
        this.warningEl.textContent = "Bootstrap Icon not found.";
        this.warningEl.classList.remove("d-none");
      } else {
        this.warningEl.textContent = "";
        this.warningEl.classList.add("d-none");
      }
    }
    this.input.classList.toggle("is-invalid", !!(raw.trim() && !valid));
  };

  BootstrapIconPicker.prototype.openModal = function () {
    const self = this;
    loadIcons(this.options.iconsUrl).then(function () {
      if (!gridBuilt) self.buildMainGrid();
      self.refreshQuickSections();
      self.applyFilter();
      self.modal?.show();
    });
  };

  BootstrapIconPicker.prototype.buildMainGrid = function () {
    if (!this.gridEl || !iconSlugs || gridBuilt) return;
    const fragment = document.createDocumentFragment();
    const favorites = new Set(readJsonList(STORAGE_FAVORITES));

    iconSlugs.forEach(function (slug) {
      const className = "bi-" + slug;
      const col = document.createElement("div");
      col.className = "col-4 col-sm-3 col-md-2 col-lg-2 bi-picker-item";
      col.dataset.icon = className;
      col.dataset.slug = slug;

      const card = document.createElement("button");
      card.type = "button";
      card.className = "bi-picker-card";
      card.dataset.icon = className;
      card.setAttribute("aria-label", "Select " + className);

      const icon = document.createElement("i");
      icon.className = "bi " + className;
      icon.setAttribute("aria-hidden", "true");

      const label = document.createElement("span");
      label.className = "bi-picker-label";
      label.textContent = className;

      const favBtn = document.createElement("button");
      favBtn.type = "button";
      favBtn.className = "bi-picker-fav" + (favorites.has(className) ? " is-fav" : "");
      favBtn.dataset.icon = className;
      favBtn.setAttribute("aria-label", "Toggle favorite " + className);
      favBtn.innerHTML = '<i class="bi bi-star' + (favorites.has(className) ? "-fill" : "") + '"></i>';

      card.appendChild(icon);
      card.appendChild(label);
      card.appendChild(favBtn);
      col.appendChild(card);
      fragment.appendChild(col);
    });

    this.gridEl.appendChild(fragment);
    gridBuilt = true;
  };

  BootstrapIconPicker.prototype.renderQuickGrid = function (container, icons, emptyText) {
    if (!container) return;
    container.innerHTML = "";
    if (!icons.length) {
      const empty = document.createElement("div");
      empty.className = "bi-picker-quick-empty";
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }
    icons.forEach(function (className) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "bi-picker-quick-item";
      btn.dataset.icon = className;
      btn.innerHTML =
        '<i class="bi ' + className + '" aria-hidden="true"></i>' +
        '<span>' + className + "</span>";
      container.appendChild(btn);
    });
  };

  BootstrapIconPicker.prototype.refreshQuickSections = function () {
    this.renderQuickGrid(
      this.favoritesEl,
      readJsonList(STORAGE_FAVORITES),
      "No favorites yet. Click the star on any icon."
    );
    this.renderQuickGrid(
      this.recentEl,
      readJsonList(STORAGE_RECENT),
      "No recently used icons."
    );
  };

  BootstrapIconPicker.prototype.applyFilter = function () {
    if (!this.gridEl) return;
    const query = (this.searchInput?.value || "").trim().toLowerCase();
    this.visibleItems = [];
    this.gridEl.querySelectorAll(".bi-picker-item").forEach(function (item) {
      const slug = (item.dataset.slug || "").toLowerCase();
      const className = (item.dataset.icon || "").toLowerCase();
      const match = !query || slug.indexOf(query) !== -1 || className.indexOf(query) !== -1;
      item.classList.toggle("d-none", !match);
      if (match) this.visibleItems.push(item.querySelector(".bi-picker-card"));
    }, this);

    if (this.emptyEl) {
      this.emptyEl.classList.toggle("d-none", this.visibleItems.length > 0);
    }
    this.focusIndex = -1;
  };

  BootstrapIconPicker.prototype.selectIcon = function (className) {
    const normalized = normalizeIconClass(className);
    if (!normalized || !isValidIcon(normalized)) return;
    this.input.value = normalized;
    this.updatePreview();
    this.pushRecent(normalized);
    this.modal?.hide();
  };

  BootstrapIconPicker.prototype.pushRecent = function (className) {
    let recent = readJsonList(STORAGE_RECENT).filter(function (item) {
      return item !== className;
    });
    recent.unshift(className);
    recent = recent.slice(0, MAX_RECENT);
    writeJsonList(STORAGE_RECENT, recent);
  };

  BootstrapIconPicker.prototype.toggleFavorite = function (className, favBtn) {
    let favorites = readJsonList(STORAGE_FAVORITES);
    const idx = favorites.indexOf(className);
    if (idx === -1) {
      favorites.unshift(className);
    } else {
      favorites.splice(idx, 1);
    }
    writeJsonList(STORAGE_FAVORITES, favorites);

    const isFav = favorites.indexOf(className) !== -1;
    if (favBtn) {
      favBtn.classList.toggle("is-fav", isFav);
      favBtn.innerHTML = '<i class="bi bi-star' + (isFav ? "-fill" : "") + '"></i>';
    }
    this.refreshQuickSections();
  };

  BootstrapIconPicker.prototype.handleGridClick = function (event) {
    const favBtn = event.target.closest(".bi-picker-fav");
    if (favBtn) {
      event.preventDefault();
      event.stopPropagation();
      this.toggleFavorite(favBtn.dataset.icon, favBtn);
      return;
    }
    const card = event.target.closest(".bi-picker-card");
    if (card) this.selectIcon(card.dataset.icon);
  };

  BootstrapIconPicker.prototype.handleQuickClick = function (event, section) {
    const favBtn = event.target.closest(".bi-picker-fav");
    if (favBtn) {
      event.preventDefault();
      event.stopPropagation();
      this.toggleFavorite(favBtn.dataset.icon, favBtn);
      return;
    }
    const btn = event.target.closest(".bi-picker-quick-item");
    if (btn) this.selectIcon(btn.dataset.icon);
  };

  BootstrapIconPicker.prototype.handleModalKeydown = function (event) {
    if (!this.visibleItems.length) return;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      this.focusIndex = Math.min(this.focusIndex + 1, this.visibleItems.length - 1);
      this.visibleItems[this.focusIndex]?.focus();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      this.focusIndex = Math.max(this.focusIndex - 1, 0);
      this.visibleItems[this.focusIndex]?.focus();
    } else if (event.key === "Enter" && document.activeElement?.dataset?.icon) {
      event.preventDefault();
      this.selectIcon(document.activeElement.dataset.icon);
    }
  };

  BootstrapIconPicker.init = function (options) {
    return new BootstrapIconPicker(options);
  };

  global.BootstrapIconPicker = BootstrapIconPicker;
})(window);
