(function () {
  "use strict";

  const cfg = window.MENU_ADMIN || {};
  const statusEl = document.getElementById("menuOrderStatus");
  if (typeof Sortable === "undefined") {
    return;
  }

  /** @type {WeakMap<Element, Element[]>} */
  const dirtyGroupsByUnit = new WeakMap();

  function setStatus(message, kind) {
    if (!statusEl) {
      return;
    }
    statusEl.className = "alert py-2 px-3 mb-3" + (kind ? " alert-" + kind : " d-none");
    statusEl.textContent = message || "";
    if (!message) {
      statusEl.classList.add("d-none");
    }
  }

  function groupParentId(group) {
    const raw = group && group.dataset ? group.dataset.parentId : "";
    return raw === "" || raw == null ? null : String(raw);
  }

  function wouldCreateCycle(unitEl, newParentId) {
    if (newParentId == null || newParentId === "") {
      return false;
    }
    const menuId = String(unitEl.dataset.menuId || "");
    if (!menuId) {
      return false;
    }
    if (String(newParentId) === menuId) {
      return true;
    }
    return !!unitEl.querySelector('.menu-sort-unit[data-menu-id="' + newParentId + '"]');
  }

  function orderInput(unit) {
    return unit.querySelector(":scope > .menu-row-grid .menu-order-input");
  }

  function saveBtn(unit) {
    return unit.querySelector(":scope > .menu-row-grid .menu-order-save-btn");
  }

  function refreshOrderInputs(group) {
    Array.from(group.children).forEach(function (unit, index) {
      if (!unit.classList.contains("menu-sort-unit")) {
        return;
      }
      const input = orderInput(unit);
      if (input) {
        input.value = String(index);
        input.dataset.savedOrder = String(index);
      }
    });
  }

  function markUnitDirty(unit, groups) {
    if (!unit) return;
    unit.classList.add("menu-row-dirty");
    const btn = saveBtn(unit);
    if (btn) btn.classList.remove("d-none");
    const list = (groups || []).filter(Boolean);
    if (list.length) {
      dirtyGroupsByUnit.set(unit, list);
    } else {
      const parentGroup = unit.closest(".menu-sortable-group");
      dirtyGroupsByUnit.set(unit, parentGroup ? [parentGroup] : []);
    }
  }

  function clearUnitDirty(unit) {
    if (!unit) return;
    unit.classList.remove("menu-row-dirty");
    const btn = saveBtn(unit);
    if (btn) {
      btn.classList.add("d-none");
      btn.disabled = false;
    }
    dirtyGroupsByUnit.delete(unit);
    const input = orderInput(unit);
    if (input) {
      input.dataset.savedOrder = String(input.value || "0");
    }
  }

  function clearGroupDirty(group) {
    if (!group) return;
    Array.from(group.children).forEach(function (unit) {
      if (unit.classList.contains("menu-sort-unit")) {
        clearUnitDirty(unit);
      }
    });
  }

  function collectGroupOrders(group) {
    const parentRaw = groupParentId(group);
    const units = Array.from(group.children).filter(function (el) {
      return el.classList.contains("menu-sort-unit");
    });
    return units.map(function (unit, index) {
      const input = orderInput(unit);
      let order = index;
      if (input && String(input.value).trim() !== "") {
        const parsed = parseInt(input.value, 10);
        if (!Number.isNaN(parsed) && parsed >= 0) {
          order = parsed;
        }
      }
      return {
        menu_id: Number(unit.dataset.menuId),
        display_order: order,
        parent_menu_id: parentRaw == null ? null : Number(parentRaw),
      };
    });
  }

  function persistOrders(orders) {
    setStatus("Saving order…", "secondary");
    return fetch(cfg.reorderUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrf || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ orders: orders }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok && data && data.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          const error = (result.data && result.data.error) || "Could not update order.";
          setStatus(error, "danger");
          return false;
        }
        setStatus((result.data && result.data.message) || "Display order updated.", "success");
        return true;
      })
      .catch(function () {
        setStatus("Could not update order. Please refresh and try again.", "danger");
        return false;
      });
  }

  function persistGroups(groups) {
    const unique = [];
    const seen = new Set();
    groups.forEach(function (group) {
      if (!group || seen.has(group)) {
        return;
      }
      seen.add(group);
      unique.push(group);
    });
    const orders = [];
    unique.forEach(function (group) {
      collectGroupOrders(group).forEach(function (item) {
        orders.push(item);
      });
    });
    return persistOrders(orders).then(function (ok) {
      if (ok) {
        unique.forEach(function (group) {
          clearGroupDirty(group);
          // Sync savedOrder markers to current input values (keep typed SR nos).
          Array.from(group.children).forEach(function (unit) {
            if (!unit.classList.contains("menu-sort-unit")) return;
            const input = orderInput(unit);
            if (input) input.dataset.savedOrder = String(input.value || "0");
          });
        });
      }
      return ok;
    });
  }

  function saveUnit(unit) {
    const groups = dirtyGroupsByUnit.get(unit) || [];
    const parentGroup = unit.closest(".menu-sortable-group");
    const toSave = groups.length ? groups : parentGroup ? [parentGroup] : [];
    if (!toSave.length) {
      setStatus("Nothing to save.", "secondary");
      return;
    }
    const input = orderInput(unit);
    if (input) {
      const parsed = parseInt(String(input.value || "").trim(), 10);
      if (Number.isNaN(parsed) || parsed < 0) {
        setStatus("Serial number must be 0 or a positive whole number.", "danger");
        input.focus();
        return;
      }
      input.value = String(parsed);
    }
    const btn = saveBtn(unit);
    if (btn) btn.disabled = true;
    persistGroups(toSave).finally(function () {
      if (btn && unit.classList.contains("menu-row-dirty")) {
        btn.disabled = false;
      }
    });
  }

  document.querySelectorAll(".menu-sortable-group").forEach(function (group) {
    Sortable.create(group, {
      animation: 150,
      handle: ".menu-drag-handle",
      draggable: ".menu-sort-unit",
      group: {
        name: "menu-admin-shared",
        pull: true,
        put: true,
      },
      fallbackOnBody: true,
      swapThreshold: 0.65,
      emptyInsertThreshold: 24,
      ghostClass: "menu-row-ghost",
      chosenClass: "menu-row-chosen",
      onMove: function (evt) {
        const newParentId = groupParentId(evt.to);
        if (wouldCreateCycle(evt.dragged, newParentId)) {
          return false;
        }
        return true;
      },
      onEnd: function (evt) {
        const fromGroup = evt.from;
        const toGroup = evt.to;
        const item = evt.item;
        const newParentId = groupParentId(toGroup);

        if (wouldCreateCycle(item, newParentId)) {
          if (evt.oldIndex != null) {
            const ref = fromGroup.children[evt.oldIndex] || null;
            fromGroup.insertBefore(item, ref);
          } else {
            fromGroup.appendChild(item);
          }
          setStatus("Cannot move a menu under itself or its child.", "danger");
          return;
        }

        item.dataset.parentId = newParentId == null ? "" : String(newParentId);

        const sameGroup = fromGroup === toGroup;
        const sameIndex = evt.oldIndex === evt.newIndex;
        if (sameGroup && sameIndex) {
          return;
        }

        // Preview new sequence in inputs; wait for row Save (no auto-save).
        refreshOrderInputs(fromGroup);
        if (!sameGroup) {
          refreshOrderInputs(toGroup);
        }
        markUnitDirty(item, sameGroup ? [toGroup] : [fromGroup, toGroup]);
        setStatus("Order changed — click Save on this row to apply.", "warning");
      },
    });
  });

  document.querySelectorAll(".menu-sort-unit").forEach(function (unit) {
    const input = orderInput(unit);
    if (input) {
      input.dataset.savedOrder = String(input.value || "0");
      input.addEventListener("input", function () {
        const current = String(input.value || "").trim();
        const saved = String(input.dataset.savedOrder || "0");
        if (current !== saved) {
          markUnitDirty(unit, [unit.closest(".menu-sortable-group")]);
          setStatus("Serial number changed — click Save on this row to apply.", "warning");
        }
      });
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          if (unit.classList.contains("menu-row-dirty")) {
            saveUnit(unit);
          }
        }
      });
    }

    const btn = saveBtn(unit);
    btn?.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      saveUnit(unit);
    });
  });
})();
