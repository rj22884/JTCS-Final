(function () {
  function tableToCsv(table) {
    const rows = [];
    table.querySelectorAll("tr").forEach(function (row) {
      const cells = [];
      row.querySelectorAll("th, td").forEach(function (cell) {
        const text = (cell.innerText || "").replace(/"/g, '""');
        cells.push('"' + text + '"');
      });
      if (cells.length) rows.push(cells.join(","));
    });
    return rows.join("\r\n");
  }

  function downloadCsv(csv, filename) {
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }

  document.addEventListener("jtcs:export-excel", function () {
    const table = document.getElementById("jtcsReportTable");
    if (!table) return;
    const title = (window.JTCS_REPORT_TITLE || "report").replace(/[^\w\-]+/g, "_");
    downloadCsv(tableToCsv(table), title + ".csv");
  });

  document.addEventListener("jtcs:export-pdf", function () {
    window.print();
  });
})();
