// Side panel: a link with `data-panel` opens its page's content (?panel=1) on the right instead of navigating.
// A data-panel link inside the panel (a session's "Xem trace") opens in the same panel; "← Quay lại" goes back.
// Click outside the panel, the close button or Esc to go back to the page. Ctrl/Cmd-click still opens a tab.
(function () {
  const panel = document.getElementById("panel");
  const backdrop = document.getElementById("panel-backdrop");
  const body = document.getElementById("panel-body");
  const pageLink = document.getElementById("panel-page");
  const back = document.getElementById("panel-back");
  let stack = []; // hrefs shown in the panel, the current one last
  let selected = null; // the row of the page whose link opened the panel

  function close() {
    panel.hidden = backdrop.hidden = true;
    body.innerHTML = "";
    stack = [];
    if (selected) selected.classList.remove("selected");
    selected = null;
  }

  async function show(href) {
    pageLink.href = href;
    back.hidden = stack.length < 2;
    body.innerHTML = '<p class="muted">Đang tải…</p>';
    panel.hidden = backdrop.hidden = false;
    try {
      const res = await fetch(href + (href.includes("?") ? "&" : "?") + "panel=1");
      body.innerHTML = await res.text(); // server-rendered by Jinja2 (escaped)
    } catch (e) {
      body.innerHTML = '<div class="notice error">Không tải được: ' + String(e).replace(/</g, "&lt;") + "</div>";
    }
    panel.scrollTop = 0;
  }

  function open(link) {
    if (panel.contains(link)) {
      stack.push(link.getAttribute("href"));
    } else {
      if (selected) selected.classList.remove("selected");
      selected = link.closest("tr, li");
      if (selected) selected.classList.add("selected");
      stack = [link.getAttribute("href")];
    }
    show(stack[stack.length - 1]);
  }

  document.addEventListener("click", function (e) {
    const link = e.target.closest("a[data-panel]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    open(link);
  });
  back.addEventListener("click", function () {
    stack.pop();
    show(stack[stack.length - 1]);
  });
  backdrop.addEventListener("click", close);
  document.getElementById("panel-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
  });
})();
