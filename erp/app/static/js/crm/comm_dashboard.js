(function () {
  "use strict";
  const page = document.getElementById("crmCommDashboard");
  if (!page || !page.dataset.apiStats) return;
  // Stats are server-rendered; optional soft refresh for live counters.
  setInterval(async function () {
    try {
      const data = await CrmCommon.apiFetch(page.dataset.apiStats);
      if (!data || !data.ok) return;
      /* Keep SSR values; badge polling handles live unread. */
    } catch (_e) {}
  }, 60000);
})();
