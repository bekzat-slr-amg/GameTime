const toggle = document.getElementById("nav-toggle");
const menu = document.getElementById("nav-menu");

function setMenu(open) {
  menu.classList.toggle("hidden", !open);
  toggle.setAttribute("aria-expanded", String(open));
}

if (toggle && menu) {
  toggle.addEventListener("click", () => {
    setMenu(menu.classList.contains("hidden"));
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setMenu(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenu(false);
  });
}