(() => {
  const namespaceInput = document.querySelector("#namespace-input");
  const keyInput = document.querySelector("#key-input");
  const requestUrl = document.querySelector("#request-url");
  const runButton = document.querySelector("#run-request");

  if (!namespaceInput || !keyInput || !requestUrl || !runButton) {
    return;
  }

  const operationButtons = [...document.querySelectorAll("[data-operation]")];
  const copyButton = document.querySelector("#copy-url");
  const responseStatus = document.querySelector("#response-status");
  const responseJson = document.querySelector("#response-json code");
  const counterValue = document.querySelector("#counter-value");
  const runLabel = document.querySelector("#run-label");
  const configuredBaseUrl = window.SUANPAN_DOCS?.apiBaseUrl || window.location.origin;
  const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");
  let operation = "hit";

  const randomSuffix = Math.random().toString(36).slice(2, 7);
  namespaceInput.value = `demo-${randomSuffix}`;

  function cleanSegment(value, fallback) {
    const cleaned = value.trim().replace(/[^a-zA-Z0-9._-]/g, "-");
    return cleaned || fallback;
  }

  function buildUrl() {
    const namespace = encodeURIComponent(cleanSegment(namespaceInput.value, "demo"));
    const key = encodeURIComponent(cleanSegment(keyInput.value, "homepage"));
    return `${apiBaseUrl}/${operation}/${namespace}/${key}`;
  }

  function updateRequestPreview() {
    requestUrl.textContent = buildUrl();
    runLabel.textContent = operation === "hit" ? "Count once" : "Read counter";
  }

  function setStatus(label, state) {
    responseStatus.textContent = label;
    responseStatus.className = `response-status is-${state}`;
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

  [namespaceInput, keyInput].forEach((input) => {
    input.addEventListener("input", updateRequestPreview);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        runButton.click();
      }
    });
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
      counterValue.textContent = "—";
      responseJson.textContent = JSON.stringify(
        { detail: "Could not reach the API from this preview.", error: error.message },
        null,
        2,
      );
      setStatus("Offline", "error");
    } finally {
      runButton.disabled = false;
    }
  });

  updateRequestPreview();
})();
