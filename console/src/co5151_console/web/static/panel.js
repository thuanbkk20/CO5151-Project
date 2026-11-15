// Side panel: a link with `data-panel` opens its page's content (?panel=1) on the right instead of navigating.
// Click outside the panel, the close button or Esc to go back to the page. Ctrl/Cmd-click still opens a tab.
(function () {
  const panel = document.getElementById("panel");
  const backdrop = document.getElementById("panel-backdrop");
  const body = document.getElementById("panel-body");
  const pageLink = document.getElementById("panel-page");
  let selected = null;

  function close() {
    panel.hidden = backdrop.hidden = true;
    body.innerHTML = "";
    if (selected) selected.classList.remove("selected");
    selected = null;
  }

  async function open(link) {
    const href = link.getAttribute("href");
    if (selected) selected.classList.remove("selected");
    selected = link.closest("tr, li");
    if (selected) selected.classList.add("selected");
    pageLink.href = href;
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

  document.addEventListener("click", function (e) {
    const link = e.target.closest("a[data-panel]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    open(link);
  });
  backdrop.addEventListener("click", close);
  document.getElementById("panel-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
  });
})();
