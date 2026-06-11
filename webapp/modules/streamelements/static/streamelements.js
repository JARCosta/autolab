(function () {
  var autolab = window.autolab || {};
  var chartPanel = autolab.id('chart-panel');
  var chartWrap = autolab.id('chart-wrap');
  var chartTitle = autolab.id('chart-title');
  var chartEmpty = autolab.id('chart-empty');
  var elStatus = autolab.id('status');
  var balanceChart = null;
  var selectedCell = null;
  var historyDays = null;
  var selectedChannel = null;
  var selectedBettor = null;
  var historySeriesCache = {};
  var historySeriesInflight = {};

  var gridColor = 'rgba(255,255,255,0.06)';
  var tickColor = '#888';

  function ensureChart() {
    if (balanceChart) return balanceChart;
    balanceChart = new Chart(autolab.id('chart'), {
      type: 'line',
      data: {
        datasets: [{
          borderColor: '#4caf50',
          backgroundColor: '#4caf5018',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.25,
          data: []
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: {
            type: 'time',
            time: {
              tooltipFormat: 'yyyy-MM-dd HH:mm',
              displayFormats: {
                second: 'HH:mm:ss',
                minute: 'HH:mm',
                hour: 'HH:mm',
                day: 'MMM d',
                week: 'MMM d',
                month: 'MMM yyyy',
                quarter: 'MMM yyyy',
                year: 'yyyy'
              }
            },
            grid: { color: gridColor },
            ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } }
          },
          y: {
            grid: { color: gridColor },
            ticks: { color: tickColor, font: { size: 10 } }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.parsed.y != null ? ctx.parsed.y.toLocaleString() : '';
              }
            }
          }
        }
      }
    });
    return balanceChart;
  }

  function historyDaysKey() {
    return historyDays != null && historyDays > 0 ? String(historyDays) : 'all';
  }

  function ensureHistorySeries() {
    var k = historyDaysKey();
    if (historySeriesCache[k]) {
      return Promise.resolve(historySeriesCache[k]);
    }
    if (historySeriesInflight[k]) {
      return historySeriesInflight[k];
    }
    var q = historyDays != null && historyDays > 0 ? 'days=' + historyDays : '';
    historySeriesInflight[k] = autolab.fetchJSON('/api/balance_history_batch?' + q)
      .then(function (data) {
        historySeriesCache[k] = data.series || {};
        delete historySeriesInflight[k];
        return historySeriesCache[k];
      })
      .catch(function (err) {
        delete historySeriesInflight[k];
        throw err;
      });
    return historySeriesInflight[k];
  }

  function applyHistoryChart(channel, bettor, points) {
    points = points || [];
    if (!points.length) {
      if (balanceChart) {
        balanceChart.data.datasets[0].data = [];
        balanceChart.update();
      }
      chartWrap.style.display = 'none';
      chartTitle.textContent = channel + ' - ' + bettor;
      chartEmpty.style.display = 'block';
      document.getElementById('chart-controls').style.display = 'flex';
      chartPanel.style.display = 'block';
      return;
    }
    chartEmpty.style.display = 'none';
    chartWrap.style.display = 'block';
    var controls = autolab.id('chart-controls'); if (controls) controls.style.display = 'flex';

    var chart = ensureChart();
    chart.data.datasets[0].data = points
      .filter(function (p) { return p.balance != null; })
      .map(function (p) { return { x: new Date(p.updated_at), y: p.balance }; });
    chart.update();

    chartTitle.textContent = channel + ' - ' + bettor;
    if (chartPanel) chartPanel.style.display = 'block';
  }

  function loadHistory(channel, bettor) {
    selectedChannel = channel;
    selectedBettor = bettor;
    ensureHistorySeries()
      .then(function (series) {
        var row = series[channel];
        var points = row && row[bettor] ? row[bettor] : [];
        applyHistoryChart(channel, bettor, points);
      })
      .catch(function () {});
  }

  function attachCellClickHandlers() {
    autolab.qsa('td.balance[data-channel][data-bettor]').forEach(function (td) {
      if (td.getAttribute('data-bound') === '1') return;
      td.setAttribute('data-bound', '1');
      autolab.on(td, 'click', function () {
        if (selectedCell) selectedCell.classList.remove('selected');
        td.classList.add('selected');
        selectedCell = td;
        loadHistory(td.getAttribute('data-channel'), td.getAttribute('data-bettor'));
      });
    });
  }

  autolab.fetchJSON('/api/balances')
    .then(function (data) {
      data.rows.forEach(function (row) {
        row.cells.forEach(function (cell) {
          var td = document.querySelector(
            'td[data-channel="' + row.channel + '"][data-bettor="' + cell.bettor + '"]'
          );
          if (td) {
            var oldText = td.textContent.trim();
            var oldVal = parseInt(oldText.replace(/[^0-9\-]/g, ''), 10);
            var newVal = cell.balance;
            var content = String(newVal);
            td.classList.remove('delta-positive', 'delta-negative');
            if (!isNaN(oldVal) && typeof newVal === 'number') {
              var delta = newVal - oldVal;
              if (delta > 0) {
                content = newVal + ' (+' + delta + ')';
                td.classList.add('delta-positive');
              } else if (delta < 0) {
                content = newVal + ' (' + delta + ')';
                td.classList.add('delta-negative');
              }
            }
            td.textContent = content;
          }
        });
      });
      autolab.setText('status', 'Updated with live data.');
      attachCellClickHandlers();
    })
    .catch(function () { autolab.setText('status', 'Update failed.'); });

  autolab.qsa('#chart-controls .range-btn').forEach(function (btn) {
    autolab.on(btn, 'click', function () {
      autolab.qsa('#chart-controls .range-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var d = btn.getAttribute('data-days');
      historyDays = d ? parseInt(d, 10) : null;
      if (selectedChannel && selectedBettor) {
        loadHistory(selectedChannel, selectedBettor);
      }
    });
  });

  attachCellClickHandlers();

  ensureHistorySeries().catch(function () {});
})();
