(() => {
  const syncBtn = document.getElementById("sync-btn");
  const syncStatus = document.getElementById("sync-status");
  const pageError = document.getElementById("page-error");

  function hideError() {
    if (pageError) {
      pageError.textContent = "";
      pageError.classList.add("is-hidden");
    }
  }

  function showError(msg) {
    if (!pageError) return;
    pageError.textContent = msg;
    pageError.classList.remove("is-hidden");
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      /* ignore */
    }
    if (!res.ok) {
      const err = data.error || `HTTP ${res.status}`;
      throw new Error(err);
    }
    return data;
  }

  document.querySelectorAll(".vote button").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      hideError();
      const tr = e.target.closest("tr");
      const id = parseInt(tr.dataset.id, 10);
      const delta = parseInt(btn.dataset.delta, 10);
      const buttons = tr.querySelectorAll(".vote button");
      buttons.forEach((b) => {
        b.disabled = true;
      });
      try {
        await postJson("/api/continente/vote", { product_id: id, delta });
        window.location.reload();
      } catch (err) {
        showError(err.message || "Vote failed.");
        buttons.forEach((b) => {
          b.disabled = false;
        });
      }
    });
  });

  document.querySelectorAll(".notify button").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      hideError();
      const tr = e.target.closest("tr");
      const id = parseInt(tr.dataset.id, 10);
      const enabled = btn.dataset.enabled !== "1";
      btn.disabled = true;
      try {
        await postJson("/api/continente/notify", { product_id: id, enabled });
        window.location.reload();
      } catch (err) {
        showError(err.message || "Could not update alerts.");
        btn.disabled = false;
      }
    });
  });

  if (syncBtn && syncStatus) {
    syncBtn.addEventListener("click", async () => {
      hideError();
      syncBtn.disabled = true;
      syncStatus.textContent = "Syncing…";
      try {
        const data = await postJson("/api/continente/sync", {});
        const parts = [];
        if (typeof data.inserted === "number") parts.push(`${data.inserted} row(s) updated`);
        if (typeof data.alerts_sent === "number") parts.push(`${data.alerts_sent} alert(s)`);
        if (typeof data.sources_ok === "number" && data.sources_ok === 0 && data.inserted === 0) {
          parts.push("no endpoint returned products (check CONTINENTE_ENDPOINTS / auth)");
        }
        syncStatus.textContent = parts.length ? parts.join(" · ") : "Done.";
        window.location.reload();
      } catch (err) {
        syncStatus.textContent = "";
        showError(err.message || "Sync failed.");
      } finally {
        syncBtn.disabled = false;
      }
    });
  }
})();
