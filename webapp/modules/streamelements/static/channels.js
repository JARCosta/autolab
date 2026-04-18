(function () {
  var elList = document.getElementById('channel-list');
  var elAddInput = document.getElementById('add-channel-input');
  var elAddBtn = document.getElementById('add-channel-btn');
  var elSave = document.getElementById('save-btn');
  var elNotif = document.getElementById('notif');
  var elDlg = document.getElementById('ch-meta-dlg');
  var elDlgTitle = document.getElementById('ch-meta-dlg-title');
  var elSid = document.getElementById('ch-meta-sid');
  var elSteam = document.getElementById('ch-meta-steam');
  var elFaceit = document.getElementById('ch-meta-faceit');
  var elDlgErr = document.getElementById('ch-meta-err');
  var elDlgCancel = document.getElementById('ch-meta-cancel');
  var elDlgConfirm = document.getElementById('ch-meta-confirm');
  var elSidApi = document.getElementById('ch-meta-sid-api');
  if (
    !elList || !elAddInput || !elAddBtn || !elSave || !elNotif
    || !elDlg || !elDlgTitle || !elSid || !elSteam || !elFaceit
    || !elDlgErr || !elDlgCancel || !elDlgConfirm || !elSidApi
  ) {
    return;
  }

  var STREAMELEMENTS_CHANNEL_API = 'https://api.streamelements.com/kappa/v2/channels/';

  var channels = {};
  /** DB channel rows (no Bettors), keyed by lowercase name */
  var channelDefs = {};
  var bettorAccounts = [];
  var expandedChannels = {};
  var dirty = false;
  var notifTimer = null;
  /** @type {{ mode: 'sidebar_add' | 'edit_meta', channel: string } | null} */
  var dlgContext = null;

  function notify(msg, type) {
    type = type || 'warn';
    elNotif.textContent = msg;
    elNotif.className = 'notif-inner ' + type + ' show';
    clearTimeout(notifTimer);
    notifTimer = setTimeout(function () {
      elNotif.classList.remove('show');
    }, 3800);
  }

  function esc(s) {
    if (!s) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bettorsMapForChannel(channel) {
    var ch = channels[channel];
    if (!ch) return {};
    if (ch.Bettors && typeof ch.Bettors === 'object' && !Array.isArray(ch.Bettors)) {
      return ch.Bettors;
    }
    var out = {};
    Object.keys(ch).forEach(function (k) {
      if (k === 'StreamElementsId' || k === 'SteamId' || k === 'FaceitId' || k === 'Bettors') {
        return;
      }
      out[k] = ch[k];
    });
    return out;
  }

  function connectedSet(channel) {
    var m = bettorsMapForChannel(channel);
    var set = {};
    Object.keys(m).forEach(function (u) {
      set[u] = true;
    });
    return set;
  }

  function bettorForChannel(channel) {
    var m = bettorsMapForChannel(channel);
    var k = Object.keys(m);
    for (var i = 0; i < k.length; i++) {
      if (m[k[i]] === true) return k[i];
    }
    return '';
  }

  function rebuildChannel(channel, conn, bettorUser) {
    var users = {};
    bettorAccounts.forEach(function (u) {
      if (conn[u]) {
        users[u] = bettorUser === u;
      }
    });
    if (Object.keys(users).length === 0) {
      delete channels[channel];
    } else {
      var prev = channels[channel] || {};
      var row = { Bettors: users };
      if (prev.StreamElementsId) row.StreamElementsId = prev.StreamElementsId;
      if (prev.SteamId) row.SteamId = prev.SteamId;
      if (prev.FaceitId) row.FaceitId = prev.FaceitId;
      channels[channel] = row;
    }
    dirty = true;
    elSave.disabled = false;
  }

  function normalizeChannelName(raw) {
    return String(raw || '').trim().toLowerCase().replace(/^#+/, '');
  }

  function strTrim(x) {
    return x == null ? '' : String(x).trim();
  }

  function metaFromInputs(sid, steam, faceit) {
    var o = { StreamElementsId: strTrim(sid) };
    if (strTrim(steam)) o.SteamId = strTrim(steam);
    if (strTrim(faceit)) o.FaceitId = strTrim(faceit);
    return o;
  }

  function metaNeedsPersist(ch, next) {
    var cur = channelDefs[ch];
    if (!cur) return true;
    if (strTrim(next.StreamElementsId) !== strTrim(cur.StreamElementsId)) return true;
    if (strTrim(next.SteamId) !== strTrim(cur.SteamId || '')) return true;
    if (strTrim(next.FaceitId) !== strTrim(cur.FaceitId || '')) return true;
    return false;
  }

  function setDlgError(msg) {
    if (msg) {
      elDlgErr.textContent = msg;
      elDlgErr.classList.remove('is-hidden');
    } else {
      elDlgErr.textContent = '';
      elDlgErr.classList.add('is-hidden');
    }
  }

  function openChannelDialog(title, prefill) {
    elDlgTitle.textContent = title;
    elSid.value = strTrim(prefill.StreamElementsId);
    elSteam.value = strTrim(prefill.SteamId);
    elFaceit.value = strTrim(prefill.FaceitId);
    setDlgError('');
    var ch = dlgContext && dlgContext.channel ? dlgContext.channel : '';
    if (ch) {
      elSidApi.href = STREAMELEMENTS_CHANNEL_API + encodeURIComponent(ch);
      elSidApi.title = 'GET ' + elSidApi.href + ' — copy the _id value';
    } else {
      elSidApi.href = '#';
      elSidApi.removeAttribute('title');
    }
    elSidApi.setAttribute('aria-hidden', ch ? 'false' : 'true');
    elSidApi.classList.toggle('is-hidden', !ch);
    elDlg.classList.remove('is-hidden');
    elDlg.setAttribute('aria-hidden', 'false');
    elSid.focus();
  }

  function closeChannelDialog() {
    dlgContext = null;
    elDlg.classList.add('is-hidden');
    elDlg.setAttribute('aria-hidden', 'true');
    setDlgError('');
  }

  function postChannelMeta(ch, meta) {
    return fetch('/api/channel_meta', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: ch,
        streamelements_id: meta.StreamElementsId,
        steam_id: meta.SteamId || undefined,
        faceit_id: meta.FaceitId || undefined,
      }),
    }).then(function (r) {
      return r.json().then(function (j) {
        return { ok: r.ok, body: j };
      });
    });
  }

  function applyDefToCatalog(ch, def) {
    if (def && typeof def === 'object') {
      channelDefs[ch] = def;
    }
  }

  function confirmChannelDialog() {
    if (!dlgContext) return;
    var ch = dlgContext.channel;
    var mode = dlgContext.mode;
    var next = metaFromInputs(elSid.value, elSteam.value, elFaceit.value);
    if (!next.StreamElementsId) {
      setDlgError('StreamElements account ID is required.');
      return;
    }

    var persist = metaNeedsPersist(ch, next);
    var run;
    if (persist) {
      run = postChannelMeta(ch, next).then(function (res) {
        if (!res.ok) {
          setDlgError(res.body.error || 'Save failed');
          return Promise.reject(new Error('meta'));
        }
        applyDefToCatalog(ch, res.body.channel_def || next);
      });
    } else {
      run = Promise.resolve();
    }

    run.then(function () {
      var def = channelDefs[ch] || next;
      if (mode === 'sidebar_add') {
        var bet = bettorAccounts[0] || '';
        var users = {};
        bettorAccounts.forEach(function (u) {
          users[u] = u === bet;
        });
        channels[ch] = Object.assign({}, def, { Bettors: users });
        expandedChannels[ch] = true;
        elAddInput.value = '';
        dirty = true;
        elSave.disabled = false;
      } else if (mode === 'edit_meta') {
        var prev = channels[ch];
        var b = prev && prev.Bettors ? prev.Bettors : bettorsMapForChannel(ch);
        channels[ch] = Object.assign({}, def, { Bettors: b });
        dirty = true;
        elSave.disabled = false;
      }
      closeChannelDialog();
      renderList();
    }).catch(function () {
      /* error already in modal */
    });
  }

  function beginAddChannel() {
    var ch = normalizeChannelName(elAddInput.value);
    if (!ch) {
      notify('Enter a channel name.', 'warn');
      return;
    }
    if (channels[ch]) {
      notify('Channel already listed.', 'warn');
      return;
    }
    if (!bettorAccounts.length) {
      notify('Add at least one account (setup below) before attaching channels.', 'warn');
      return;
    }
    dlgContext = { mode: 'sidebar_add', channel: ch };
    var pre = Object.assign({}, channelDefs[ch] || {});
    openChannelDialog('Add channel: ' + ch, pre);
  }

  function beginEditMeta(ch) {
    dlgContext = { mode: 'edit_meta', channel: ch };
    var pre = Object.assign({}, channelDefs[ch] || {}, channels[ch] || {});
    openChannelDialog('Channel data: ' + ch, pre);
  }

  function renderList() {
    /* ``channels`` from JSON keeps server key order (SQL ORDER BY sort_order, name). */
    var keys = Object.keys(channels);
    if (!keys.length) {
      elList.innerHTML = '<p class="list-empty">No channels yet. Add one below.</p>';
      return;
    }
    var html = '';
    keys.forEach(function (ch) {
      html += buildCardHtml(ch);
    });
    elList.innerHTML = html;
    bindListEvents();
  }

  function buildCardHtml(ch) {
    var conn = connectedSet(ch);
    var currentBettor = bettorForChannel(ch);
    var expanded = !!expandedChannels[ch];
    var toggles = '';
    bettorAccounts.forEach(function (u) {
      var on = !!conn[u];
      toggles += '<button type="button" class="acct-toggle' + (on ? ' active' : '') + '" '
        + 'data-ch="' + esc(ch) + '" data-user="' + esc(u) + '" '
        + 'aria-pressed="' + (on ? 'true' : 'false') + '">'
        + esc(u) + '</button>';
    });

    var sel = '<option value="">Viewers only</option>';
    bettorAccounts.forEach(function (u) {
      if (!conn[u]) return;
      var selAttr = u === currentBettor ? ' selected' : '';
      sel += '<option value="' + esc(u) + '"' + selAttr + '>' + esc(u) + '</option>';
    });

    var cardClass = 'ch-card' + (expanded ? ' is-expanded' : '');
    var toggleLabel = expanded ? 'Collapse channel' : 'Expand channel';
    var toggleIcon = expanded ? '▼' : '▶';
    var bodyId = 'ch-body-' + String(ch).replace(/[^a-zA-Z0-9_-]/g, '_');

    return '<div class="' + cardClass + '" data-channel="' + esc(ch) + '">'
      + '<div class="ch-card-head">'
      + '<button type="button" class="ch-toggle" data-ch="' + esc(ch) + '" '
      + 'aria-expanded="' + (expanded ? 'true' : 'false') + '" aria-controls="' + bodyId + '" '
      + 'aria-label="' + esc(toggleLabel) + '">'
      + toggleIcon + '</button>'
      + '<div class="ch-name-wrap">'
      + '<span class="ch-name">' + esc(ch) + '</span>'
      + '<button type="button" class="ch-info-btn" data-ch="' + esc(ch) + '" '
      + 'aria-label="Channel StreamElements and linked IDs" title="IDs">i</button>'
      + '</div>'
      + '<button type="button" class="ch-remove-icon" data-ch="' + esc(ch) + '" '
      + 'aria-label="Remove channel from list" title="Remove">🗑</button>'
      + '</div>'
      + '<div class="ch-card-body" id="' + bodyId + '" '
      + 'aria-hidden="' + (expanded ? 'false' : 'true') + '">'
      + '<div class="acct-toggle-label">Watching</div>'
      + '<div class="acct-toggle-row" role="group" aria-label="Accounts watching ' + esc(ch) + '">' + toggles + '</div>'
      + '<div class="bet-row">'
      + '<label for="bet-' + esc(ch) + '">Bet with</label>'
      + '<select id="bet-' + esc(ch) + '" class="bet-select" data-ch="' + esc(ch) + '">' + sel + '</select>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  function bindListEvents() {
    elList.querySelectorAll('.ch-toggle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var ch = btn.getAttribute('data-ch');
        expandedChannels[ch] = !expandedChannels[ch];
        renderList();
      });
    });

    elList.querySelectorAll('.ch-info-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var ch = btn.getAttribute('data-ch');
        beginEditMeta(ch);
      });
    });

    elList.querySelectorAll('.ch-remove-icon').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var ch = btn.getAttribute('data-ch');
        delete channels[ch];
        delete expandedChannels[ch];
        dirty = true;
        elSave.disabled = false;
        renderList();
      });
    });

    elList.querySelectorAll('.acct-toggle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var ch = btn.getAttribute('data-ch');
        var u = btn.getAttribute('data-user');
        var wasOn = btn.classList.contains('active');
        var conn = connectedSet(ch);
        if (wasOn) {
          delete conn[u];
        } else {
          conn[u] = true;
        }
        var prevBet = bettorForChannel(ch);
        var bet = prevBet;
        if (!conn[prevBet]) {
          bet = '';
          var names = Object.keys(conn);
          if (names.length === 1) bet = names[0];
        }
        rebuildChannel(ch, conn, bet);
        renderList();
      });
    });

    elList.querySelectorAll('.bet-select').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var ch = sel.getAttribute('data-ch');
        var bet = sel.value;
        var conn = connectedSet(ch);
        rebuildChannel(ch, conn, bet);
        renderList();
      });
    });
  }

  function load() {
    return fetch('/api/betting_channels')
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        channels = data.channels || {};
        channelDefs = data.channel_defs || {};
        bettorAccounts = data.accounts || data.bettors || [];
        expandedChannels = {};
        dirty = false;
        elSave.disabled = true;
        renderList();
      })
      .catch(function () {
        notify('Could not load settings.', 'error');
      });
  }

  function save() {
    elSave.disabled = true;
    fetch('/api/betting_channels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channels: channels }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          notify(res.body.error || 'Save failed', 'error');
          elSave.disabled = false;
          return;
        }
        channels = res.body.channels || channels;
        if (res.body.channel_defs) {
          channelDefs = res.body.channel_defs;
        }
        if (res.body.accounts) bettorAccounts = res.body.accounts;
        else if (res.body.bettors) bettorAccounts = res.body.bettors;
        dirty = false;
        elSave.disabled = true;
        notify('Saved. Restart AutoLab to apply.', 'ok');
        renderList();
      })
      .catch(function () {
        notify('Network error while saving.', 'error');
        elSave.disabled = false;
      });
  }

  elAddBtn.addEventListener('click', beginAddChannel);
  elAddInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      beginAddChannel();
    }
  });
  elSave.addEventListener('click', save);

  elDlgCancel.addEventListener('click', closeChannelDialog);
  elDlgConfirm.addEventListener('click', confirmChannelDialog);
  elDlg.addEventListener('click', function (e) {
    if (e.target === elDlg) {
      closeChannelDialog();
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !elDlg.classList.contains('is-hidden')) {
      closeChannelDialog();
    }
  });

  window.addEventListener('beforeunload', function (e) {
    if (dirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  load();
})();
