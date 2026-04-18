(function () {
  var elExport = document.getElementById('export-layout-btn');
  var elImportText = document.getElementById('import-layout-text');
  var elImportBtn = document.getElementById('import-layout-btn');
  var elAddBettor = document.getElementById('add-bettor-btn');
  var elBettorId = document.getElementById('new-bettor-id');
  var elChName = document.getElementById('new-ch-name');
  var elChSe = document.getElementById('new-ch-seid');
  var elChSteam = document.getElementById('new-ch-steam');
  var elChFaceit = document.getElementById('new-ch-faceit');
  var elChBettors = document.getElementById('new-ch-bettors');
  var elChPrimary = document.getElementById('new-ch-primary');
  var elAddChannel = document.getElementById('add-channel-btn');
  if (!elExport || !elImportBtn) return;

  function toast(msg, type) {
    type = type || 'ok';
    var el = document.getElementById('notif');
    if (!el) {
      window.alert(msg);
      return;
    }
    el.textContent = msg;
    el.className = 'notif-inner ' + type + ' show';
    clearTimeout(toast._t);
    toast._t = setTimeout(function () {
      el.classList.remove('show');
    }, 4000);
  }

  function refreshBettorPickers() {
    if (!elChBettors || !elChPrimary) return;
    fetch('/api/channels_snapshot')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var ids = Object.keys(data.accounts || data.bettors || {}).sort();
        elChBettors.innerHTML = '';
        elChPrimary.innerHTML = '<option value="">—</option>';
        ids.forEach(function (id) {
          var lab = document.createElement('label');
          var cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.value = id;
          cb.setAttribute('data-account-cb', '1');
          lab.appendChild(cb);
          lab.appendChild(document.createTextNode(' ' + id));
          elChBettors.appendChild(lab);
          var opt = document.createElement('option');
          opt.value = id;
          opt.textContent = id;
          elChPrimary.appendChild(opt);
        });
      })
      .catch(function () {});
  }

  elExport.addEventListener('click', function () {
    fetch('/api/channels_snapshot')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'channels_snapshot.json';
        a.click();
        URL.revokeObjectURL(a.href);
        toast('Exported channels_snapshot.json', 'ok');
      })
      .catch(function () { toast('Export failed', 'error'); });
  });

  elImportBtn.addEventListener('click', function () {
    var raw = (elImportText && elImportText.value) || '';
    var data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      toast('Invalid JSON', 'warn');
      return;
    }
    if (!window.confirm('Replace all accounts, channels, and viewers in the database?')) return;
    fetch('/api/channels_snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          toast(res.body.error || 'Import failed', 'error');
          return;
        }
        toast('Import applied. Reloading…', 'ok');
        window.location.reload();
      })
      .catch(function () { toast('Network error', 'error'); });
  });

  if (elAddBettor) {
    elAddBettor.addEventListener('click', function () {
      var id = elBettorId && elBettorId.value.trim();
      if (!id) {
        toast('Account id required', 'warn');
        return;
      }
      fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: id }),
      })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
          if (!res.ok) {
            toast(res.body.error || 'Failed', 'error');
            return;
          }
          if (elBettorId) elBettorId.value = '';
          toast('Account added. Reloading…', 'ok');
          window.location.reload();
        })
        .catch(function () { toast('Network error', 'error'); });
    });
  }

  if (elAddChannel) {
    elAddChannel.addEventListener('click', function () {
      var name = elChName && elChName.value.trim();
      var sid = elChSe && elChSe.value.trim();
      if (!name || !sid) {
        toast('Channel name and StreamElements id required', 'warn');
        return;
      }
      var steam = elChSteam && elChSteam.value.trim();
      var faceit = elChFaceit && elChFaceit.value.trim();
      var primary = elChPrimary && elChPrimary.value;
      var checked = [];
      if (elChBettors) {
        elChBettors.querySelectorAll('input[type="checkbox"][data-account-cb]').forEach(function (cb) {
          if (cb.checked) checked.push(cb.value);
        });
      }
      var body = {
        name: name,
        streamelements_id: sid,
        steam_id: steam || null,
        faceit_id: faceit || null,
      };
      if (checked.length) {
        var Bettors = {};
        checked.forEach(function (bid) {
          Bettors[bid] = primary === bid;
        });
        body.Bettors = Bettors;
      }
      fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
          if (!res.ok) {
            toast(res.body.error || 'Failed', 'error');
            return;
          }
          if (elChName) elChName.value = '';
          if (elChSe) elChSe.value = '';
          if (elChSteam) elChSteam.value = '';
          if (elChFaceit) elChFaceit.value = '';
          if (elChPrimary) elChPrimary.value = '';
          toast('Channel added. Reloading…', 'ok');
          window.location.reload();
        })
        .catch(function () { toast('Network error', 'error'); });
    });
  }

  refreshBettorPickers();
})();
