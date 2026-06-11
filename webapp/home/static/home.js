(function () {
  'use strict';

  var autolab = window.autolab || {};
  var banner = autolab.id('restart-banner');
  var copyBtn = autolab.id('copy-restart-cmd');
  var saveBtn = autolab.id('save-modules-btn');
  var restartCmdEl = autolab.id('restart-cmd');
  var initialState = {};
  var draftState = {};
  var toggles = autolab.qsa('.module-toggle');

  toggles.forEach(function (el) {
    initialState[el.dataset.module] = el.checked;
    draftState[el.dataset.module] = el.checked;
  });

  function refreshBanner() {
    var dirty = toggles.some(function (el) {
      return draftState[el.dataset.module] !== initialState[el.dataset.module];
    });
    if (banner) banner.hidden = !dirty;
    if (saveBtn) saveBtn.disabled = !dirty;
  }

  toggles.forEach(function (el) {
    autolab.on(el, 'click', function (e) { e.stopPropagation(); });
    autolab.on(el, 'change', function () {
      var name = el.dataset.module;
      var enabled = el.checked;
      draftState[name] = enabled;
      var wrap = el.closest('.card-wrap');
      var card = wrap ? wrap.querySelector('.card') : null;
      if (card) card.classList.toggle('card-off', !enabled);
      refreshBanner();
    });
  });

  if (saveBtn) {
    autolab.on(saveBtn, 'click', async function () {
      var state = {};
      toggles.forEach(function (el) {
        state[el.dataset.module] = draftState[el.dataset.module];
      });

      saveBtn.disabled = true;
      toggles.forEach(function (el) { el.disabled = true; });
      try {
        await autolab.postJSON('/api/modules', { state: state });
        Object.keys(state).forEach(function (name) {
          initialState[name] = state[name];
        });
        refreshBanner();
      } catch (err) {
        alert('Failed to save module changes: ' + err.message);
        saveBtn.disabled = false;
      } finally {
        toggles.forEach(function (el) { el.disabled = false; });
      }
    });
  }

  if (copyBtn) {
    autolab.on(copyBtn, 'click', async function () {
      var text = restartCmdEl ? restartCmdEl.textContent.trim() : '';
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = 'Copied';
        setTimeout(function () { copyBtn.textContent = 'Copy command'; }, 2000);
      } catch {
        copyBtn.textContent = 'Select & copy manually';
      }
    });
  }

  refreshBanner();
})();
