(function () {
  "use strict";

  const page = document.getElementById("mergeCustomerPage");
  if (!page) return;
  const groupsUrl = page.dataset.groupsUrl;
  const mergeUrl = page.dataset.mergeUrl;
  const csrf = page.dataset.csrf || "";
  const summary = document.getElementById("mergeSummary");
  const host = document.getElementById("mergeGroups");

  function selectedMode() {
    const picked = document.querySelector('input[name="mergeMode"]:checked');
    return picked ? picked.value : "name_phone";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderGroups(groups) {
    if (!host) return;
    if (!groups.length) {
      host.innerHTML = '<div class="alert alert-success py-2 mb-0">Is option par koi duplicate customer nahi mila.</div>';
      return;
    }
    host.innerHTML = groups.map(function (group, index) {
      const rows = (group.customers || []).map(function (customer) {
        const id = customer.customer_id;
        return (
          "<tr>" +
          '<td><input type="radio" name="main-' + index + '" class="merge-main" value="' + id + '"></td>' +
          '<td><input type="checkbox" class="merge-with" value="' + id + '" disabled></td>' +
          "<td>" + escapeHtml(customer.customer_name || "—") + "</td>" +
          "<td>" + escapeHtml(customer.mobile_number || "—") + "</td>" +
          "<td>" + escapeHtml(customer.pan_number || "—") + "</td>" +
          "<td>" + escapeHtml(customer.email || "—") + "</td>" +
          "<td>" + id + "</td>" +
          "</tr>"
        );
      }).join("");
      return (
        '<div class="border rounded p-2 mb-3 merge-group" data-index="' + index + '">' +
        '<div class="fw-semibold mb-2">' + escapeHtml(group.label) +
        ' <span class="text-muted fw-normal">(' + group.count + " customers)</span></div>" +
        '<div class="table-responsive"><table class="table table-sm align-middle mb-2">' +
        "<thead><tr>" +
        "<th>Select main customer</th>" +
        "<th>Merge with this customer</th>" +
        "<th>Customer name</th><th>Mobile</th><th>PAN</th><th>Email</th><th>ID</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
        '<button type="button" class="btn btn-primary btn-sm merge-go">Merge</button>' +
        "</div>"
      );
    }).join("");
  }

  async function loadGroups() {
    if (summary) summary.textContent = "Duplicates load ho rahe hain…";
    if (host) host.innerHTML = "";
    const url = new URL(groupsUrl, window.location.origin);
    url.searchParams.set("mode", selectedMode());
    const res = await fetch(url.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || !data.ok) {
      if (summary) summary.textContent = data.error || "Unable to load duplicates.";
      return;
    }
    const count = data.count || 0;
    if (summary) {
      summary.textContent = count
        ? count + " duplicate group" + (count === 1 ? "" : "s") + " mili."
        : "Koi duplicate group nahi mili.";
    }
    renderGroups(data.groups || []);
  }

  document.querySelectorAll('input[name="mergeMode"]').forEach(function (input) {
    input.addEventListener("change", function () {
      loadGroups().catch(function () {
        if (summary) summary.textContent = "Unable to load duplicates.";
      });
    });
  });

  host?.addEventListener("change", function (event) {
    const main = event.target.closest(".merge-main");
    if (!main) return;
    const group = main.closest(".merge-group");
    group.querySelectorAll(".merge-with").forEach(function (box) {
      const isMain = box.value === main.value;
      box.disabled = isMain;
      if (isMain) box.checked = false;
    });
  });

  host?.addEventListener("click", function (event) {
    const button = event.target.closest(".merge-go");
    if (!button) return;
    const group = button.closest(".merge-group");
    const main = group.querySelector(".merge-main:checked");
    const ids = Array.prototype.map.call(
      group.querySelectorAll(".merge-with:checked"),
      function (box) { return parseInt(box.value, 10); }
    ).filter(Boolean);
    if (!main) {
      alert("Select main customer.");
      return;
    }
    if (!ids.length) {
      alert("Merge with this customer mein kam se kam ek customer select karein.");
      return;
    }
    const names = Array.prototype.map.call(ids, function (id) {
      const box = group.querySelector('.merge-with[value="' + id + '"]');
      const row = box && box.closest("tr");
      return row ? (row.children[2].textContent || "").trim() : String(id);
    });
    if (!window.confirm("In customers ko main customer mein merge karna hai?\n" + names.join("\n"))) return;
    button.disabled = true;
    fetch(mergeUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      body: JSON.stringify({
        mode: selectedMode(),
        main_customer_id: parseInt(main.value, 10),
        merge_customer_ids: ids,
      }),
    })
      .then(function (res) { return res.json().then(function (data) { return { res: res, data: data }; }); })
      .then(function (result) {
        if (!result.res.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to merge these customers.");
        }
        alert(result.data.message || "Customers merged.");
        return loadGroups();
      })
      .catch(function (err) {
        alert(err.message || "Unable to merge these customers.");
      })
      .finally(function () {
        button.disabled = false;
      });
  });

  loadGroups().catch(function () {
    if (summary) summary.textContent = "Unable to load duplicates.";
  });
})();
