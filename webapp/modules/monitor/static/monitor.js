(function () {
  'use strict';

  /* ================================================================
   * Configuration
   * ================================================================ */
  var HISTORY_MAX_POINTS = 4000;
  var DELTA_MAX_POINTS = 500;
  var RENDER_MAX_POINTS_RECENT = 2000;
  var RENDER_MAX_POINTS_LONG = 1000;
  var LINE_GAP_MS = 45 * 60 * 1000;
  var STALE_TAB_MS = 5 * 60 * 1000;

  var POLL_ACTIVE_MS = 10000;
  var POLL_IDLE_MS = 30000;
  var POLL_DEEP_IDLE_MS = 60000;

  /* ================================================================
   * State
   * ================================================================ */
  var currentMinutes = (function () {
    var btn = document.querySelector('.range-btn.active[data-minutes]');
    var m = btn ? parseInt(btn.getAttribute('data-minutes'), 10) : 10080;
    return (isNaN(m) || m <= 0) ? 10080 : m;
  })();

  var currentDevice = '';
  try { currentDevice = localStorage.getItem('autolab_hw_device') || ''; } catch (e) {}

  var HISTORY_FETCH_MINUTES = (function () {
    var max = 0;
    document.querySelectorAll('.range-btn[data-minutes]').forEach(function (b) {
      var n = parseInt(b.getAttribute('data-minutes'), 10);
      if (!isNaN(n) && n > max) max = n;
    });
    return max || 10080;
  })();

  var cachedMetrics = null;
  var cachedLatest = null;
  var emptyPollCount = 0;
  var pollTimer = null;
  var pollingEnabled = false;
  var pollGeneration = 0;
  var historyInFlight = false;
  var deltaInFlight = false;
  var hiddenSince = null;
  var lastDeltaSince = '';
  var lastDeltaSentAt = 0;

  /* ================================================================
   * DOM refs
   * ================================================================ */
  var elStatus = document.getElementById('status');
  var elDevice = document.getElementById('device-select');
  var elFetchNowBtn = document.getElementById('fetch-now-btn');
  var elMergeToggle = document.getElementById('device-merge-toggle');
  var elMergePopover = document.getElementById('device-merge-popover');
  var elMergeTarget = document.getElementById('device-merge-target');
  var elMergeBtn = document.getElementById('device-merge-btn');
  var elMergeCancel = document.getElementById('device-merge-cancel');
  var elDeviceNameList = document.getElementById('device-name-list');

  /* ================================================================
   * Chart setup
   * ================================================================ */
  var gridColor = 'rgba(255,255,255,0.06)';
  var tickColor = '#888';

  function mhzToGhz(m) { return m != null ? m / 1000 : null; }
  function pctFmt(y) { return y.toFixed(1) + '%'; }
  function ghzFmt(y) { return y.toFixed(3) + ' GHz'; }
  function degFmt(y) { return y.toFixed(1) + '\u00b0C'; }

  function chartOptsSingle(unit) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { intersect: false, mode: 'index' },
      scales: {
        x: {
          type: 'time',
          time: {
            tooltipFormat: 'HH:mm:ss',
            displayFormats: { second: 'HH:mm:ss', minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
          },
          grid: { color: gridColor },
          ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } }
        },
        y: {
          suggestedMin: 0,
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { size: 10 } }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return ctx.parsed.y != null ? ctx.parsed.y.toFixed(1) + unit : '';
            }
          }
        }
      }
    };
  }

  function chartOptsDual(fmt) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { intersect: false, mode: 'index' },
      scales: {
        x: {
          type: 'time',
          time: {
            tooltipFormat: 'HH:mm:ss',
            displayFormats: { second: 'HH:mm:ss', minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' }
          },
          grid: { color: gridColor },
          ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } }
        },
        y: {
          suggestedMin: 0,
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { size: 10 } }
        }
      },
      plugins: {
        legend: { display: true, labels: { color: '#888', font: { size: 10 }, boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var y = ctx.parsed.y;
              if (y == null) return ctx.dataset.label + ': \u2014';
              return ctx.dataset.label + ': ' + fmt(y);
            }
          }
        }
      }
    };
  }

  function dsLine(label, color) {
    return {
      label: label,
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 1.5,
      pointRadius: 0,
      fill: true,
      tension: 0.25,
      data: []
    };
  }

  function makeDualChart(id, c1, c2, lab1, lab2, fmt) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: { datasets: [dsLine(lab1, c1), dsLine(lab2, c2)] },
      options: chartOptsDual(fmt)
    });
  }

  function makeChart(id, color, unit) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: { datasets: [dsLine('', color)] },
      options: chartOptsSingle(unit)
    });
  }

  function makePcieChart(id) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: { datasets: [dsLine('TX (host\u2192GPU)', '#43a047'), dsLine('RX (GPU\u2192host)', '#e53935')] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: {
            type: 'time',
            time: { tooltipFormat: 'HH:mm:ss', displayFormats: { minute: 'HH:mm', hour: 'HH:mm', day: 'MMM d' } },
            grid: { color: gridColor },
            ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } }
          },
          y: {
            suggestedMin: 0,
            grid: { color: gridColor },
            ticks: { color: tickColor, font: { size: 10 } }
          }
        },
        plugins: {
          legend: { display: true, labels: { color: '#888', font: { size: 10 } } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var v = ctx.parsed.y;
                return ctx.dataset.label + ': ' + (v != null ? v.toFixed(2) + ' MB/s' : '');
              }
            }
          }
        }
      }
    });
  }

  var chartLoad = makeDualChart('chart-load', '#42a5f5', '#43a047', 'CPU', 'GPU', pctFmt);
  var chartClock = makeDualChart('chart-clock', '#42a5f5', '#43a047', 'CPU', 'GPU', ghzFmt);
  var chartTemp = makeDualChart('chart-temp', '#42a5f5', '#43a047', 'CPU', 'GPU', degFmt);
  var chartRamSwap = makeDualChart('chart-ram-swap', '#43a047', '#e53935', 'RAM', 'Swap', pctFmt);
  var chartGmem = makeChart('chart-gpu-mem', '#43a047', '%');
  var chartPcie = makePcieChart('chart-pcie');

  /* ================================================================
   * Chart toggle sidebar
   * ================================================================ */
  function loadToggles() {
    try { var r = localStorage.getItem('autolab_hw_chart_toggles'); if (r) return JSON.parse(r); } catch (e) {}
    return null;
  }

  function saveToggles(obj) {
    try { localStorage.setItem('autolab_hw_chart_toggles', JSON.stringify(obj)); } catch (e) {}
  }

  function applyChartVisibility() {
    var t = loadToggles();
    document.querySelectorAll('[data-chart-panel]').forEach(function (panel) {
      var key = panel.getAttribute('data-chart-panel');
      var on = t && Object.prototype.hasOwnProperty.call(t, key) ? t[key] : true;
      panel.style.display = on ? '' : 'none';
    });
    document.querySelectorAll('.sidebar input[data-chart]').forEach(function (inp) {
      var key = inp.getAttribute('data-chart');
      if (t && Object.prototype.hasOwnProperty.call(t, key)) inp.checked = t[key];
    });
  }

  document.querySelectorAll('.sidebar input[data-chart]').forEach(function (inp) {
    inp.addEventListener('change', function () {
      var o = loadToggles() || {};
      o[inp.getAttribute('data-chart')] = inp.checked;
      saveToggles(o);
      applyChartVisibility();
    });
  });
  applyChartVisibility();

  /* ================================================================
   * Data series building
   * ================================================================ */
  function buildSeriesWithGaps(metrics, key, mapY) {
    mapY = mapY || function (y) { return y; };
    var out = [];
    var prevTs = null;
    for (var i = 0; i < metrics.length; i++) {
      var m = metrics[i];
      if (!m || m[key] == null || !m.timestamp) continue;
      var ts = new Date(m.timestamp);
      if (isNaN(ts.getTime())) continue;
      if (prevTs != null && (ts.getTime() - prevTs) > LINE_GAP_MS) {
        out.push({ x: ts, y: null });
      }
      out.push({ x: ts, y: mapY(m[key]) });
      prevTs = ts.getTime();
    }
    return out;
  }

  function filterMetricsForWindow(metrics, minutes) {
    if (!metrics || !metrics.length) return [];
    var cutoff = Date.now() - minutes * 60 * 1000;
    return metrics.filter(function (m) {
      if (!m || !m.timestamp) return false;
      var t = new Date(m.timestamp).getTime();
      return !isNaN(t) && t >= cutoff;
    });
  }

  function thinMetricsForRender(metrics, maxPoints) {
    if (!metrics || metrics.length <= maxPoints || maxPoints <= 0) return metrics || [];
    var stride = Math.ceil(metrics.length / maxPoints);
    var out = [];
    for (var i = 0; i < metrics.length; i += stride) out.push(metrics[i]);
    var last = metrics[metrics.length - 1];
    if (out.length && last && out[out.length - 1] !== last) out.push(last);
    if (out.length > maxPoints) out = out.slice(out.length - maxPoints);
    return out;
  }

  function renderPointBudget(minutes) {
    return minutes >= 1440 ? RENDER_MAX_POINTS_LONG : RENDER_MAX_POINTS_RECENT;
  }

  function panelVisible(key) {
    var panel = document.querySelector('[data-chart-panel="' + key + '"]');
    return !!(panel && panel.style.display !== 'none');
  }

  /* ================================================================
   * Vendor colors (sets dataset colors, no chart.update calls)
   * ================================================================ */
  function cpuLineColor(v) {
    if (v === 'intel') return '#42a5f5';
    if (v === 'amd') return '#e53935';
    return '#90a4ae';
  }

  function gpuLineColor(v) {
    if (v === 'nvidia') return '#43a047';
    if (v === 'amd') return '#e53935';
    return '#ec407a';
  }

  function applyVendorColors(latest) {
    var absent = '#757575';
    var cv = (latest && latest.cpu_vendor) || 'unknown';
    var gv = (latest && latest.gpu_vendor) || 'unknown';
    var cc = cpuLineColor(cv);
    var gc = gpuLineColor(gv);

    function ok(f) { return latest != null && latest[f] != null; }
    function paint(chart, i, color) {
      chart.data.datasets[i].borderColor = color;
      chart.data.datasets[i].backgroundColor = color + '18';
    }

    paint(chartLoad, 0, ok('cpu_load') ? cc : absent);
    paint(chartLoad, 1, ok('gpu_util') ? gc : absent);
    paint(chartClock, 0, ok('cpu_clock') ? cc : absent);
    paint(chartClock, 1, ok('gpu_clock') ? gc : absent);
    paint(chartTemp, 0, ok('cpu_temp') ? cc : absent);
    paint(chartTemp, 1, ok('gpu_temp') ? gc : absent);
    paint(chartRamSwap, 0, '#43a047');
    paint(chartRamSwap, 1, '#e53935');
    paint(chartGmem, 0, ok('gpu_mem_percent') ? gc : absent);

    function setElColor(id, color) {
      var el = document.getElementById(id);
      if (el) el.style.color = color;
    }
    setElColor('cur-load-cpu', ok('cpu_load') ? cc : absent);
    setElColor('cur-load-gpu', ok('gpu_util') ? gc : absent);
    setElColor('cur-clock-cpu', ok('cpu_clock') ? cc : absent);
    setElColor('cur-clock-gpu', ok('gpu_clock') ? gc : absent);
    setElColor('cur-temp-cpu', ok('cpu_temp') ? cc : absent);
    setElColor('cur-temp-gpu', ok('gpu_temp') ? gc : absent);
    setElColor('cur-ram', '#43a047');
    setElColor('cur-swap', '#e53935');
    setElColor('cur-gmem', ok('gpu_mem_percent') ? gc : absent);
    setElColor('cur-pcie-tx', '#43a047');
    setElColor('cur-pcie-rx', '#e53935');
  }

  /* ================================================================
   * Batched chart rendering — one rAF for everything
   * ================================================================ */
  var renderQueued = false;

  function scheduleRender() {
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(render);
  }

  function render() {
    renderQueued = false;
    if (!cachedMetrics) return;

    var windowed = filterMetricsForWindow(cachedMetrics, currentMinutes);
    var m = thinMetricsForRender(windowed, renderPointBudget(currentMinutes));

    applyVendorColors(cachedLatest);
    var toUpdate = [];

    if (panelVisible('load')) {
      chartLoad.data.datasets[0].data = buildSeriesWithGaps(m, 'cpu_load');
      chartLoad.data.datasets[1].data = buildSeriesWithGaps(m, 'gpu_util');
      toUpdate.push(chartLoad);
    }
    if (panelVisible('clock')) {
      chartClock.data.datasets[0].data = buildSeriesWithGaps(m, 'cpu_clock', mhzToGhz);
      chartClock.data.datasets[1].data = buildSeriesWithGaps(m, 'gpu_clock', mhzToGhz);
      toUpdate.push(chartClock);
    }
    if (panelVisible('temp')) {
      chartTemp.data.datasets[0].data = buildSeriesWithGaps(m, 'cpu_temp');
      chartTemp.data.datasets[1].data = buildSeriesWithGaps(m, 'gpu_temp');
      toUpdate.push(chartTemp);
    }
    if (panelVisible('ram_swap')) {
      chartRamSwap.data.datasets[0].data = buildSeriesWithGaps(m, 'ram_percent');
      chartRamSwap.data.datasets[1].data = buildSeriesWithGaps(m, 'swap_percent');
      toUpdate.push(chartRamSwap);
    }
    if (panelVisible('gpu_mem')) {
      chartGmem.data.datasets[0].data = buildSeriesWithGaps(m, 'gpu_mem_percent');
      toUpdate.push(chartGmem);
    }
    if (panelVisible('pcie')) {
      chartPcie.data.datasets[0].data = buildSeriesWithGaps(m, 'pcie_tx_mbps');
      chartPcie.data.datasets[1].data = buildSeriesWithGaps(m, 'pcie_rx_mbps');
      toUpdate.push(chartPcie);
    }

    toUpdate.forEach(function (c) { c.update('none'); });

    renderLatest(cachedLatest);
  }

  /* ================================================================
   * Latest readings display
   * ================================================================ */
  function renderLatest(latest) {
    var elGpuBanner = document.getElementById('gpu-status');
    if (latest) {
      function setPair(cpuId, gpuId, a, b, af, bf) {
        document.getElementById(cpuId).textContent = a != null ? af(a) : '\u2014';
        document.getElementById(gpuId).textContent = b != null ? bf(b) : '\u2014';
      }
      setPair('cur-load-cpu', 'cur-load-gpu', latest.cpu_load, latest.gpu_util,
        function (x) { return x.toFixed(1) + '%'; },
        function (x) { return x.toFixed(0) + '%'; });
      setPair('cur-clock-cpu', 'cur-clock-gpu', latest.cpu_clock, latest.gpu_clock,
        function (x) { return mhzToGhz(x).toFixed(3) + ' GHz'; },
        function (x) { return mhzToGhz(x).toFixed(3) + ' GHz'; });
      setPair('cur-temp-cpu', 'cur-temp-gpu', latest.cpu_temp, latest.gpu_temp,
        function (x) { return x.toFixed(1) + '\u00b0C'; },
        function (x) { return x.toFixed(1) + '\u00b0C'; });
      document.getElementById('cur-ram').textContent =
        latest.ram_percent != null ? latest.ram_percent.toFixed(1) + '%' : '\u2014';
      document.getElementById('cur-swap').textContent =
        latest.swap_percent != null ? latest.swap_percent.toFixed(1) + '%' : '\u2014';
      document.getElementById('cur-gmem').textContent =
        latest.gpu_mem_percent != null ? latest.gpu_mem_percent.toFixed(1) + '%' : '\u2014';
      document.getElementById('cur-pcie-tx').textContent =
        latest.pcie_tx_mbps != null ? latest.pcie_tx_mbps.toFixed(2) + ' MB/s' : '\u2014';
      document.getElementById('cur-pcie-rx').textContent =
        latest.pcie_rx_mbps != null ? latest.pcie_rx_mbps.toFixed(2) + ' MB/s' : '\u2014';

      var gpuLive = latest.gpu_util != null || latest.gpu_temp != null || latest.gpu_clock != null;
      elGpuBanner.className = 'gpu-banner ' + (gpuLive ? 'ok' : 'warn');
      elGpuBanner.textContent = gpuLive
        ? 'GPU: sensors active (NVIDIA data in this sample).'
        : 'GPU: no NVIDIA metrics in latest sample.';
    } else {
      elGpuBanner.className = 'gpu-banner warn';
      elGpuBanner.textContent = 'GPU: no data yet for this device.';
    }
  }

  /* ================================================================
   * Loading shimmer
   * ================================================================ */
  function setChartsLoading(on) {
    document.querySelectorAll('.chart-wrap').forEach(function (w) {
      w.classList.toggle('chart-loading', !!on);
    });
  }

  /* ================================================================
   * Status line — shows age of most recent datapoint
   * ================================================================ */
  function dataAge() {
    if (!cachedLatest || !cachedLatest.timestamp) return '';
    var ms = Date.now() - new Date(cachedLatest.timestamp).getTime();
    if (isNaN(ms) || ms < 0) return '';
    if (ms < 60000) return Math.round(ms / 1000) + 's ago';
    if (ms < 3600000) return Math.round(ms / 60000) + 'm ago';
    if (ms < 86400000) return (ms / 3600000).toFixed(1) + 'h ago';
    return Math.round(ms / 86400000) + 'd ago';
  }

  function updateStatus(msg, isError) {
    var parts = [msg, new Date().toLocaleTimeString()];
    var age = dataAge();
    if (age) parts.push('last sample ' + age);
    elStatus.textContent = parts.join(' \u00b7 ');
    elStatus.style.color = isError ? '#e57373' : '';
  }

  /* ================================================================
   * Device management
   * ================================================================ */
  function isValidDeviceName(name) {
    return /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/.test(name);
  }

  function refreshDeviceSuggestions(devices) {
    if (!elDeviceNameList) return;
    elDeviceNameList.innerHTML = '';
    (devices || []).forEach(function (d) {
      if (!d) return;
      var opt = document.createElement('option');
      opt.value = d;
      elDeviceNameList.appendChild(opt);
    });
  }

  function mergeDeviceOptions(devices) {
    if (!devices || !devices.length) return;
    var seen = {};
    for (var i = 0; i < elDevice.options.length; i++) seen[elDevice.options[i].value] = true;
    devices.forEach(function (d) {
      if (d && !seen[d]) {
        var opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        elDevice.appendChild(opt);
        seen[d] = true;
      }
    });
    if (currentDevice && seen[currentDevice]) {
      elDevice.value = currentDevice;
    } else if (devices.length) {
      elDevice.value = devices[0];
      currentDevice = devices[0];
    }
    if (elMergeTarget && !elMergeTarget.value) {
      var t = devices.find(function (d) { return d !== currentDevice; }) || currentDevice;
      elMergeTarget.value = t || '';
    }
    refreshDeviceSuggestions(devices);
    try { localStorage.setItem('autolab_hw_device', currentDevice); } catch (e) {}
  }

  /* ================================================================
   * Cache management
   * ================================================================ */
  function latestCachedTimestamp() {
    if (cachedLatest && cachedLatest.timestamp) return cachedLatest.timestamp;
    if (cachedMetrics && cachedMetrics.length) {
      var last = cachedMetrics[cachedMetrics.length - 1];
      if (last && last.timestamp) return last.timestamp;
    }
    return '';
  }

  function appendMetricsToCache(metrics) {
    if (!metrics || !metrics.length) return;
    if (!cachedMetrics) cachedMetrics = [];
    for (var i = 0; i < metrics.length; i++) cachedMetrics.push(metrics[i]);
    var cutoff = Date.now() - HISTORY_FETCH_MINUTES * 60 * 1000;
    cachedMetrics = cachedMetrics.filter(function (m) {
      if (!m || !m.timestamp) return false;
      var t = new Date(m.timestamp).getTime();
      return !isNaN(t) && t >= cutoff;
    });
  }

  /* ================================================================
   * API: fetchHistory, fetchDelta, wakeNode
   * ================================================================ */
  function fetchHistory() {
    if (historyInFlight) return Promise.resolve();
    historyInFlight = true;
    var dev = elDevice.value || currentDevice || '';
    var url = '/api/monitor/history?minutes=' + HISTORY_FETCH_MINUTES
            + '&max_points=' + HISTORY_MAX_POINTS;
    if (dev) url += '&device=' + encodeURIComponent(dev);
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.devices) mergeDeviceOptions(data.devices);
        cachedMetrics = data.metrics || [];
        cachedLatest = data.latest;
        scheduleRender();
        updateStatus(cachedMetrics.length + ' points loaded');
      })
      .catch(function () { updateStatus('Failed to load data', true); })
      .finally(function () { historyInFlight = false; });
  }

  function fetchDelta() {
    if (deltaInFlight) return Promise.resolve();
    var dev = elDevice.value || currentDevice || '';
    var since = latestCachedTimestamp();
    if (!since) return fetchHistory();
    var nowMs = Date.now();
    if (since === lastDeltaSince && (nowMs - lastDeltaSentAt) < 1500) {
      return Promise.resolve();
    }
    deltaInFlight = true;
    lastDeltaSince = since;
    lastDeltaSentAt = nowMs;
    var url = '/api/monitor/history_delta?since=' + encodeURIComponent(since)
            + '&max_points=' + DELTA_MAX_POINTS;
    if (dev) url += '&device=' + encodeURIComponent(dev);
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var n = (data && data.metrics) ? data.metrics.length : 0;
        if (n > 0) {
          appendMetricsToCache(data.metrics);
          emptyPollCount = 0;
          updateStatus('+' + n + ' new');
        } else {
          emptyPollCount++;
        }
        if (data && data.latest) cachedLatest = data.latest;
        scheduleRender();
      })
      .catch(function () { emptyPollCount++; })
      .finally(function () { deltaInFlight = false; });
  }

  function wakeNode(opts) {
    opts = opts || {};
    var dev = elDevice.value || currentDevice || '';
    if (!dev) return Promise.resolve();
    if (!opts.quiet) {
      updateStatus('Requesting sample from node\u2026');
      if (elFetchNowBtn) elFetchNowBtn.disabled = true;
    }
    return fetch('/api/monitor/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device: dev })
    })
    .then(function (r) {
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    })
    .then(function (res) {
      if (res.status >= 400 || !res.body || !res.body.ok) {
        var msg = (res.body && res.body.error) || 'unavailable';
        if (!opts.quiet) updateStatus('Node: ' + msg, true);
        return false;
      }
      emptyPollCount = 0;
      if (!opts.quiet) updateStatus('Node responded');
      return true;
    })
    .catch(function () {
      if (!opts.quiet) updateStatus('Node unreachable', true);
      return false;
    })
    .finally(function () {
      if (!opts.quiet && elFetchNowBtn) elFetchNowBtn.disabled = false;
    });
  }

  /* ================================================================
   * Adaptive polling engine
   *
   * Intervals adapt to whether data is flowing:
   *   data arriving  → 10 s  (fast refresh)
   *   <5 empty polls → 30 s  (normal)
   *   5+ empty polls → 60 s  (save bandwidth)
   *
   * Polling pauses entirely when the tab is hidden (Page Visibility
   * API) and resumes when visible.  If the tab was hidden >5 min a
   * full history re-fetch fires instead of a delta.
   * ================================================================ */
  function nextPollMs() {
    if (emptyPollCount === 0) return POLL_ACTIVE_MS;
    if (emptyPollCount < 5) return POLL_IDLE_MS;
    return POLL_DEEP_IDLE_MS;
  }

  function startPolling() {
    stopPolling();
    pollingEnabled = true;
    pollGeneration++;
    pollTick(pollGeneration);
  }

  function scheduleNextPoll() {
    stopPolling();
    pollingEnabled = true;
    pollGeneration++;
    var gen = pollGeneration;
    pollTimer = setTimeout(function () { pollTick(gen); }, nextPollMs());
  }

  function stopPolling() {
    pollingEnabled = false;
    pollGeneration++;
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  function pollTick(gen) {
    if (!pollingEnabled || gen !== pollGeneration) return;
    fetchDelta().finally(function () {
      if (!pollingEnabled || gen !== pollGeneration) return;
      pollTimer = setTimeout(function () { pollTick(gen); }, nextPollMs());
    });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      hiddenSince = Date.now();
      stopPolling();
    } else {
      var stale = hiddenSince && (Date.now() - hiddenSince) > STALE_TAB_MS;
      hiddenSince = null;
      if (stale) {
        setChartsLoading(true);
        emptyPollCount = 0;
        fetchHistory().finally(function () {
          setChartsLoading(false);
          wakeNode({ quiet: true });
          scheduleNextPoll();
        });
      } else {
        wakeNode({ quiet: true });
        startPolling();
      }
    }
  });

  /* ================================================================
   * Merge popover
   * ================================================================ */
  function isMergeOpen() { return !!(elMergePopover && !elMergePopover.hidden); }

  function openMerge() {
    if (!elMergePopover) return;
    elMergePopover.hidden = false;
    if (elMergeTarget) {
      if (!elMergeTarget.value || elMergeTarget.value === currentDevice) elMergeTarget.value = '';
      elMergeTarget.focus();
      elMergeTarget.select();
    }
  }

  function closeMerge() { if (elMergePopover) elMergePopover.hidden = true; }

  if (elMergeToggle) elMergeToggle.addEventListener('click', function (e) {
    e.stopPropagation();
    isMergeOpen() ? closeMerge() : openMerge();
  });

  if (elMergeCancel) elMergeCancel.addEventListener('click', closeMerge);

  document.addEventListener('click', function (e) {
    if (!isMergeOpen()) return;
    var root = elMergePopover && elMergePopover.parentElement;
    if (root && !root.contains(e.target)) closeMerge();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isMergeOpen()) closeMerge();
  });

  if (elMergeBtn) elMergeBtn.addEventListener('click', function () {
    var source = (elDevice.value || '').trim();
    var target = (elMergeTarget && elMergeTarget.value ? elMergeTarget.value : '').trim();
    if (!source) { alert('Pick a source device first.'); return; }
    if (!target) { alert('Enter a target device name.'); return; }
    if (!isValidDeviceName(target)) {
      alert('Invalid name. Use 1\u201364 chars: letters, digits, dot, underscore, hyphen.');
      return;
    }
    if (source === target) { alert('Source and target are the same.'); return; }
    if (!confirm('Move all samples from \u201c' + source + '\u201d to \u201c' + target + '\u201d?\n\nCannot be undone.')) return;

    elMergeBtn.disabled = true;
    updateStatus('Moving data\u2026');
    fetch('/api/monitor/device/reassign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: source, target: target })
    })
    .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
    .then(function (res) {
      if (res.status >= 400 || !res.body || !res.body.ok) {
        throw new Error((res.body && res.body.error) || 'failed');
      }
      currentDevice = target;
      elDevice.value = currentDevice;
      if (elMergeTarget) elMergeTarget.value = '';
      if (res.body.devices) mergeDeviceOptions(res.body.devices);
      fetchHistory();
      updateStatus('Moved ' + res.body.moved + ' sample(s) to ' + target);
      closeMerge();
    })
    .catch(function (err) {
      updateStatus('Move failed: ' + (err.message || 'unknown'), true);
    })
    .finally(function () { elMergeBtn.disabled = false; });
  });

  /* ================================================================
   * Event: device change
   * ================================================================ */
  elDevice.addEventListener('change', function () {
    currentDevice = elDevice.value;
    if (elMergeTarget && elMergeTarget.value === currentDevice) elMergeTarget.value = '';
    try { localStorage.setItem('autolab_hw_device', currentDevice); } catch (e) {}
    cachedMetrics = null;
    cachedLatest = null;
    emptyPollCount = 0;
    deltaInFlight = false;
    lastDeltaSince = '';
    lastDeltaSentAt = 0;
    stopPolling();
    setChartsLoading(true);
    fetchHistory().finally(function () {
      setChartsLoading(false);
      wakeNode({ quiet: true });
      scheduleNextPoll();
    });
  });

  /* ================================================================
   * Event: fetch-now button
   * ================================================================ */
  if (elFetchNowBtn) elFetchNowBtn.addEventListener('click', function () {
    wakeNode({ quiet: false }).then(function (ok) {
      if (ok) setTimeout(function () { fetchDelta(); }, 2000);
    });
  });

  /* ================================================================
   * Event: range buttons (pure client-side — no network request)
   * ================================================================ */
  document.querySelectorAll('.range-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.range-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentMinutes = parseInt(btn.getAttribute('data-minutes'), 10);
      scheduleRender();
    });
  });

  /* ================================================================
   * Bootstrap — single history fetch, then fire-and-forget wake
   * ================================================================ */
  setChartsLoading(true);
  updateStatus('Loading\u2026');
  fetchHistory().finally(function () {
    setChartsLoading(false);
    wakeNode({ quiet: true });
    scheduleNextPoll();
  });

})();
