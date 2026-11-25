(function () {
  try {
    var saved = localStorage.getItem("nakout-theme");
    var theme =
      saved === "light" || saved === "dark"
        ? saved
        : window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark";
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", theme === "light" ? "#f3efe6" : "#090b0e");
    }
  } catch (error) {
    document.documentElement.dataset.theme = "dark";
  }
})();
