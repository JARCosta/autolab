(() => {
  const autolab = window.autolab || {};
  const syncBtn = autolab.id("sync-btn");
  const syncStatus = autolab.id("sync-status");
  const pageError = autolab.id("page-error");

  function hideError() { if (pageError) { pageError.textContent = ""; autolab.cls.add(pageError, 'is-hidden'); } }

  function showError(msg) { if (!pageError) return; pageError.textContent = msg; autolab.cls.remove(pageError, 'is-hidden'); }

  var postJson = autolab.postJSON;

  autolab.qsa('.vote button').forEach((btn) => {
    autolab.on(btn, 'click', async (e) => {
      hideError();
      const tr = e.target.closest('tr');
      const id = parseInt(tr.dataset.id, 10);
      const delta = parseInt(btn.dataset.delta, 10);
      var buttons = Array.prototype.slice.call(tr.querySelectorAll('.vote button'));
      buttons.forEach((b) => { b.disabled = true; });
      try {
        await postJson('/api/continente/vote', { product_id: id, delta });
        window.location.reload();
      } catch (err) {
        showError(err.message || 'Vote failed.');
        buttons.forEach((b) => { b.disabled = false; });
      }
    });
  });

  autolab.qsa('.notify button').forEach((btn) => {
    autolab.on(btn, 'click', async (e) => {
      hideError();
      const tr = e.target.closest('tr');
      const id = parseInt(tr.dataset.id, 10);
      const enabled = btn.dataset.enabled !== '1';
      btn.disabled = true;
      try {
        await postJson('/api/continente/notify', { product_id: id, enabled });
        window.location.reload();
      } catch (err) {
        showError(err.message || 'Could not update alerts.');
        btn.disabled = false;
      }
    });
  });

  if (syncBtn && syncStatus) {
    autolab.on(syncBtn, 'click', async () => {
      hideError();
      syncBtn.disabled = true;
      syncStatus.textContent = 'Syncing…';
      try {
        const data = await postJson('/api/continente/sync', {});
        const parts = [];
        if (typeof data.inserted === 'number') parts.push(data.inserted + ' row(s) updated');
        if (typeof data.alerts_sent === 'number') parts.push(data.alerts_sent + ' alert(s)');
        if (typeof data.sources_ok === 'number' && data.sources_ok === 0 && data.inserted === 0) {
          parts.push('no endpoint returned products (check CONTINENTE_ENDPOINTS / auth)');
        }
        syncStatus.textContent = parts.length ? parts.join(' · ') : 'Done.';
        window.location.reload();
      } catch (err) {
        syncStatus.textContent = '';
        showError(err.message || 'Sync failed.');
      } finally {
        syncBtn.disabled = false;
      }
    });
  }
})();
