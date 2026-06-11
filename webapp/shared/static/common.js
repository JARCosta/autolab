(function () {
  'use strict';

  // Minimal shared utilities to keep module scripts small and consistent.
  // Add helpers here incrementally — keep functions well-named and tiny.
  window.autolab = window.autolab || {};
  var autolab = window.autolab;

  autolab.qs = function (sel, root) { return (root || document).querySelector(sel); };
  autolab.qsa = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  autolab.id = function (id) { return document.getElementById(id); };

  autolab.on = function (selOrEl, evt, cb) {
    if (typeof selOrEl === 'string') {
      autolab.qsa(selOrEl).forEach(function (el) { el.addEventListener(evt, cb); });
    } else if (selOrEl && selOrEl.addEventListener) {
      selOrEl.addEventListener(evt, cb);
    }
  };

  autolab.fetchJSON = function (url, opts) {
    opts = opts || {};
    return fetch(url, opts).then(function (r) { return r.json(); });
  };

  autolab.postJSON = function (url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.text().then(function (t) {
        var data = {};
        try { data = t ? JSON.parse(t) : {}; } catch (e) { /* ignore */ }
        if (!res.ok) {
          var err = (data && data.error) ? data.error : ('HTTP ' + res.status);
          var e = new Error(err);
          e.response = res;
          e.body = data;
          throw e;
        }
        return data;
      });
    });
  };

  autolab.setText = function (id, txt) {
    var el = autolab.id(id);
    if (!el) return;
    el.textContent = (txt == null) ? '\u2014' : txt;
  };

  autolab.cls = {
    add: function (el, c) { if (el && el.classList) el.classList.add(c); },
    remove: function (el, c) { if (el && el.classList) el.classList.remove(c); },
    toggle: function (el, c, force) { if (el && el.classList) el.classList.toggle(c, force); }
  };

})();
