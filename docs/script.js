(() => {
  const keyInput = document.querySelector("#key-input");
  const requestUrl = document.querySelector("#request-url");
  const runButton = document.querySelector("#run-request");

  if (!keyInput || !requestUrl || !runButton) {
    return;
  }

  const operationButtons = [...document.querySelectorAll("[data-operation]")];
  const copyButton = document.querySelector("#copy-url");
  const responseStatus = document.querySelector("#response-status");
  const responseJson = document.querySelector("#response-json code");
  const counterValue = document.querySelector("#counter-value");
  const runLabel = document.querySelector("#run-label");
  const apiStatus = document.querySelector("#api-status");
  const apiStatusLabel = document.querySelector("#api-status-label");
  const configuredBaseUrl = window.SUANPAN_DOCS?.apiBaseUrl || window.location.origin;
  const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");
  const playgroundNamespace = "playground";
  let operation = "hit";
  let checkingApi = false;

  function cleanSegment(value, fallback) {
    const cleaned = value.trim().replace(/[^a-zA-Z0-9._-]/g, "-");
    return cleaned || fallback;
  }

  function buildUrl() {
    const key = encodeURIComponent(cleanSegment(keyInput.value, "homepage"));
    return `${apiBaseUrl}/${operation}/${playgroundNamespace}/${key}`;
  }

  function updateRequestPreview() {
    requestUrl.textContent = buildUrl();
    runLabel.textContent = operation === "hit" ? "Count once" : "Read counter";
  }

  function setStatus(label, state) {
    responseStatus.textContent = label;
    responseStatus.className = `response-status is-${state}`;
  }

  function setApiStatus(online) {
    apiStatus.className = `live-indicator is-${online ? "online" : "offline"}`;
    apiStatusLabel.textContent = online ? "API live" : "API offline";
  }

  async function checkApiStatus() {
    if (checkingApi) return;
    checkingApi = true;

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${apiBaseUrl}/healthcheck`, {
        cache: "no-store",
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
      const health = response.ok ? await response.json() : null;
      setApiStatus(response.ok && health?.status === "healthy");
    } catch {
      setApiStatus(false);
    } finally {
      window.clearTimeout(timeout);
      checkingApi = false;
    }
  }

  function showResponse(payload, statusCode, ok) {
    const value = payload && typeof payload.value !== "undefined" ? payload.value : "—";
    counterValue.textContent = value;
    responseJson.textContent = JSON.stringify(payload, null, 2);
    setStatus(ok ? `${statusCode} OK` : `${statusCode} Error`, ok ? "success" : "error");
  }

  operationButtons.forEach((button) => {
    button.addEventListener("click", () => {
      operation = button.dataset.operation;
      operationButtons.forEach((candidate) => {
        const isSelected = candidate === button;
        candidate.classList.toggle("is-selected", isSelected);
        candidate.setAttribute("aria-pressed", String(isSelected));
      });
      updateRequestPreview();
    });
  });

  keyInput.addEventListener("input", updateRequestPreview);
  keyInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runButton.click();
    }
  });

  copyButton?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(buildUrl());
      copyButton.textContent = "Copied";
      window.setTimeout(() => {
        copyButton.textContent = "Copy URL";
      }, 1400);
    } catch {
      copyButton.textContent = "Copy failed";
    }
  });

  runButton.addEventListener("click", async () => {
    runButton.disabled = true;
    setStatus("Sending…", "idle");

    try {
      const response = await fetch(buildUrl(), { headers: { Accept: "application/json" } });
      const responseText = await response.text();
      let payload;

      try {
        payload = JSON.parse(responseText);
      } catch {
        payload = { detail: responseText || "The API returned an empty response." };
      }

      showResponse(payload, response.status, response.ok);
    } catch (error) {
      setApiStatus(false);
      counterValue.textContent = "—";
      responseJson.textContent = JSON.stringify(
        { detail: "Could not reach the API from this preview.", error: error.message },
        null,
        2,
      );
      setStatus("Offline", "error");
    } finally {
      runButton.disabled = false;
      void checkApiStatus();
    }
  });

  updateRequestPreview();
  void checkApiStatus();
  window.setInterval(() => {
    if (!document.hidden) void checkApiStatus();
  }, 30000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void checkApiStatus();
  });
})();
