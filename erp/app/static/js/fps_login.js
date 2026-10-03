(function () {
  const api = window.FPS_LOGIN_API || {};
  const els = {
    state: document.getElementById("fpsState"),
    district: document.getElementById("fpsDistrict"),
    dso: document.getElementById("fpsDso"),
    aro: document.getElementById("fpsAro"),
    search: document.getElementById("fpsSearch"),
    shopBlock: document.getElementById("fpsShopBlock"),
    list: document.getElementById("fpsList"),
    status: document.getElementById("fpsStatus"),
    error: document.getElementById("fpsError"),
    count: document.getElementById("fpsCount"),
    more: document.getElementById("fpsMoreBtn"),
    selectedWrap: document.getElementById("fpsSelected"),
    selectedName: document.getElementById("fpsSelectedName"),
    selectedMeta: document.getElementById("fpsSelectedMeta"),
    login: document.getElementById("fpsLoginBtn"),
  };

  if (!api.shops || !api.options || !els.state) return;

  const STEPS = [
    { key: "state", el: els.state, level: "state", placeholder: "Select State", next: "district" },
    { key: "district", el: els.district, level: "district", placeholder: "Select District", next: "dso" },
    { key: "dso", el: els.dso, level: "dso", placeholder: "Select DSO", next: "aro" },
    { key: "aro", el: els.aro, level: "aro", placeholder: "Select ARO", next: null },
  ];

  let page = 1;
  let query = "";
  let hasMore = false;
  let selected = null;
  let timer = null;
  let loading = false;

  function csrfToken() {
    return api.csrf ||
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setError(message) {
    if (!els.error) return;
    if (!message) {
      els.error.classList.add("d-none");
      els.error.textContent = "";
      return;
    }
    els.error.textContent = message;
    els.error.classList.remove("d-none");
  }

  function setStatus(message) {
    if (els.status) els.status.textContent = message || "";
  }

  function selectedId(el) {
    const value = parseInt((el && el.value) || "0", 10);
    return value > 0 ? value : 0;
  }

  function aroReady() {
    return !!selectedId(els.aro);
  }

  function fillSelect(select, rows, placeholder) {
    if (!select) return;
    const current = select.value;
    select.innerHTML = '<option value="">' + escapeHtml(placeholder) + "</option>";
    (rows || []).forEach(function (row) {
      const option = document.createElement("option");
      option.value = String(row.id);
      option.textContent = row.label;
      if (String(row.id) === current) option.selected = true;
      select.appendChild(option);
    });
  }

  function resetFrom(index) {
    STEPS.slice(index).forEach(function (step, offset) {
      fillSelect(step.el, [], step.placeholder);
      step.el.disabled = offset !== 0;
      if (offset !== 0) step.el.value = "";
    });
    selected = null;
    loading = false;
    if (els.selectedWrap) els.selectedWrap.classList.add("d-none");
    if (els.list) els.list.innerHTML = "";
    if (els.count) els.count.textContent = "";
    if (els.more) els.more.classList.add("d-none");
    if (els.search) els.search.value = "";
    query = "";
    page = 1;
    if (els.shopBlock) els.shopBlock.classList.add("d-none");
  }

  function metaRows(row) {
    return [
      ["State", row.state_name],
      ["District", row.district_name],
      ["DSO", row.dso_name],
      ["ARO", row.aro_name],
      ["FPS ID", row.fps_id],
      ["Existing FPS", row.existing_fps_id],
      ["Tehsil", row.tehsil_name],
      ["Status", row.status_label || (row.active_status === false ? "Inactive" : "Active")],
    ].filter(function (pair) { return pair[1]; });
  }

  function renderMeta(target, row) {
    if (!target) return;
    target.innerHTML = metaRows(row).map(function (pair) {
      return "<dt>" + escapeHtml(pair[0]) + "</dt><dd>" + escapeHtml(pair[1]) + "</dd>";
    }).join("");
  }

  function showSelected(row) {
    selected = row;
    if (!els.selectedWrap) return;
    els.selectedWrap.classList.toggle("d-none", !row);
    if (!row) return;
    if (els.selectedName) els.selectedName.textContent = row.shop_name || row.dealer_name || "FPS";
    renderMeta(els.selectedMeta, row);
  }

  function renderRows(rows, append) {
    if (!els.list) return;
    if (!append) els.list.innerHTML = "";
    (rows || []).forEach(function (row) {
      const item = document.createElement("article");
      item.className = "ol-fps-item";
      const name = escapeHtml(row.shop_name || row.dealer_name || "FPS");
      const place = [row.district_name, row.tehsil_name].filter(Boolean).join(" | ");
      item.innerHTML =
        '<div class="ol-fps-item-name">' + name + "</div>" +
        "<dl>" +
          "<dt>FPS ID</dt><dd>" + escapeHtml(row.fps_id || "") + "</dd>" +
          (row.existing_fps_id ? "<dt>Existing FPS</dt><dd>" + escapeHtml(row.existing_fps_id) + "</dd>" : "") +
          (place ? "<dt>Location</dt><dd>" + escapeHtml(place) + "</dd>" : "") +
          "<dt>Status</dt><dd>" + escapeHtml(row.status_label || "Active") + "</dd>" +
        "</dl>" +
        '<button type="button" class="btn btn-sm btn-outline-primary">Select</button>';
      item.querySelector("button").addEventListener("click", function () {
        setError("");
        showSelected(row);
        els.selectedWrap?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      els.list.appendChild(item);
    });
  }

  async function parseJson(res) {
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Unable to login. Please try again.");
    }
    return data;
  }

  async function loadOptions(step, parentId) {
    const url = new URL(api.options, window.location.origin);
    url.searchParams.set("level", step.level);
    if (parentId) url.searchParams.set("parent_id", String(parentId));
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJson(res);
    fillSelect(step.el, data.rows || [], step.placeholder);
    step.el.disabled = false;
    if (!(data.rows || []).length) {
      setStatus("No active records found for this selection.");
    }
    return data.rows || [];
  }

  async function loadShops(options) {
    const opts = options || {};
    if (!aroReady()) {
      if (els.shopBlock) els.shopBlock.classList.add("d-none");
      setStatus("Select State, District, DSO and ARO first.");
      return;
    }
    if (loading) return;
    loading = true;
    const nextPage = opts.reset ? 1 : page;
    setError("");
    setStatus(query ? "Searching FPS..." : "Loading FPS list...");
    const url = new URL(api.shops, window.location.origin);
    if (query) url.searchParams.set("q", query);
    url.searchParams.set("page", String(nextPage));
    url.searchParams.set("per_page", "40");
    url.searchParams.set("state_id", String(selectedId(els.state)));
    url.searchParams.set("district_id", String(selectedId(els.district)));
    url.searchParams.set("dso_id", String(selectedId(els.dso)));
    url.searchParams.set("aro_id", String(selectedId(els.aro)));
    try {
      const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
      const data = await parseJson(res);
      page = data.page || nextPage;
      hasMore = !!data.has_more;
      if (els.shopBlock) els.shopBlock.classList.remove("d-none");
      renderRows(data.rows || [], !opts.reset && page > 1);
      if (!(data.rows || []).length && page <= 1) {
        if (els.list) els.list.innerHTML = "";
        setStatus("No active FPS records found.");
      } else {
        setStatus("Select your FPS, then Login.");
      }
      if (els.count) els.count.textContent = (data.total || 0) + " active FPS";
      if (els.more) els.more.classList.toggle("d-none", !hasMore);
    } catch (err) {
      setStatus("");
      setError(err.message || "Unable to login. Please try again.");
    } finally {
      loading = false;
    }
  }

  async function login() {
    if (!selected || !selected.fps_row_id) {
      setError("Select an FPS from the list.");
      return;
    }
    els.login.disabled = true;
    els.login.textContent = "Signing in…";
    setError("");
    try {
      const res = await fetch(api.login, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ fps_row_id: selected.fps_row_id, csrf_token: csrfToken() }),
      });
      const data = await parseJson(res);
      window.location.href = data.redirect || "/public-report/ration-card/fps-detail";
    } catch (err) {
      setError(err.message || "Unable to login. Please try again.");
      els.login.disabled = false;
      els.login.textContent = "Login";
    }
  }

  STEPS.forEach(function (step, index) {
    step.el.addEventListener("change", function () {
      setError("");
      resetFrom(index + 1);
      const value = selectedId(step.el);
      if (!value) {
        setStatus("Select " + step.placeholder.replace("Select ", "") + " to continue.");
        return;
      }
      const next = STEPS[index + 1];
      if (next) {
        setStatus("Loading " + next.placeholder.replace("Select ", "") + "...");
        loadOptions(next, value).then(function (rows) {
          if (rows.length) setStatus("Select " + next.placeholder.replace("Select ", "") + " to continue.");
        }).catch(function (err) {
          setError(err.message || "Unable to load the next office list.");
        });
        return;
      }
      loadShops({ reset: true });
    });
  });

  els.search?.addEventListener("input", function () {
    if (!aroReady()) return;
    clearTimeout(timer);
    timer = setTimeout(function () {
      query = (els.search.value || "").trim();
      page = 1;
      loadShops({ reset: true });
    }, 280);
  });
  els.more?.addEventListener("click", function () {
    if (!hasMore || !aroReady()) return;
    page += 1;
    loadShops();
  });
  els.login?.addEventListener("click", function () {
    login().catch(function (err) { setError(err.message); });
  });

  setStatus("Loading states...");
  loadOptions(STEPS[0], null).then(function (rows) {
    if (rows.length) setStatus("Select State to continue.");
    else setStatus("No active FPS records found.");
  }).catch(function (err) {
    setError(err.message || "Unable to load State list.");
  });
})();
