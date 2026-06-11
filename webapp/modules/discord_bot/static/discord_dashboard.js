(function () {
  const autolab = window.autolab || {}
  const statusEl = autolab.id('lb-status')
  const wrapEl = autolab.id('lb-table-wrap')

  function esc (s) {
    const d = document.createElement('div')
    d.textContent = s
    return d.innerHTML
  }

  function render (players) {
    if (!players.length) {
      statusEl.textContent = ''
      statusEl.classList.remove('is-error')
      wrapEl.innerHTML = '<p class="empty">No players in stats yet. Use the bot in Discord to record matches.</p>'
      wrapEl.classList.remove('is-hidden')
      return
    }

    statusEl.textContent = ''
    statusEl.classList.remove('is-error')

    const head =
      '<thead><tr>' +
      '<th>#</th><th>Player</th><th class="num">Elo</th>' +
      '<th class="num">W–D–L</th><th class="num">WR</th><th>Discord ID</th>' +
      '</tr></thead>'

    let body = '<tbody>'
    players.forEach(function (p, i) {
      const rec = p.wins + '-' + p.draws + '-' + p.losses
      const wr = p.win_rate == null ? '—' : String(p.win_rate) + '%'
      body +=
        '<tr>' +
        '<td>' + (i + 1) + '</td>' +
        '<td>' + esc(p.name) + '</td>' +
        '<td class="num">' + esc(String(p.points)) + '</td>' +
        '<td class="num">' + esc(rec) + '</td>' +
        '<td class="num">' + esc(wr) + '</td>' +
        '<td><code>' + esc(p.id) + '</code></td>' +
        '</tr>'
    })
    body += '</tbody>'

    wrapEl.innerHTML = '<table class="lb">' + head + body + '</table>'
    wrapEl.classList.remove('is-hidden')
  }

  autolab.fetchJSON('/api/discord/leaderboard')
    .then(function (data) {
      render(data.players || [])
    })
    .catch(function (err) {
      statusEl.textContent = 'Could not load leaderboard: ' + err.message
      statusEl.classList.add('is-error')
      wrapEl.classList.add('is-hidden')
    })
})()
