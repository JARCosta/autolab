(function () {
  var selected = {};
  var players = [];
  var allMatches = [];
  var notifTimer = null;

  var elRoster = document.getElementById('roster');
  var elMatches = document.getElementById('matches');
  var elCreateBtn = document.getElementById('create-btn');
  var elCount = document.getElementById('create-count');
  var elNotif = document.getElementById('notif');
  var elAddName = document.getElementById('add-name');
  var elAddBtn = document.getElementById('add-btn');

  function notify(msg, type) {
    type = type || 'warn';
    elNotif.textContent = msg;
    elNotif.className = 'notif-inner ' + type + ' show';
    clearTimeout(notifTimer);
    notifTimer = setTimeout(function () {
      elNotif.classList.remove('show');
    }, 3500);
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); });
  }

  function fmtDate(iso) {
    var d = new Date(iso);
    var mo = d.toLocaleString(undefined, { month: 'short' });
    var day = d.getDate();
    var h = String(d.getHours()).padStart(2, '0');
    var m = String(d.getMinutes()).padStart(2, '0');
    return mo + ' ' + day + ', ' + h + ':' + m;
  }

  function playerNameById(id) {
    for (var i = 0; i < players.length; i++) {
      if (players[i].id === id) return players[i].name;
    }
    return 'Unknown';
  }

  function updateCreateBtn() {
    var ids = Object.keys(selected);
    var n = ids.length;
    elCount.textContent = n > 0 ? '(' + n + ')' : '';
    elCreateBtn.disabled = n < 2;
  }

  function renderRoster() {
    var html = '';
    for (var i = 0; i < players.length; i++) {
      var p = players[i];
      var sel = !!selected[p.id];
      var record = p.wins + '-' + p.draws + '-' + p.losses;
      html += '<label class="player-row' + (sel ? ' selected' : '') + '" data-id="' + p.id + '">'
        + '<input type="checkbox"' + (sel ? ' checked' : '') + '>'
        + '<span class="player-rank">' + (i + 1) + '</span>'
        + '<span class="player-name">' + esc(p.name) + '</span>'
        + '<span class="player-elo">' + p.points + '</span>'
        + '<span class="player-record">' + record + '</span>'
        + '</label>';
    }
    if (!players.length) {
      html = '<p class="roster-empty">No players yet. Add one below.</p>';
    }
    elRoster.innerHTML = html;

    elRoster.querySelectorAll('.player-row input').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var row = cb.closest('.player-row');
        var id = row.getAttribute('data-id');
        if (cb.checked) {
          selected[id] = true;
          row.classList.add('selected');
        } else {
          delete selected[id];
          row.classList.remove('selected');
        }
        updateCreateBtn();
      });
    });
  }

  function renderMatches() {
    if (!allMatches.length) {
      elMatches.innerHTML = '<p class="empty-state">No matches yet. Select players and create a custom.</p>';
      return;
    }
    var html = '';
    for (var i = 0; i < allMatches.length; i++) {
      html += buildMatchCard(allMatches[i]);
    }
    elMatches.innerHTML = html;
    bindMatchEvents();
  }

  function buildMatchCard(m) {
    var scoreHtml;
    if (m.result === 'team_a') {
      scoreHtml = '<span class="win">1</span> - <span class="loss">0</span>';
    } else if (m.result === 'team_b') {
      scoreHtml = '<span class="loss">0</span> - <span class="win">1</span>';
    } else if (m.result === 'draw') {
      scoreHtml = '<span class="draw">Draw</span>';
    } else if (m.result === 'cancelled') {
      scoreHtml = '<span class="cancelled">Cancelled</span>';
    } else {
      scoreHtml = '<span class="pending">vs</span>';
    }

    var teamANames = m.team_a_names || m.team_a.map(playerNameById);
    var teamBNames = m.team_b_names || m.team_b.map(playerNameById);

    var teamAPts = 0;
    var teamBPts = 0;
    for (var k = 0; k < players.length; k++) {
      if (m.team_a.indexOf(players[k].id) !== -1) teamAPts += players[k].points;
      if (m.team_b.indexOf(players[k].id) !== -1) teamBPts += players[k].points;
    }

    var h = '<div class="match-card" data-match-id="' + m.id + '">';
    h += '<div class="match-header">';
    h += '<span class="match-title">' + esc(m.title) + '</span>';
    h += '<span class="match-date">' + fmtDate(m.created_at) + '</span>';
    h += '</div>';
    h += '<div class="match-body">';

    h += '<div class="match-score-row">';
    h += '<div class="match-side left">';
    h += '<div class="match-team-label a">Team A</div>';
    h += '<div class="match-pts">' + teamAPts + ' pts</div>';
    h += '</div>';
    h += '<div class="match-score">' + scoreHtml + '</div>';
    h += '<div class="match-side right">';
    h += '<div class="match-team-label b">Team B</div>';
    h += '<div class="match-pts">' + teamBPts + ' pts</div>';
    h += '</div>';
    h += '</div>';

    h += '<div class="match-teams">';
    h += '<div class="team-col a">';
    for (var a = 0; a < teamANames.length; a++) {
      h += '<div class="team-player">' + esc(teamANames[a]) + '</div>';
    }
    h += '</div>';
    h += '<div class="team-col b">';
    for (var b = 0; b < teamBNames.length; b++) {
      h += '<div class="team-player">' + esc(teamBNames[b]) + '</div>';
    }
    h += '</div>';
    h += '</div>';

    if (m.result === null) {
      h += '<div class="match-actions">';
      h += '<button class="btn-win-a" data-action="team_a">Team A Wins</button>';
      h += '<button data-action="draw">Draw</button>';
      h += '<button class="btn-win-b" data-action="team_b">Team B Wins</button>';
      h += '<button class="btn-cancel" data-action="cancelled">Cancel</button>';
      h += '</div>';
    }

    h += '</div>';

    h += '<button class="stats-toggle" data-toggle-stats="' + m.id + '">';
    h += '<span class="arrow">&#9654;</span> Player Stats';
    h += '</button>';
    h += '<div class="stats-panel" id="stats-' + m.id + '">';
    h += buildStatsTable(m, 'a');
    h += buildStatsTable(m, 'b');
    h += '</div>';

    h += '</div>';
    return h;
  }

  function buildStatsTable(m, team) {
    var ids = team === 'a' ? m.team_a : m.team_b;
    var names = team === 'a'
      ? (m.team_a_names || m.team_a.map(playerNameById))
      : (m.team_b_names || m.team_b.map(playerNameById));
    var ps = m.player_stats || {};
    var lbl = team === 'a' ? 'Team A' : 'Team B';
    var cls = team === 'a' ? 'a' : 'b';

    var h = '<div class="stats-team-label ' + cls + '">' + lbl + '</div>';
    h += '<table class="stats-table"><thead><tr>';
    h += '<th>Player</th><th>K</th><th>D</th><th>A</th><th>DMG</th>';
    h += '</tr></thead><tbody>';
    for (var i = 0; i < ids.length; i++) {
      var s = ps[ids[i]] || {};
      h += '<tr>';
      h += '<td>' + esc(names[i]) + '</td>';
      h += statCell(m.id, ids[i], 'kills', s.kills);
      h += statCell(m.id, ids[i], 'deaths', s.deaths);
      h += statCell(m.id, ids[i], 'assists', s.assists);
      h += statCell(m.id, ids[i], 'damage', s.damage);
      h += '</tr>';
    }
    h += '</tbody></table>';
    return h;
  }

  function statCell(matchId, playerId, field, val) {
    return '<td><input type="number" min="0" placeholder="-" '
      + 'data-mid="' + matchId + '" data-pid="' + playerId + '" data-field="' + field + '" '
      + (val != null ? 'value="' + val + '"' : '')
      + '></td>';
  }

  function bindMatchEvents() {
    document.querySelectorAll('.match-actions button[data-action]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var card = btn.closest('.match-card');
        var mid = card.getAttribute('data-match-id');
        var action = btn.getAttribute('data-action');
        postJSON('/api/boost/match/' + mid + '/result', { result: action })
          .then(function (res) {
            if (res.error) return notify(res.error, 'error');
            notify('Result recorded', 'ok');
            loadAll();
          });
      });
    });

    document.querySelectorAll('[data-toggle-stats]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mid = btn.getAttribute('data-toggle-stats');
        var panel = document.getElementById('stats-' + mid);
        var open = panel.classList.toggle('open');
        btn.classList.toggle('open', open);
      });
    });

    document.querySelectorAll('.stats-table input').forEach(function (inp) {
      var timer;
      inp.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          var mid = inp.getAttribute('data-mid');
          var pid = inp.getAttribute('data-pid');
          var row = inp.closest('tr');
          var inputs = row.querySelectorAll('input');
          var stats = {};
          inputs.forEach(function (i) {
            var v = i.value.trim();
            if (v !== '') stats[i.getAttribute('data-field')] = parseInt(v, 10);
          });
          postJSON('/api/boost/match/' + mid + '/stats', {
            player_id: pid,
            stats: stats
          });
        }, 600);
      });
    });
  }

  function esc(s) {
    var el = document.createElement('span');
    el.textContent = s || '';
    return el.innerHTML;
  }

  function loadPlayers() {
    return fetch('/api/boost/players').then(function (r) { return r.json(); })
      .then(function (data) {
        players = data.players || [];
        renderRoster();
        updateCreateBtn();
      });
  }

  function loadMatches() {
    return fetch('/api/boost/matches').then(function (r) { return r.json(); })
      .then(function (data) {
        allMatches = data.matches || [];
        renderMatches();
      });
  }

  function loadAll() {
    loadPlayers().then(loadMatches);
  }

  elCreateBtn.addEventListener('click', function () {
    var ids = Object.keys(selected);
    if (ids.length < 2) return notify('Select at least 2 players.', 'warn');
    if (ids.length % 2 !== 0) return notify('Need an even number of players.', 'warn');
    postJSON('/api/boost/queue', { players: ids })
      .then(function (res) {
        if (res.error) return notify(res.error, 'error');
        selected = {};
        notify('Custom created - teams balanced!', 'ok');
        loadAll();
      });
  });

  function addPlayer() {
    var name = elAddName.value.trim();
    if (!name) return;
    postJSON('/api/boost/players', { name: name })
      .then(function (res) {
        if (res.error) return notify(res.error, 'error');
        elAddName.value = '';
        loadPlayers();
      });
  }
  elAddBtn.addEventListener('click', addPlayer);
  elAddName.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') addPlayer();
  });

  loadAll();
})();
