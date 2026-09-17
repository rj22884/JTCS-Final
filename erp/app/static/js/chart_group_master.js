(function () {
  "use strict";

  const api = window.CHART_GROUP_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("cgmAddBtn"),
    addNewBtn: document.getElementById("cgmAddNewBtn"),
    refreshBtn: document.getElementById("cgmRefreshBtn"),
    search: document.getElementById("cgmSearch"),
    count: document.getElementById("cgmCount"),
    body: document.getElementById("cgmGridBody"),
    empty: document.getElementById("cgmEmpty"),
    status: document.getElementById("cgmStatus"),
    modalEl: document.getElementById("cgmModal"),
    modalTitle: document.getElementById("cgmModalTitle"),
    form: document.getElementById("cgmForm"),
    id: document.getElementById("cgmId"),
    name: document.getElementById("cgmName"),
    parent: document.getElementById("cgmParent"),
    isActive: document.getElementById("cgmIsActive"),
    fieldList: document.getElementById("cgmFieldList"),
    fieldSearch: document.getElementById("cgmFieldSearch"),
    addFieldBtn: document.getElementById("cgmAddFieldBtn"),
    fieldModalEl: document.getElementById("cgmFieldModal"),
    fieldForm: document.getElementById("cgmFieldForm"),
    fieldModalTitle: document.getElementById("cgmFieldModalTitle"),
    fieldKey: document.getElementById("cgmFieldKey"),
    fieldLabel: document.getElementById("cgmFieldLabel"),
    fieldType: document.getElementById("cgmFieldType"),
    fieldHint: document.getElementById("cgmFieldHint"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  const fieldModal =
    els.fieldModalEl && window.bootstrap ? new bootstrap.Modal(els.fieldModalEl) : null;
  let searchTimer = null;
  let fieldCatalog = window.CHART_GROUP_DYN_CATALOG || { sections: [] };
  let selectedFields = { customer_name: { show: true, required: true } };
  let allGroups = Array.isArray(window.CHART_GROUP_INITIAL_ROWS)
    ? window.CHART_GROUP_INITIAL_ROWS.slice()
    : [];

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fillParentOptions(excludeId, selectedValue) {
    if (!els.parent) return;
    const current = selectedValue != null ? String(selectedValue) : "Assets";
    const skip = excludeId != null && excludeId !== "" ? String(excludeId) : "";
    let html =
      '<option value="Assets">Assets (Primary)</option>' +
      '<option value="Liabilities">Liabilities (Primary)</option>';
    const groups = (allGroups || []).slice().sort(function (a, b) {
      return String(a.group_name || "").localeCompare(String(b.group_name || ""));
    });
    groups.forEach(function (g) {
      if (!g || String(g.group_id) === skip) return;
      if (g.is_active === false) return;
      const label = (g.group_name || "") + " (" + (g.under_label || g.parent_group_name || g.under_type || "") + ")";
      html +=
        '<option value="' +
        escapeHtml(String(g.group_id)) +
        '">' +
        escapeHtml(label) +
        "</option>";
    });
    els.parent.innerHTML = html;
    if (current && Array.prototype.some.call(els.parent.options, function (opt) { return opt.value === current; })) {
      els.parent.value = current;
    } else {
      els.parent.value = "Assets";
    }
  }

  function selectedParentPayload() {
    const v = (els.parent && els.parent.value) || "Assets";
    if (v === "Assets" || v === "Liabilities") {
      return { under_type: v, parent_group_id: null };
    }
    const gid = parseInt(v, 10);
    return { parent_group_id: gid || null };
  }

  function parentSelectValue(record) {
    if (record && record.parent_group_id) return String(record.parent_group_id);
    return record && record.under_type === "Liabilities" ? "Liabilities" : "Assets";
  }

  function fieldUrl(template, key) {
    return String(template || "").replace("KEY", encodeURIComponent(key));
  }

  function fallbackFieldsForCurrentParent() {
    const selected = [{ key: "customer_name", required: true }];
    const v = (els.parent && els.parent.value) || "Assets";
    if (v === "Assets" || v === "Liabilities") return selected;
    const byId = {};
    (allGroups || []).forEach(function (g) {
      byId[String(g.group_id)] = g;
    });
    const names = [];
    let pid = parseInt(v, 10);
    let hops = 0;
    while (pid && hops < 40) {
      const g = byId[String(pid)];
      if (!g) break;
      names.push(String(g.group_name || "").toLowerCase());
      pid = g.parent_group_id ? parseInt(g.parent_group_id, 10) : 0;
      hops += 1;
    }
    const blob = names.join(" ");
    if (
      blob.indexOf("fixed asset") >= 0 ||
      blob.indexOf("immovable") >= 0 ||
      blob.indexOf("computers printers") >= 0
    ) {
      selected.push({ key: "purchase_date", required: false });
      selected.push({ key: "depreciation_rate", required: false });
    } else if (blob.indexOf("investment") >= 0) {
      selected.push({ key: "purchase_date", required: false });
      selected.push({ key: "appreciation_rate", required: false });
      selected.push({ key: "investment_kind", required: false });
      selected.push({ key: "property_state", required: false });
      selected.push({ key: "property_district", required: false });
      selected.push({ key: "property_tehsil", required: false });
      selected.push({ key: "property_pincode", required: false });
      selected.push({ key: "property_village", required: false });
      selected.push({ key: "property_land_area", required: false });
      selected.push({ key: "property_land_unit", required: false });
      selected.push({ key: "property_land_value", required: false });
    }
    return selected;
  }

  const FIELD_LINKS_FALLBACK = {
    pincode: ["country", "state", "district", "city", "state_gst_code"],
    state: ["country"],
    district: ["country", "state"],
    city: ["country", "state", "district"],
    state_gst_code: ["country", "state"],
    village: ["country", "state", "district", "pincode"],
    area: ["country", "state", "district", "city", "pincode"],
    address_line1: ["country", "state", "district", "city", "pincode"],
    address_line2: ["address_line1", "country", "state", "district", "city", "pincode"],
    gst_number: ["country", "state", "state_gst_code"],
    ifsc_code: ["bank_name", "branch_name"],
    account_number: ["bank_name", "account_holder_name", "ifsc_code", "branch_name"],
    opening_balance: ["opening_balance_date", "opening_balance_dr_cr"],
    depreciation_rate: ["purchase_date"],
    appreciation_rate: ["purchase_date"],
    property_state: [
      "investment_kind",
      "property_district",
      "property_tehsil",
      "property_pincode",
      "property_village",
    ],
    property_district: [
      "investment_kind",
      "property_state",
      "property_tehsil",
      "property_pincode",
      "property_village",
    ],
    property_tehsil: [
      "investment_kind",
      "property_state",
      "property_district",
      "property_pincode",
      "property_village",
    ],
    property_pincode: [
      "investment_kind",
      "property_state",
      "property_district",
      "property_tehsil",
      "property_village",
    ],
    property_village: [
      "investment_kind",
      "property_state",
      "property_district",
      "property_tehsil",
      "property_pincode",
    ],
    property_land_value: [
      "investment_kind",
      "property_state",
      "property_district",
      "property_tehsil",
      "property_pincode",
      "property_village",
      "property_land_area",
      "property_land_unit",
      "opening_balance",
      "opening_balance_date",
      "opening_balance_dr_cr",
    ],
  };

  function fieldLinksMap() {
    const links = fieldCatalog && fieldCatalog.links;
    if (links && Object.keys(links).length) return links;
    return FIELD_LINKS_FALLBACK;
  }

  function linksFor(key) {
    const extra = fieldLinksMap()[key] || [];
    const out = extra.slice();
    if (key && key.indexOf("property_") === 0) {
      if (out.indexOf("investment_kind") < 0) out.unshift("investment_kind");
    }
    return out;
  }

  function applyLinkedTicks(startKey) {
    const queue = [startKey];
    const seen = {};
    seen[startKey] = true;
    while (queue.length) {
      const cur = queue.shift();
      linksFor(cur).forEach(function (dep) {
        if (!dep || seen[dep]) return;
        seen[dep] = true;
        const spec = findCatalogField(dep);
        selectedFields[dep] = selectedFields[dep] || { show: false, required: false };
        selectedFields[dep].show = true;
        if (spec && spec.always_required) selectedFields[dep].required = true;
        queue.push(dep);
      });
    }
  }

  function tickAlwaysOnFields() {
    (fieldCatalog.sections || []).forEach(function (section) {
      (section.fields || []).forEach(function (field) {
        if (!field || !field.key) return;
        if (!field.always_on && !field.always_required) return;
        selectedFields[field.key] = { show: true, required: true };
      });
    });
  }

  function expandSelectedLinks() {
    tickAlwaysOnFields();
    Object.keys(selectedFields).forEach(function (key) {
      if (selectedFields[key] && selectedFields[key].show) applyLinkedTicks(key);
    });
  }

  function resetSelectedFields(selected) {
    selectedFields = { customer_name: { show: true, required: true } };
    (selected || []).forEach(function (item) {
      const key = item && item.key;
      if (!key) return;
      selectedFields[key] = {
        show: true,
        required: key === "customer_name" ? true : !!item.required,
      };
    });
    expandSelectedLinks();
  }

  function collectSelectedFields() {
    expandSelectedLinks();
    const out = [];
    Object.keys(selectedFields).forEach(function (key) {
      const row = selectedFields[key];
      if (!row || !row.show || key === "customer_name") return;
      if (!findCatalogField(key)) return;
      out.push({ key: key, required: !!row.required });
    });
    return out;
  }

  function renderFieldList() {
    if (!els.fieldList) return;
    const q = (els.fieldSearch?.value || "").trim().toLowerCase();
    const sections = fieldCatalog.sections || [];
    let html = "";
    sections.forEach(function (section) {
      const fields = (section.fields || []).filter(function (field) {
        if (!q) return true;
        return (
          String(field.label || "").toLowerCase().indexOf(q) >= 0 ||
          String(field.key || "").toLowerCase().indexOf(q) >= 0
        );
      });
      if (!fields.length) return;
      html +=
        '<div class="cgm-field-section">' +
        '<div class="fw-semibold small mb-1">' +
        escapeHtml(section.label || section.key) +
        "</div>" +
        '<div class="cgm-field-row cgm-field-head">' +
        '<span class="small text-muted">Show</span>' +
        '<span class="small text-muted">Req</span>' +
        '<span class="small text-muted">Field</span>' +
        "<span></span></div>";
      fields.forEach(function (field) {
        const lockedOn = !!field.always_on;
        const state = selectedFields[field.key] || {
          show: lockedOn,
          required: !!field.always_required,
        };
        if (lockedOn) {
          state.show = true;
          state.required = true;
          selectedFields[field.key] = state;
        }
        const custom = field.source === "custom";
        html +=
          '<div class="cgm-field-row' +
          (lockedOn ? " is-locked-on" : "") +
          '" data-field-key="' +
          escapeHtml(field.key) +
          '">' +
          '<input type="checkbox" class="form-check-input cgm-field-show" data-key="' +
          escapeHtml(field.key) +
          '"' +
          (state.show ? " checked" : "") +
          (lockedOn ? " disabled" : "") +
          ">" +
          '<label class="small mb-0">' +
          '<input type="checkbox" class="form-check-input me-1 cgm-field-req" data-key="' +
          escapeHtml(field.key) +
          '"' +
          (state.required ? " checked" : "") +
          (lockedOn || !state.show ? " disabled" : "") +
          "> Req</label>" +
          '<span class="small">' +
          escapeHtml(field.label) +
          (custom ? ' <span class="badge text-bg-secondary">Custom</span>' : "") +
          "</span>" +
          (custom
            ? '<span class="text-nowrap">' +
              '<button type="button" class="btn btn-link btn-sm py-0 px-1 cgm-field-edit" data-key="' +
              escapeHtml(field.key) +
              '">Edit</button>' +
              '<button type="button" class="btn btn-link btn-sm py-0 px-1 text-danger cgm-field-del" data-key="' +
              escapeHtml(field.key) +
              '">Delete</button>' +
              "</span>"
            : "<span></span>") +
          "</div>";
      });
      html += "</div>";
    });
    els.fieldList.innerHTML = html || '<div class="small text-muted">No fields match.</div>';
  }

  function loadCatalog() {
    if (!api.dynCatalog) return Promise.resolve(fieldCatalog);
    return fetch(api.dynCatalog, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) throw new Error(data.error || "Unable to load fields.");
          return data;
        });
      })
      .then(function (data) {
        fieldCatalog = {
          sections: data.sections || [],
          links: data.links || fieldCatalog.links || {},
        };
        renderFieldList();
        return fieldCatalog;
      });
  }

  function openFieldModal(record) {
    if (els.fieldKey) els.fieldKey.value = record && record.key ? record.key : "";
    if (els.fieldLabel) els.fieldLabel.value = record && record.label ? record.label : "";
    if (els.fieldType) els.fieldType.value = (record && record.type) || "text";
    if (els.fieldHint) els.fieldHint.value = record && record.hint ? record.hint : "";
    if (els.fieldModalTitle) {
      els.fieldModalTitle.textContent = record && record.key ? "Edit Field" : "Add Field";
    }
    fieldModal?.show();
    els.fieldLabel?.focus();
  }

  function findCatalogField(key) {
    let found = null;
    (fieldCatalog.sections || []).forEach(function (section) {
      (section.fields || []).forEach(function (field) {
        if (field.key === key) found = field;
      });
    });
    return found;
  }

  function saveCustomField(event) {
    event.preventDefault();
    const key = (els.fieldKey?.value || "").trim();
    const payload = {
      label: (els.fieldLabel?.value || "").trim(),
      type: els.fieldType?.value || "text",
      hint: (els.fieldHint?.value || "").trim(),
    };
    if (!payload.label) {
      alert("Field label is required.");
      return;
    }
    const url = key ? fieldUrl(api.dynUpdateField, key) : api.dynCreateField;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.CHART_GROUP_CSRF || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) throw new Error(data.error || "Save failed.");
          return data;
        });
      })
      .then(function (data) {
        const rec = data.record || {};
        if (rec.key) {
          selectedFields[rec.key] = selectedFields[rec.key] || { show: true, required: false };
          selectedFields[rec.key].show = true;
        }
        fieldModal?.hide();
        return loadCatalog();
      })
      .catch(function (err) {
        alert(err.message || "Unable to save field.");
      });
  }

  async function deleteCustomField(key) {
    if (!key) return;
    if (!(await JTCSDialog.confirm("Delete this custom field from all groups?"))) return;
    fetch(fieldUrl(api.dynDeleteField, key), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-CSRFToken": window.CHART_GROUP_CSRF || "",
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.ok === false) throw new Error(data.error || "Delete failed.");
          return data;
        });
      })
      .then(function () {
        delete selectedFields[key];
        return loadCatalog();
      })
      .catch(function (err) {
        alert(err.message || "Unable to delete field.");
      });
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      els.status.textContent = "";
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function renderRows(rows) {
    if (!els.body) return;
    els.body.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    rows.forEach(function (row) {
      const underLabel = row.under_label || row.parent_group_name || row.under_type || "";
      const underBadge =
        row.parent_group_id
          ? '<span class="badge text-bg-primary">' + escapeHtml(underLabel) + "</span>"
          : row.under_type === "Liabilities"
          ? '<span class="badge text-bg-warning">Liabilities</span>'
          : '<span class="badge text-bg-info">Assets</span>';
      const nature = row.group_nature || "";
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        escapeHtml(row.group_id) +
        "</td>" +
        "<td>" +
        escapeHtml(row.group_name) +
        "</td>" +
        "<td>" +
        escapeHtml(nature || "—") +
        "</td>" +
        "<td>" +
        underBadge +
        "</td>" +
        "<td>" +
        (row.is_active
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 cgm-edit" data-id="' +
        row.group_id +
        '"><i class="bi bi-pencil"></i> Edit</button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm cgm-delete" data-id="' +
        row.group_id +
        '"><i class="bi bi-trash"></i> Delete</button>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  function filteredRows() {
    const q = (els.search?.value || "").trim().toLowerCase();
    if (!q) return allGroups;
    return allGroups.filter(function (row) {
      const blob = [
        row.group_name,
        row.under_label,
        row.parent_group_name,
        row.under_type,
      ]
        .join(" ")
        .toLowerCase();
      return blob.indexOf(q) >= 0;
    });
  }

  function loadRows() {
    return fetch(api.list, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data;
        });
      })
      .then(function (data) {
        allGroups = data.rows || [];
        renderRows(filteredRows());
      })
      .catch(function (err) {
        showStatus(err.message || "Load failed.", "danger");
      });
  }

  function openAdd() {
    if (els.id) els.id.value = "";
    if (els.name) els.name.value = "";
    fillParentOptions("", "Assets");
    if (els.isActive) els.isActive.checked = true;
    if (els.fieldSearch) els.fieldSearch.value = "";
    resetSelectedFields(fallbackFieldsForCurrentParent());
    renderFieldList();
    loadCatalog().catch(function () {});
    if (els.modalTitle) els.modalTitle.textContent = "Add Group";
    modal?.show();
    els.name?.focus();
  }

  function openEdit(id) {
    fetch(apiUrl(api.record, id), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(function (record) {
        if (els.id) els.id.value = String(record.group_id || "");
        if (els.name) els.name.value = record.group_name || "";
        fillParentOptions(record.group_id, parentSelectValue(record));
        if (els.isActive) els.isActive.checked = !!record.is_active;
        if (els.fieldSearch) els.fieldSearch.value = "";
        if (record.catalog && record.catalog.sections) {
          fieldCatalog = record.catalog;
        }
        resetSelectedFields(record.selected || []);
        renderFieldList();
        if (els.modalTitle) els.modalTitle.textContent = "Edit Group";
        modal?.show();
      })
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function save(event) {
    event.preventDefault();
    const id = (els.id?.value || "").trim();
    const payload = Object.assign(
      {
        group_name: (els.name?.value || "").trim(),
        is_active: els.isActive?.checked ? "1" : "0",
        dyn_fields: collectSelectedFields(),
      },
      selectedParentPayload()
    );
    if (!payload.group_name) {
      alert("Group Name is required.");
      return;
    }
    const url = id ? apiUrl(api.update, id) : api.create;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.CHART_GROUP_CSRF || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Save failed.");
          return data;
        });
      })
      .then(function (data) {
        modal?.hide();
        showStatus(data.message || "Saved.", "success");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Save failed.");
      });
  }

  async function remove(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this group?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this group?" });
      if (!creds) return;
    }
    fetch(apiUrl(api.delete, id), {
      method: "POST",
      headers: Object.assign(
        {
          Accept: "application/json",
          "X-CSRFToken": window.CHART_GROUP_CSRF || "",
          "X-Requested-With": "XMLHttpRequest",
        },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) } : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Delete failed.");
          return data;
        });
      })
      .then(function (data) {
        showStatus(data.message || "Deleted.", "info");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
      });
  }

  els.addBtn?.addEventListener("click", openAdd);
  els.addNewBtn?.addEventListener("click", openAdd);
  els.refreshBtn?.addEventListener("click", loadRows);
  els.form?.addEventListener("submit", save);
  els.parent?.addEventListener("change", function () {
    if (els.id && els.id.value) return;
    resetSelectedFields(fallbackFieldsForCurrentParent());
    renderFieldList();
  });
  els.fieldSearch?.addEventListener("input", renderFieldList);
  els.addFieldBtn?.addEventListener("click", function () {
    openFieldModal(null);
  });
  els.fieldForm?.addEventListener("submit", saveCustomField);
  els.fieldList?.addEventListener("change", function (event) {
    const showBox = event.target.closest(".cgm-field-show");
    const reqBox = event.target.closest(".cgm-field-req");
    const box = showBox || reqBox;
    if (!box) return;
    const key = box.getAttribute("data-key");
    if (!key || key === "customer_name") return;
    selectedFields[key] = selectedFields[key] || { show: false, required: false };
    if (showBox) {
      selectedFields[key].show = !!showBox.checked;
      if (!showBox.checked) selectedFields[key].required = false;
      else applyLinkedTicks(key);
    }
    if (reqBox) {
      selectedFields[key].required = !!reqBox.checked;
      if (reqBox.checked) {
        selectedFields[key].show = true;
        applyLinkedTicks(key);
      }
    }
    renderFieldList();
  });
  els.fieldList?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".cgm-field-edit");
    if (editBtn) {
      openFieldModal(findCatalogField(editBtn.getAttribute("data-key")));
      return;
    }
    const delBtn = event.target.closest(".cgm-field-del");
    if (delBtn) deleteCustomField(delBtn.getAttribute("data-key"));
  });
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      renderRows(filteredRows());
    }, 250);
  });
  els.body?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".cgm-edit");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-id"));
      return;
    }
    const delBtn = event.target.closest(".cgm-delete");
    if (delBtn) remove(delBtn.getAttribute("data-id"));
  });

  renderRows(filteredRows());
})();
