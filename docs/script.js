(() => {
  "use strict";

  const root = document.documentElement;
  const body = document.body;
  const config = window.SUANPAN_DOCS || {};
  const placeholderOrigin = "https://suanpan.example.com";
  const apiOrigin = String(config.apiBaseUrl || placeholderOrigin).replace(/\/$/, "");

  // Keep the public API origin in one small configuration file.
  if (apiOrigin !== placeholderOrigin) {
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach((node) => {
      if (node.nodeValue.includes(placeholderOrigin)) {
        node.nodeValue = node.nodeValue.replaceAll(placeholderOrigin, apiOrigin);
      }
    });
    document.querySelectorAll("a[href]").forEach((link) => {
      if (link.href.startsWith(placeholderOrigin)) {
        link.href = link.href.replace(placeholderOrigin, apiOrigin);
      }
    });
  }

  const storedTheme = localStorage.getItem("suanpan-theme");
  const preferredDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = storedTheme || (preferredDark ? "dark" : "light");
  setTheme(initialTheme);

  function setTheme(theme) {
    root.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content",
      theme === "dark" ? "#111714" : "#f7f5f0",
    );
    const toggle = document.querySelector(".theme-toggle");
    if (toggle) toggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
  }

  document.querySelector(".theme-toggle")?.addEventListener("click", () => {
    const theme = root.dataset.theme === "dark" ? "light" : "dark";
    setTheme(theme);
    localStorage.setItem("suanpan-theme", theme);
  });

  const menuToggle = document.querySelector(".menu-toggle");
  const mobileBackdrop = document.querySelector(".mobile-backdrop");

  function setMenu(open) {
    body.classList.toggle("menu-open", open);
    menuToggle?.setAttribute("aria-expanded", String(open));
    menuToggle?.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    if (mobileBackdrop) mobileBackdrop.hidden = !open;
  }

  menuToggle?.addEventListener("click", () => setMenu(!body.classList.contains("menu-open")));
  mobileBackdrop?.addEventListener("click", () => setMenu(false));
  document.querySelectorAll(".sidebar a").forEach((link) => link.addEventListener("click", () => setMenu(false)));

  const quickstarts = {
    curl: `<span class="prompt">$</span> curl ${apiOrigin}/hit/acme.dev/homepage\n\n<span class="comment"># 200 OK</span>\n<span class="json">{ "value": 1 }</span>`,
    javascript: `<span class="comment">// Browser or Node.js</span>\nconst response = await fetch(\n  <span class="json-string">"${apiOrigin}/hit/acme.dev/homepage"</span>\n);\nconst { value } = await response.json();\nconsole.log(value); <span class="comment">// 1</span>`,
    python: `<span class="comment"># Python 3</span>\nimport requests\n\nresponse = requests.get(\n    <span class="json-string">"${apiOrigin}/hit/acme.dev/homepage"</span>\n)\nprint(response.json()) <span class="comment"># {"value": 1}</span>`,
  };

  document.querySelectorAll(".code-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".code-tab").forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      const code = document.querySelector(".quickstart-code code");
      if (code) code.innerHTML = quickstarts[tab.dataset.language];
    });
  });

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text.trim());
      const previous = button.textContent;
      button.textContent = "Copied";
      setTimeout(() => { button.textContent = previous; }, 1300);
    } catch {
      button.textContent = "Select text";
      setTimeout(() => { button.textContent = "Copy"; }, 1300);
    }
  }

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", () => {
      const code = button.closest(".code-window")?.querySelector("pre code");
      if (code) copyText(code.textContent, button);
    });
  });

  document.querySelectorAll(".copy-path").forEach((button) => {
    button.addEventListener("click", () => {
      const path = button.closest(".endpoint-heading")?.querySelector("code");
      if (path) copyText(path.textContent, button);
    });
  });

  const shieldLabel = document.querySelector("#shield-label");
  const shieldColor = document.querySelector("#shield-color");
  const shieldHex = document.querySelector("#shield-hex");
  const shieldStyle = document.querySelector("#shield-style");
  const badge = document.querySelector(".badge-preview");
  const badgeLabel = badge?.querySelector("span");
  const shieldUrl = document.querySelector(".shield-url");

  function validHex(value) {
    return /^[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : null;
  }

  function updateShield(source) {
    const label = shieldLabel.value.trim() || "counter";
    if (source === "picker") shieldHex.value = shieldColor.value.slice(1);
    if (source === "hex") {
      const hex = validHex(shieldHex.value);
      if (hex) shieldColor.value = `#${hex}`;
    }
    const hex = validHex(shieldHex.value) || "d9533f";
    const style = shieldStyle.value;
    badgeLabel.textContent = label;
    badge.style.setProperty("--badge-color", `#${hex}`);
    badge.classList.toggle("simple", style.endsWith("-simple"));
    badge.classList.toggle("square", style.includes("square"));
    badge.classList.toggle("plastic", style.startsWith("plastic"));
    shieldUrl.textContent = `/get/acme.dev/homepage/shield?text=${encodeURIComponent(label)}&bgcolor=${hex}&style=${style}`;
  }

  shieldLabel?.addEventListener("input", () => updateShield("label"));
  shieldColor?.addEventListener("input", () => updateShield("picker"));
  shieldHex?.addEventListener("input", () => updateShield("hex"));
  shieldStyle?.addEventListener("change", () => updateShield("style"));

  const searchDialog = document.querySelector(".search-dialog");
  const searchInput = document.querySelector("#docs-search");
  const searchResults = document.querySelector(".search-results");
  const searchable = [...document.querySelectorAll("main section[id]")].map((section) => ({
    id: section.id,
    title: section.querySelector("h1, h2")?.textContent.trim() || section.id,
    text: section.textContent.replace(/\s+/g, " ").trim(),
  }));

  function renderSearch(query = "") {
    const needle = query.trim().toLowerCase();
    const results = searchable.filter((item) => !needle || `${item.title} ${item.text}`.toLowerCase().includes(needle)).slice(0, 8);
    searchResults.replaceChildren();
    if (!results.length) {
      const empty = document.createElement("p");
      empty.className = "search-empty";
      empty.textContent = "No matching sections.";
      searchResults.append(empty);
      return;
    }
    results.forEach((item) => {
      const link = document.createElement("a");
      link.className = "search-result";
      link.href = `#${item.id}`;
      const title = document.createElement("strong");
      title.textContent = item.title;
      const hint = document.createElement("span");
      hint.textContent = item.id === "overview" ? "Introduction" : `Jump to #${item.id}`;
      link.append(title, hint);
      link.addEventListener("click", () => searchDialog.close());
      searchResults.append(link);
    });
  }

  function openSearch() {
    renderSearch(searchInput.value);
    if (!searchDialog.open) searchDialog.showModal();
    requestAnimationFrame(() => searchInput.focus());
  }

  document.querySelector(".search-trigger")?.addEventListener("click", openSearch);
  document.querySelector(".search-close")?.addEventListener("click", () => searchDialog.close());
  searchInput?.addEventListener("input", () => renderSearch(searchInput.value));
  searchDialog?.addEventListener("click", (event) => {
    if (event.target === searchDialog) searchDialog.close();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
    }
  });

  const observedSections = [...document.querySelectorAll("main section[id]")];
  const navLinks = [...document.querySelectorAll('.sidebar a[href^="#"], .toc a[href^="#"]')];
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!visible) return;
      navLinks.forEach((link) => link.classList.toggle("active", link.hash === `#${visible.target.id}`));
    }, { rootMargin: "-18% 0px -68% 0px", threshold: 0 });
    observedSections.forEach((section) => observer.observe(section));
  }
})();
