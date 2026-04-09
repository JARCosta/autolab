(function () {
  var currentMinutes = 10080;
  var currentDevice = '';
  try { currentDevice = localStorage.getItem('autolab_hw_device') || ''; } catch (e) {}

  /** Largest range in the UI; history is always fetched for this span and sliced in JS for range buttons (no extra request per click). */
  var HISTORY_FETCH_MINUTES = (function () {
    var max = 0;
    document.querySelectorAll('.range-btn[data-minutes]').forEach(function (b) {
      var n = parseInt(b.getAttribute('data-minutes'), 10);
      if (!isNaN(n) && n > max) max = n;
    });
    return max || 10080;
  })();
  /** Server allows up to 20k; larger cap keeps short windows usable when the cache is a long range (downsampled). */
  var HISTORY_MAX_POINTS = 20000;

  var cachedMetrics = null;
  var cachedLatest = null;

  var gridColor = 'rgba(255,255,255,0.06)';
  var tickColor = '#888';
  var lineGapBreakMs = 5 * 60 * 1000;

  function mhzToGhz(m) {
    return m != null ? m / 1000 : null;
  }

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

  function makeDualChart(id, c1, c2, lab1, lab2, fmt) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: {
        datasets: [
          {
            label: lab1,
            borderColor: c1,
            backgroundColor: c1 + '18',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: true,
            tension: 0.25,
            data: []
          },
          {
            label: lab2,
            borderColor: c2,
            backgroundColor: c2 + '18',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: true,
            tension: 0.25,
            data: []
          }
        ]
      },
      options: chartOptsDual(fmt)
    });
  }

  function makeChart(id, color, unit) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: {
        datasets: [{
          borderColor: color,
          backgroundColor: color + '18',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.25,
          data: []
        }]
      },
      options: chartOptsSingle(unit)
    });
  }

  function makePcieChart(id) {
    return new Chart(document.getElementById(id), {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'TX (host->GPU)',
            borderColor: '#43a047',
            backgroundColor: '#43a04712',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: true,
            tension: 0.25,
            data: []
          },
          {
            label: 'RX (GPU->host)',
            borderColor: '#e53935',
            backgroundColor: '#e5393512',
            borderWidth: 1.5,
            pointRadius: 0,
            fill: true,
            tension: 0.25,
            data: []
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
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

  function pctFmt(y) { return y.toFixed(1) + '%'; }
  function ghzFmt(y) { return y.toFixed(3) + ' GHz'; }
  function degFmt(y) { return y.toFixed(1) + ' C'; }

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

    function ok(field) {
      return latest != null && latest[field] != null;
    }
    function paintSeries(chart, i, color) {
      chart.data.datasets[i].borderColor = color;
      chart.data.datasets[i].backgroundColor = color + '18';
    }

    paintSeries(chartLoad, 0, ok('cpu_load') ? cc : absent);
    paintSeries(chartLoad, 1, ok('gpu_util') ? gc : absent);
    chartLoad.update('none');

    paintSeries(chartClock, 0, ok('cpu_clock') ? cc : absent);
    paintSeries(chartClock, 1, ok('gpu_clock') ? gc : absent);
    chartClock.update('none');

    paintSeries(chartTemp, 0, ok('cpu_temp') ? cc : absent);
    paintSeries(chartTemp, 1, ok('gpu_temp') ? gc : absent);
    chartTemp.update('none');

    var ramGreen = '#43a047';
    var swapRed = '#e53935';
    chartRamSwap.data.datasets[0].borderColor = ramGreen;
    chartRamSwap.data.datasets[0].backgroundColor = ramGreen + '18';
    chartRamSwap.data.datasets[1].borderColor = swapRed;
    chartRamSwap.data.datasets[1].backgroundColor = swapRed + '18';
    chartRamSwap.update('none');

    var gmemColor = ok('gpu_mem_percent') ? gc : absent;
    chartGmem.data.datasets[0].borderColor = gmemColor;
    chartGmem.data.datasets[0].backgroundColor = gmemColor + '18';
    chartGmem.update('none');

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

  var chartLoad = makeDualChart('chart-load', '#42a5f5', '#43a047', 'CPU', 'GPU', pctFmt);
  var chartClock = makeDualChart('chart-clock', '#42a5f5', '#43a047', 'CPU', 'GPU', ghzFmt);
  var chartTemp = makeDualChart('chart-temp', '#42a5f5', '#43a047', 'CPU', 'GPU', degFmt);
  var chartRamSwap = makeDualChart('chart-ram-swap', '#43a047', '#e53935', 'RAM', 'Swap', pctFmt);
  var chartGmem = makeChart('chart-gpu-mem', '#43a047', '%');
  var chartPcie = makePcieChart('chart-pcie');

  function buildSeriesWithGaps(metrics, key, mapY) {
    mapY = mapY || function (y) { return y; };
    var out = [];
    var prevTs = null;
    metrics.forEach(function (m) {
      if (!m || m[key] == null || !m.timestamp) return;
      var ts = new Date(m.timestamp);
      if (isNaN(ts.getTime())) return;
      if (prevTs != null && (ts.getTime() - prevTs) > lineGapBreakMs) {
        out.push({ x: ts, y: null });
      }
      out.push({ x: ts, y: mapY(m[key]) });
      prevTs = ts.getTime();
    });
    return out;
  }

  function setData(chart, metrics, key) {
    chart.data.datasets[0].data = buildSeriesWithGaps(metrics, key);
    chart.update();
  }

  function setDualData(chart, metrics, key1, key2, mapY1, mapY2) {
    mapY1 = mapY1 || function (y) { return y; };
    mapY2 = mapY2 || function (y) { return y; };
    chart.data.datasets[0].data = buildSeriesWithGaps(metrics, key1, mapY1);
    chart.data.datasets[1].data = buildSeriesWithGaps(metrics, key2, mapY2);
    chart.update();
  }

  function setPcieData(metrics) {
    chartPcie.data.datasets[0].data = buildSeriesWithGaps(metrics, 'pcie_tx_mbps');
    chartPcie.data.datasets[1].data = buildSeriesWithGaps(metrics, 'pcie_rx_mbps');
    chartPcie.update();
  }

  function loadToggles() {
    try {
      var raw = localStorage.getItem('autolab_hw_chart_toggles');
      if (raw) return JSON.parse(raw);
    } catch (e) {}
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

  var elStatus = document.getElementById('status');
  var elDevice = document.getElementById('device-select');
  var elMergeToggle = document.getElementById('device-merge-toggle');
  var elMergePopover = document.getElementById('device-merge-popover');
  var elMergeTarget = document.getElementById('device-merge-target');
  var elMergeBtn = document.getElementById('device-merge-btn');
  var elMergeCancel = document.getElementById('device-merge-cancel');
  var elDeviceNameList = document.getElementById('device-name-list');
  var elFetchNowBtn = document.getElementById('fetch-now-btn');

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

  function isMergePopoverOpen() {
    return !!(elMergePopover && !elMergePopover.hidden);
  }

  function openMergePopover() {
    if (!elMergePopover) return;
    elMergePopover.hidden = false;
    if (elMergeTarget) {
      if (!elMergeTarget.value || elMergeTarget.value === currentDevice) {
        elMergeTarget.value = '';
      }
      elMergeTarget.focus();
      elMergeTarget.select();
    }
  }

  function closeMergePopover() {
    if (!elMergePopover) return;
    elMergePopover.hidden = true;
  }

  function mergeDeviceOptions(devices) {
    if (!devices || !devices.length) return;
    var seen = {};
    for (var i = 0; i < elDevice.options.length; i++) {
      seen[elDevice.options[i].value] = true;
    }
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
      var initialTarget = devices.find(function (d) { return d !== currentDevice; }) || currentDevice;
      elMergeTarget.value = initialTarget || '';
    }
    refreshDeviceSuggestions(devices);
    try { localStorage.setItem('autolab_hw_device', currentDevice); } catch (e) {}
  }

  function renderLatest(latest) {
    var elGpuBanner = document.getElementById('gpu-status');
    if (latest) {
      function setPair(cpuId, gpuId, a, b, af, bf) {
        document.getElementById(cpuId).textContent = a != null ? af(a) : '\u2014';
        document.getElementById(gpuId).textContent = b != null ? bf(b) : '\u2014';
      }
      setPair(
        'cur-load-cpu', 'cur-load-gpu',
        latest.cpu_load, latest.gpu_util,
        function (x) { return x.toFixed(1) + '%'; },
        function (x) { return x.toFixed(0) + '%'; }
      );
      setPair(
        'cur-clock-cpu', 'cur-clock-gpu',
        latest.cpu_clock, latest.gpu_clock,
        function (x) { return mhzToGhz(x).toFixed(3) + ' GHz'; },
        function (x) { return mhzToGhz(x).toFixed(3) + ' GHz'; }
      );
      setPair(
        'cur-temp-cpu', 'cur-temp-gpu',
        latest.cpu_temp, latest.gpu_temp,
        function (x) { return x.toFixed(1) + 'C'; },
        function (x) { return x.toFixed(1) + 'C'; }
      );
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

      applyVendorColors(latest);

      var gpuLive = latest.gpu_util != null || latest.gpu_temp != null || latest.gpu_clock != null;
      elGpuBanner.className = 'gpu-banner ' + (gpuLive ? 'ok' : 'warn');
      elGpuBanner.textContent = gpuLive
        ? 'GPU: sensors active (NVIDIA data in this sample).'
        : 'GPU: no NVIDIA metrics in latest sample (install drivers / nvidia-smi on the host that pushes metrics).';
    } else {
      applyVendorColors(null);
      elGpuBanner.className = 'gpu-banner warn';
      elGpuBanner.textContent = 'GPU: no data yet for this device.';
    }
  }

  function trimDatasetToWindow(dataset, minTs) {
    dataset.data = dataset.data.filter(function (p) {
      var t = (p && p.x instanceof Date) ? p.x.getTime() : new Date(p.x).getTime();
      return !isNaN(t) && t >= minTs;
    });
  }

  function appendLatestPoint(latest) {
    if (!latest || !latest.timestamp) return;
    var ts = new Date(latest.timestamp);
    if (isNaN(ts.getTime())) return;
    var minTs = Date.now() - (currentMinutes * 60 * 1000);

    function push(chart, idx, v, mapY) {
      if (v == null) return;
      var dataset = chart.data.datasets[idx];
      var points = dataset.data || [];
      if (points.length) {
        var last = points[points.length - 1];
        var lastTs = (last && last.x instanceof Date) ? last.x.getTime() : new Date(last && last.x).getTime();
        if (!isNaN(lastTs) && (ts.getTime() - lastTs) > lineGapBreakMs) {
          points.push({ x: ts, y: null });
        }
      }
      points.push({ x: ts, y: mapY ? mapY(v) : v });
      dataset.data = points;
      trimDatasetToWindow(dataset, minTs);
      chart.update('none');
    }

    push(chartLoad, 0, latest.cpu_load);
    push(chartLoad, 1, latest.gpu_util);
    push(chartClock, 0, latest.cpu_clock, mhzToGhz);
    push(chartClock, 1, latest.gpu_clock, mhzToGhz);
    push(chartTemp, 0, latest.cpu_temp);
    push(chartTemp, 1, latest.gpu_temp);
    push(chartRamSwap, 0, latest.ram_percent);
    push(chartRamSwap, 1, latest.swap_percent);
    push(chartGmem, 0, latest.gpu_mem_percent);
    push(chartPcie, 0, latest.pcie_tx_mbps);
    push(chartPcie, 1, latest.pcie_rx_mbps);
  }

  var historyFetchGen = 0;

  function setChartsLoading(loading) {
    document.querySelectorAll('.chart-wrap').forEach(function (w) {
      w.classList.toggle('chart-loading', !!loading);
    });
  }

  function fetchDevicesOnly() {
    return fetch('/api/monitor/devices')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.devices) mergeDeviceOptions(data.devices);
      })
      .catch(function () {});
  }

  function filterMetricsForWindow(metrics, minutes) {
    if (!metrics || !metrics.length) return [];
    var minTs = Date.now() - minutes * 60 * 1000;
    return metrics.filter(function (m) {
      if (!m || !m.timestamp) return false;
      var t = new Date(m.timestamp).getTime();
      return !isNaN(t) && t >= minTs;
    });
  }

  function applyCachedHistoryToCharts() {
    if (!cachedMetrics) return;
    var m = filterMetricsForWindow(cachedMetrics, currentMinutes);
    setDualData(chartLoad, m, 'cpu_load', 'gpu_util');
    setDualData(chartClock, m, 'cpu_clock', 'gpu_clock', mhzToGhz, mhzToGhz);
    setDualData(chartTemp, m, 'cpu_temp', 'gpu_temp');
    setDualData(chartRamSwap, m, 'ram_percent', 'swap_percent');
    setData(chartGmem, m, 'gpu_mem_percent');
    setPcieData(m);
    renderLatest(cachedLatest);
  }

  function fetchHistoryOnly() {
    var gen = ++historyFetchGen;
    var dev = elDevice.value || currentDevice || '';
    var q = '/api/monitor/history?minutes=' + HISTORY_FETCH_MINUTES + '&max_points=' + HISTORY_MAX_POINTS;
    if (dev) q += '&device=' + encodeURIComponent(dev);
    return fetch(q)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (gen !== historyFetchGen) return;
        if (data.devices) mergeDeviceOptions(data.devices);
        cachedMetrics = data.metrics || [];
        cachedLatest = data.latest;
        applyCachedHistoryToCharts();
        elStatus.textContent = 'Updated ' + new Date().toLocaleTimeString();
      })
      .catch(function () {
        if (gen !== historyFetchGen) return;
        elStatus.textContent = 'Update failed';
      });
  }

  /** Load chart from DB immediately, then pull node backlog (slow), then refresh again.
   *  Node pull is deferred one tick so the browser can paint the first history response first. */
  function refreshHistoryWithPull(options) {
    options = options || {};
    var quietPull = options.quietPull !== false;
    fetchHistoryOnly();
    setTimeout(function () {
      requestSampleNow(false, { quiet: quietPull }).finally(function () {
        fetchHistoryOnly();
      });
    }, 0);
  }

  /** First paint: tiny device list + DB history in parallel; shimmer until history returns; node pull after. */
  function bootstrapMonitor() {
    setChartsLoading(true);
    elStatus.textContent = 'Loading…';
    fetchDevicesOnly();
    fetchHistoryOnly()
      .finally(function () {
        setChartsLoading(false);
      });
    setTimeout(function () {
      requestSampleNow(false, { quiet: true }).finally(function () {
        fetchHistoryOnly();
      });
    }, 0);
  }

  function requestSampleNow(refreshAfter, opts) {
    opts = opts || {};
    var quiet = opts.quiet === true;
    var dev = elDevice.value || currentDevice || '';
    if (!dev) {
      elStatus.textContent = 'Pick a device first.';
      return Promise.resolve(false);
    }
    if (!quiet && elFetchNowBtn) elFetchNowBtn.disabled = true;
    if (!quiet) elStatus.textContent = 'Requesting sample from node...';
    return fetch('/api/monitor/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device: dev })
    })
      .then(function (r) {
        return r.json().then(function (data) { return { status: r.status, data: data }; });
      })
      .then(function (res) {
        if (res.status >= 400 || !res.data || !res.data.ok) {
          var msg = (res.data && res.data.error) || 'request failed';
          throw new Error(msg);
        }
        if (!quiet) {
          elStatus.textContent = 'Sample received at ' + new Date().toLocaleTimeString();
        }
        if (refreshAfter) fetchHistoryOnly();
        return true;
      })
      .catch(function (err) {
        elStatus.textContent = 'Sample request failed: ' + (err && err.message ? err.message : 'unknown error');
        return false;
      })
      .finally(function () {
        if (!quiet && elFetchNowBtn) elFetchNowBtn.disabled = false;
      });
  }

  elDevice.addEventListener('change', function () {
    currentDevice = elDevice.value;
    if (elMergeTarget && elMergeTarget.value === currentDevice) {
      elMergeTarget.value = '';
    }
    try { localStorage.setItem('autolab_hw_device', currentDevice); } catch (e) {}
    refreshHistoryWithPull();
  });

  if (elFetchNowBtn) {
    elFetchNowBtn.addEventListener('click', function () {
      refreshHistoryWithPull({ quietPull: false });
    });
  }

  if (elMergeBtn) {
    elMergeBtn.addEventListener('click', function () {
      var source = (elDevice.value || '').trim();
      var target = (elMergeTarget && elMergeTarget.value ? elMergeTarget.value : '').trim();
      if (!source) {
        alert('Pick a source device first.');
        return;
      }
      if (!target) {
        alert('Enter a target device name.');
        return;
      }
      if (!isValidDeviceName(target)) {
        alert('Invalid target name. Use 1-64 chars: letters, numbers, dot, underscore, hyphen.');
        return;
      }
      if (source === target) {
        alert('Source and target are the same.');
        return;
      }
      var ok = window.confirm(
        'Move all samples from "' + source + '" into "' + target + '"?\n\nThis cannot be undone.'
      );
      if (!ok) return;

      elMergeBtn.disabled = true;
      elStatus.textContent = 'Moving data...';
      fetch('/api/monitor/device/reassign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source, target: target })
      })
        .then(function (r) {
          return r.json().then(function (data) { return { status: r.status, data: data }; });
        })
        .then(function (res) {
          if (res.status >= 400 || !res.data || !res.data.ok) {
            var msg = (res.data && res.data.error) || 'Reassign failed';
            throw new Error(msg);
          }
          currentDevice = target;
          elDevice.value = currentDevice;
          if (elMergeTarget) elMergeTarget.value = '';
          if (res.data.devices) mergeDeviceOptions(res.data.devices);
          fetchHistoryOnly();
          elStatus.textContent = 'Moved ' + res.data.moved + ' sample(s) from ' + source + ' to ' + target + '.';
          closeMergePopover();
        })
        .catch(function (err) {
          elStatus.textContent = 'Move failed: ' + (err && err.message ? err.message : 'unknown error');
        })
        .finally(function () {
          elMergeBtn.disabled = false;
        });
    });
  }

  if (elMergeToggle) {
    elMergeToggle.addEventListener('click', function (evt) {
      evt.stopPropagation();
      if (isMergePopoverOpen()) {
        closeMergePopover();
      } else {
        openMergePopover();
      }
    });
  }

  if (elMergeCancel) {
    elMergeCancel.addEventListener('click', function () {
      closeMergePopover();
    });
  }

  document.addEventListener('click', function (evt) {
    if (!isMergePopoverOpen()) return;
    var root = elMergePopover && elMergePopover.parentElement;
    if (root && !root.contains(evt.target)) {
      closeMergePopover();
    }
  });

  document.addEventListener('keydown', function (evt) {
    if (evt.key === 'Escape' && isMergePopoverOpen()) {
      closeMergePopover();
    }
  });

  var pollMs = 30 * 1000;

  function refreshTick() {
    fetchHistoryOnly();
  }

  bootstrapMonitor();
  setInterval(refreshTick, pollMs);

  document.querySelectorAll('.range-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.range-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentMinutes = parseInt(btn.getAttribute('data-minutes'), 10);
      if (cachedMetrics) applyCachedHistoryToCharts();
      else fetchHistoryOnly();
    });
  });
})();
