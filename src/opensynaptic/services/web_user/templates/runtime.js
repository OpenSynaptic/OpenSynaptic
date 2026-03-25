
(function () {
  function byId(id) { return document.getElementById(id); }
  function setText(id, v) { var el = byId(id); if (el) { el.textContent = String(v); } }
  function setHtml(id, html) { var el = byId(id); if (el) { el.innerHTML = String(html || ''); } }
  function escHtml(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function setBanner(state, msg) {
    var el = byId('connectionBanner');
    if (!el) { return; }
    el.className = 'conn-banner' + (state === 'ok' ? ' ok' : (state === 'bad' ? ' bad' : ''));
    el.textContent = msg;
  }
  function flashButtonState(btn, stateClass) {
    if (!btn || !btn.classList || !stateClass) { return; }
    btn.classList.remove('btn-success');
    btn.classList.remove('btn-fail');
    btn.classList.add(stateClass);
    setTimeout(function () {
      if (btn && btn.classList) { btn.classList.remove(stateClass); }
    }, 520);
  }
  function setButtonBusy(btn, busy, busyLabel) {
    if (!btn) { return; }
    if (busy) {
      if (!btn.getAttribute('data-os-btn-label')) {
        btn.setAttribute('data-os-btn-label', String(btn.textContent || ''));
      }
      btn.disabled = true;
      if (busyLabel) { btn.textContent = String(busyLabel); }
      if (btn.classList) { btn.classList.add('btn-busy'); }
      return;
    }
    var baseLabel = btn.getAttribute('data-os-btn-label');
    if (baseLabel != null && baseLabel !== '') {
      btn.textContent = baseLabel;
    }
    btn.disabled = false;
    if (btn.classList) { btn.classList.remove('btn-busy'); }
    btn.removeAttribute('data-os-btn-label');
  }
  function tokenHeader(xhr) {
    var tokenEl = byId('token');
    var token = tokenEl ? String(tokenEl.value || '').trim() : '';
    if (token) { xhr.setRequestHeader('X-Admin-Token', token); }
  }
  function req(method, path, body, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, path, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    tokenHeader(xhr);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          var data = JSON.parse(xhr.responseText || '{}');
          setBanner('ok', 'Connected to web service.');
          cb(null, data);
          return;
        } catch (e) {
          setBanner('bad', 'Connected but invalid JSON response.');
          cb(e || new Error('invalid json'));
          return;
        }
      }
      setBanner('bad', 'Disconnected: HTTP ' + String(xhr.status) + ' (auto retrying)');
      cb(new Error('http ' + String(xhr.status)));
    };
    try {
      xhr.send(body ? JSON.stringify(body) : null);
    } catch (e) {
      setBanner('bad', 'Disconnected: network error (auto retrying)');
      cb(e || new Error('network error'));
    }
  }
  function renderOverview(payload) {
    var d = payload && payload.overview ? payload.overview : {};
    var idn = d.identity || {};
    var svc = d.service || {};
    var m = d.overview_metrics || {};
    var run = m.run_stats || {};
    var perf = m.performance_stats || {};
    var httpStats = m.http_stats || {};
    var jobs = m.jobs || {};
    var dot = byId('runningDot');
    if (dot) { dot.classList.toggle('ok', !!svc.running); }
    setText('runningLabel', svc.running ? 'service running' : 'service stopped');
    setText('kpiDevice', idn.device_id || '-');
    setText('kpiAid', idn.assigned_id == null ? '-' : idn.assigned_id);
    setText('kpiCore', idn.core_backend || '-');
    setText('kpiUp', String(svc.uptime_s || 0) + ' s');
    setText('runStatus', run.status || 'idle');
    setText('runPackets', run.packets_processed || 0);
    setText('runLatency', run.avg_packet_latency_ms || 0.0);
    setText('runErrors', run.tick_errors || 0);
    setText('perfStatsView', JSON.stringify(perf, null, 2));
    renderHttpStats(httpStats);
    setText('jobStatsView', JSON.stringify({total: jobs.total || 0, recent: jobs.recent || []}, null, 2));
  }
  function renderHttpStats(httpStats) {
    var s = httpStats || {};
    var total = Number(s.total || 0);
    var minuteStart = Number(s.window_start_epoch || 0);
    var statusBands = s.status_bands || {};
    var statusCodes = s.status || {};
    var topPaths = s.top_paths || [];

    var chips = '';
    var order = ['2xx', '3xx', '4xx', '5xx', 'unknown'];
    for (var i = 0; i < order.length; i++) {
      var k = order[i];
      if (statusBands[k] == null) { continue; }
      var cls = 'os-badge os-badge-neutral';
      if (k === '2xx') { cls = 'os-badge os-badge-ok'; }
      if (k === '3xx') { cls = 'os-badge os-badge-mid'; }
      if (k === '4xx' || k === '5xx') { cls = 'os-badge os-badge-bad'; }
      chips += '<span class="' + cls + '">' + escHtml(k) + ': ' + escHtml(statusBands[k]) + '</span>';
    }
    if (!chips) { chips = '<span class="muted">No status yet</span>'; }

    var codeParts = [];
    for (var code in statusCodes) {
      if (!Object.prototype.hasOwnProperty.call(statusCodes, code)) { continue; }
      codeParts.push(String(code) + '=' + String(statusCodes[code]));
    }
    codeParts.sort();
    var codesText = codeParts.length ? codeParts.join(', ') : '-';

    var rows = '';
    if (topPaths && topPaths.length) {
      for (var j = 0; j < topPaths.length; j++) {
        var row = topPaths[j] || [];
        var p = row[0] == null ? '' : String(row[0]);
        var c = row[1] == null ? 0 : row[1];
        rows += '<tr><td><code>' + escHtml(p) + '</code></td><td class="right">' + escHtml(c) + '</td></tr>';
      }
    } else {
      rows = '<tr><td colspan="2" class="muted">No requests in current minute window.</td></tr>';
    }

    var minuteText = minuteStart > 0 ? new Date(minuteStart * 1000).toLocaleTimeString() : '-';
    var html = '' +
      '<div class="http-stats-wrap">' +
      '<div class="row"><span class="muted">Total:</span><strong>' + escHtml(total) + '</strong><span class="muted">Window:</span><span>' + escHtml(minuteText) + '</span></div>' +
      '<div class="http-badges">' + chips + '</div>' +
      '<div class="http-codes muted">Status codes: ' + escHtml(codesText) + '</div>' +
      '<table class="http-table"><thead><tr><th>Path</th><th class="right">Count</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '</div>';
    setHtml('httpStatsView', html);
  }
  function switchSection(name) {
    var targetName = String(name || '').trim();
    if (!targetName) { return; }
    var sections = document.querySelectorAll('.section');
    for (var i = 0; i < sections.length; i++) { sections[i].classList.remove('show'); }
    var sec = byId('sec-' + targetName);
    if (sec) { sec.classList.add('show'); }
    var navs = document.querySelectorAll('.nav-btn[data-target]');
    for (var j = 0; j < navs.length; j++) {
      var v = navs[j].getAttribute('data-target');
      navs[j].classList.toggle('active', v === targetName);
    }
  }
  function reloadUsers() {
    req('GET', '/users', null, function (err, usersPayload) {
      if (err || !usersPayload) { return; }
      var rows = usersPayload.users || [];
      var html = '';
      for (var i = 0; i < rows.length; i++) {
        var u = rows[i] || {};
        var uname = String(u.username || '');
        var role = String(u.role || 'user');
        var checked = u.enabled ? 'checked' : '';
        html += '<tr>' +
          '<td>' + uname + '</td>' +
          '<td><input id="role-' + uname + '" value="' + role + '"></td>' +
          '<td><input id="on-' + uname + '" type="checkbox" ' + checked + '></td>' +
          '<td><button data-user-action="update" data-username="' + uname + '">Update</button> <button data-user-action="delete" data-username="' + uname + '">Delete</button></td>' +
          '</tr>';
      }
      var tb = byId('users');
      if (tb) { tb.innerHTML = html; }
    });
  }
  function loadUiOptions() {
    req('GET', '/api/ui/config', null, function (err, payload) {
      if (err || !payload || !payload.ui) { return; }
      var ui = payload.ui || {};
      var theme = byId('uiTheme');
      var layout = byId('uiLayout');
      var refresh = byId('uiRefresh');
      var compact = byId('uiCompact');
      if (theme && ui.ui_theme != null) { theme.value = String(ui.ui_theme); }
      if (layout && ui.ui_layout != null) { layout.value = String(ui.ui_layout); }
      if (refresh && ui.ui_refresh_seconds != null) { refresh.value = String(ui.ui_refresh_seconds); }
      if (compact) { compact.checked = !!ui.ui_compact; }
      var body = document.body;
      if (body && body.classList) {
        body.classList.toggle('light', String(ui.ui_theme || '') === 'router-light');
        body.classList.toggle('compact', !!ui.ui_compact);
      }
    });
  }
  function saveUiOptions() {
    var theme = byId('uiTheme');
    var layout = byId('uiLayout');
    var refresh = byId('uiRefresh');
    var compact = byId('uiCompact');
    var payload = {
      ui_theme: theme ? theme.value : 'router-dark',
      ui_layout: layout ? layout.value : 'sidebar',
      ui_refresh_seconds: parseInt(String(refresh ? refresh.value : '3'), 10) || 3,
      ui_compact: compact ? !!compact.checked : false,
    };
    var btn = byId('uiSaveBtn');
    if (btn) { setButtonBusy(btn, true, 'Saving...'); }
    req('PUT', '/api/ui/config', payload, function (err, out) {
      setText('uiResult', JSON.stringify(out || {ok: false, error: String(err || 'request failed')}, null, 2));
      if (btn) {
        setButtonBusy(btn, false);
        flashButtonState(btn, !!(out && out.ok) ? 'btn-success' : 'btn-fail');
      }
      loadUiOptions();
    });
  }
  function toggleFullCmdOutput() {
    var full = byId('cmdOutputFull');
    if (!full) { return; }
    var hidden = full.style.display === 'none' || full.style.display === '';
    full.style.display = hidden ? 'block' : 'none';
  }
  function reloadAll(silent) {
    var refreshBtn = byId('refreshBtn');
    var manualRefresh = !silent;
    if (manualRefresh) { setButtonBusy(refreshBtn, true, 'Refreshing...'); }
    function done(ok) {
      if (!manualRefresh) { return; }
      setButtonBusy(refreshBtn, false);
      flashButtonState(refreshBtn, ok ? 'btn-success' : 'btn-fail');
    }
    req('GET', '/api/overview', null, function (err, payload) {
      if (err || !payload) {
        setText('perfStatsView', 'Failed to load overview.');
        setHtml('httpStatsView', '<span class="muted">Failed to load HTTP stats.</span>');
        done(false);
        return;
      }
      renderOverview(payload);
      req('GET', '/users', null, function (_e, usersPayload) {
        if (_e || !usersPayload) {
          done(false);
          return;
        }
        var rows = usersPayload.users || [];
        var html = '';
        for (var i = 0; i < rows.length; i++) {
          var u = rows[i] || {};
          var uname = String(u.username || '');
          var role = String(u.role || 'user');
          var checked = u.enabled ? 'checked' : '';
          html += '<tr>' +
            '<td>' + uname + '</td>' +
            '<td><input id="role-' + uname + '" value="' + role + '"></td>' +
            '<td><input id="on-' + uname + '" type="checkbox" ' + checked + '></td>' +
            '<td><button data-user-action="update" data-username="' + uname + '">Update</button> <button data-user-action="delete" data-username="' + uname + '">Delete</button></td>' +
            '</tr>';
        }
        var tb = byId('users');
        if (tb) { tb.innerHTML = html; }
        done(true);
      });
    });
  }
  function setCmd(text) {
    var el = byId('cmdLine');
    if (el) { el.value = String(text || ''); }
  }
  function runCommandLine() {
    var el = byId('cmdLine');
    var line = el ? String(el.value || '').trim() : '';
    if (!line) { return; }
    req('POST', '/api/oscli/execute', {command: line, background: true}, function (err, payload) {
      setText('cmdResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function loadCommandHelp() {
    req('POST', '/api/oscli/execute', {command: 'help --full', background: false}, function (err, payload) {
      setText('cmdResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function renderPluginItems(payload) {
    var view = byId('pluginItemsView');
    if (!view) { return; }
    var items = payload && payload.items ? payload.items : [];
    if (!items.length) { view.textContent = 'No plugin entries found.'; return; }
    var html = '<div class="opt-cat"><div class="opt-head">Service Plugins (' + items.length + ')</div>';
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      var selectedTrue = it.enabled ? 'selected' : '';
      var selectedFalse = it.enabled ? '' : 'selected';
      html += '<div class="opt-row">' +
        '<div><div><strong>' + String(it.name || '') + '</strong></div><div class="opt-meta">mode=' + String(it.mode || 'manual') + ' | ' + (it.mounted ? 'mounted' : 'not-mounted') + ' | ' + (it.loaded ? 'loaded' : 'idle') + '</div></div>' +
        '<div><select data-plugin-name="' + String(it.name || '') + '"><option value="true" ' + selectedTrue + '>true</option><option value="false" ' + selectedFalse + '>false</option></select></div>' +
        '<div><button data-plugin-apply="' + String(it.name || '') + '">Apply</button></div>' +
        '</div>';
    }
    html += '</div>';
    view.innerHTML = html;
  }
  function loadPluginControl() {
    req('GET', '/api/plugins', null, function (err, payload) {
      if (err || !payload) {
        setText('pluginItemsView', 'Failed to load plugins: ' + String(err || 'request failed'));
        return;
      }
      renderPluginItems(payload);
      setText('pluginResult', JSON.stringify(payload, null, 2));
    });
  }
  function setPluginEnabled(name, enabled, onComplete) {
    req('POST', '/api/plugins', {plugin: name, action: 'set_enabled', enabled: !!enabled}, function (err, payload) {
      var result = payload || {ok: false, error: String(err || 'request failed')};
      var status = result.ok ? '✓ Applied' : '✗ Failed';
      setText('pluginResult', status + ': ' + name + ' - ' + JSON.stringify(result, null, 2));
      if (result.ok) { setBanner('ok', 'Plugin "' + name + '" updated'); }
      else { setBanner('bad', 'Failed to update plugin: ' + (result.error || 'unknown error')); }
      if (!err && payload) { renderPluginItems(payload); }
      reloadAll();
      if (typeof onComplete === 'function') { onComplete(result); }
    });
  }
  function renderTransportItems(payload) {
    var view = byId('transportItemsView');
    if (!view) { return; }
    var items = payload && payload.items ? payload.items : [];
    if (!items.length) { view.textContent = 'No transport entries found.'; return; }
    var html = '<div class="opt-cat"><div class="opt-head">Transport/Physical/Application (' + items.length + ')</div>';
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      var selectedTrue = it.enabled ? 'selected' : '';
      var selectedFalse = it.enabled ? '' : 'selected';
      html += '<div class="opt-row">' +
        '<div><div><strong>' + String(it.name || '') + '</strong></div><div class="opt-meta">layer=' + String(it.layer || '') + '</div></div>' +
        '<div><select data-medium-name="' + String(it.name || '') + '"><option value="true" ' + selectedTrue + '>true</option><option value="false" ' + selectedFalse + '>false</option></select></div>' +
        '<div><button data-medium-apply="' + String(it.name || '') + '">Apply</button></div>' +
        '</div>';
    }
    html += '</div>';
    view.innerHTML = html;
  }
  function loadTransportControl() {
    req('GET', '/api/transport', null, function (err, payload) {
      if (err || !payload) {
        setText('transportItemsView', 'Failed to load transport list: ' + String(err || 'request failed'));
        return;
      }
      renderTransportItems(payload);
      setText('transportResult', JSON.stringify(payload, null, 2));
    });
  }
  function setTransportEnabled(name, enabled, onComplete) {
    req('POST', '/api/transport', {medium: name, enabled: !!enabled}, function (err, payload) {
      var result = payload || {ok: false, error: String(err || 'request failed')};
      var status = result.ok ? '✓ Applied' : '✗ Failed';
      setText('transportResult', status + ': ' + name + ' - ' + JSON.stringify(result, null, 2));
      if (result.ok) { setBanner('ok', 'Transport "' + name + '" updated'); }
      else { setBanner('bad', 'Failed to update transport: ' + (result.error || 'unknown error')); }
      loadTransportControl();
      reloadAll();
      if (typeof onComplete === 'function') { onComplete(result); }
    });
  }
  function loadOptionSchema() {
    var only = byId('onlyWritable');
    var onlyWritable = only && !!only.checked;
    req('GET', '/api/options/schema?only_writable=' + (onlyWritable ? '1' : '0'), null, function (err, payload) {
      if (err || !payload) {
        setText('optionSchemaView', 'Failed to load option schema: ' + String(err || 'request failed'));
        return;
      }
      if (typeof renderOptionSchemaFallback === 'function') {
        renderOptionSchemaFallback(payload);
      } else {
        setText('optionSchemaView', JSON.stringify(payload, null, 2));
      }
    });
  }
  function applyDirtyOptions() {
    if (typeof __optionDraft === 'undefined' || !__optionDraft) {
      setText('optionApplyResult', JSON.stringify({ok: false, error: 'option runtime not initialized'}, null, 2));
      return;
    }
    var updates = [];
    for (var k in __optionDraft) {
      if (!Object.prototype.hasOwnProperty.call(__optionDraft, k)) { continue; }
      var it = __optionDraft[k];
      try {
        updates.push({key: it.key, value_type: it.value_type, value: parseOptionValue(it.raw_value, it.value_type)});
      } catch (e) {
        setText('optionApplyResult', JSON.stringify({ok: false, key: it.key, error: String(e)}, null, 2));
        return;
      }
    }
    if (!updates.length) {
      setText('optionApplyResult', JSON.stringify({ok: true, changed: [], info: 'no dirty fields'}, null, 2));
      return;
    }
    var btn = byId('optionsApplyBtn');
    if (btn) { setButtonBusy(btn, true, 'Processing...'); }
    setText('optionApplyResult', 'Sending updates...');
    req('PUT', '/api/options', {updates: updates}, function (err, payload) {
      var result = payload || {ok: false, error: String(err || 'request failed')};
      var status = result.ok ? '✓ SUCCESS' : '✗ FAILED';
      setText('optionApplyResult', status + ' - ' + JSON.stringify(result, null, 2));
      if (result.ok) { setBanner('ok', 'Options applied successfully'); }
      else { setBanner('bad', 'Failed to apply options: ' + (result.error || 'unknown error')); }
      __optionDraft = {};
      if (btn) {
        setButtonBusy(btn, false);
        flashButtonState(btn, result.ok ? 'btn-success' : 'btn-fail');
      }
      setTimeout(function () { loadOptionSchema(); }, 300);
    });
  }
  function getConfig() {
    var key = byId('cfgKey');
    var path = '/api/config';
    if (key && String(key.value || '').trim()) {
      path += '?key=' + encodeURIComponent(String(key.value).trim());
    }
    req('GET', path, null, function (err, payload) {
      setText('configResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function setConfig() {
    var key = byId('cfgKey');
    var value = byId('cfgValue');
    var valueType = byId('cfgType');
    req('PUT', '/api/config', {
      key: key ? key.value : '',
      value: value ? value.value : '',
      value_type: valueType ? valueType.value : 'json',
    }, function (err, payload) {
      setText('configResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
      reloadAll();
    });
  }
  function addUser() {
    var u = byId('username');
    var r = byId('role');
    var username = u ? String(u.value || '').trim() : '';
    if (!username) { return; }
    req('POST', '/users', {username: username, role: r ? (r.value || 'user') : 'user', enabled: true}, function () {
      if (u) { u.value = ''; }
      reloadAll();
    });
  }
  function updateUser(username) {
    var roleEl = byId('role-' + username);
    var onEl = byId('on-' + username);
    req('PUT', '/users/' + encodeURIComponent(username), {
      role: roleEl ? roleEl.value : null,
      enabled: onEl ? !!onEl.checked : null,
    }, function () { reloadAll(); });
  }
  function delUser(username) {
    req('DELETE', '/users/' + encodeURIComponent(username), null, function () { reloadAll(); });
  }
  function runSelfCheck() {
    var report = {
      ts: Math.floor(Date.now() / 1000),
      mode: 'external-runtime',
      location: window.location.href,
      runtime_loaded: !!window.__OS_WEB_RUNTIME_LOADED,
      checks: {},
    };
    function put(name, ok, status, sample) {
      report.checks[name] = {ok: !!ok, status: status, sample: String(sample || '')};
      setText('selfCheckView', JSON.stringify(report, null, 2));
    }
    req('GET', '/api/health', null, function (e1, d1) {
      put('health', !e1, e1 ? 'error' : 200, e1 ? String(e1) : JSON.stringify(d1 || {}).slice(0, 120));
    });
    req('GET', '/api/overview', null, function (e2, d2) {
      put('overview', !e2, e2 ? 'error' : 200, e2 ? String(e2) : JSON.stringify(d2 || {}).slice(0, 120));
    });
    req('GET', '/api/web_runtime.js', null, function (e3, _d3) {
      put('runtime_js', !e3, e3 ? 'error' : 200, e3 ? String(e3) : 'runtime script reachable');
    });
  }
  var __optionDraft = {};
  var __optionSubState = {keyEnc: '', mode: 'json', value: null};
  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function parseOptionValue(raw, t) {
    if (t === 'bool') { return String(raw) === 'true'; }
    if (t === 'int') { return parseInt(String(raw || '0'), 10); }
    if (t === 'float') { return parseFloat(String(raw || '0')); }
    if (t === 'json') { return JSON.parse(String(raw || 'null')); }
    return String(raw == null ? '' : raw);
  }
  function optionControlHtml(f) {
    var t = String(f.type || 'json');
    var ek = encodeURIComponent(String(f.key || ''));
    if (t === 'bool') {
      var cur = String(!!f.value);
      return '<select data-opt-key-enc="' + ek + '" data-opt-type="bool">' +
        '<option value="true" ' + (cur === 'true' ? 'selected' : '') + '>true</option>' +
        '<option value="false" ' + (cur === 'false' ? 'selected' : '') + '>false</option>' +
      '</select>';
    }
    if (t === 'int' || t === 'float') {
      return '<input type="number" data-opt-key-enc="' + ek + '" data-opt-type="' + t + '" value="' + esc(f.value) + '">';
    }
    if (t === 'str') {
      return '<input type="text" data-opt-key-enc="' + ek + '" data-opt-type="str" value="' + esc(f.value) + '">';
    }
    return '<textarea data-opt-key-enc="' + ek + '" data-opt-type="json">' + esc(JSON.stringify(f.value, null, 2)) + '</textarea>';
  }
  function markOptionDirtyFromControl(ctrl) {
    if (!ctrl || !ctrl.getAttribute) { return; }
    var ek = ctrl.getAttribute('data-opt-key-enc');
    var tp = ctrl.getAttribute('data-opt-type') || 'json';
    if (!ek) { return; }
    __optionDraft[ek] = {key: decodeURIComponent(ek), value_type: tp, raw_value: ctrl.value};
  }
  function setOptionControlValue(ek, value, tp) {
    var host = byId('optionSchemaView');
    if (!host) { return false; }
    var q = host.querySelector('[data-opt-key-enc="' + ek + '"]');
    if (!q) { return false; }
    var typeName = String(tp || q.getAttribute('data-opt-type') || 'json');
    if (typeName === 'json') { q.value = JSON.stringify(value, null, 2); }
    else { q.value = String(value == null ? '' : value); }
    markOptionDirtyFromControl(q);
    autoSizeOptionTextArea(q);
    return true;
  }
  function renderSubArrayEditor(items) {
    var body = byId('optionSubEditorBody');
    if (!body) { return; }
    var rows = '';
    for (var i = 0; i < items.length; i++) {
      rows += '<div class="sub-editor-item">' +
        '<input data-sub-item-index="' + i + '" value="' + esc(items[i]) + '">' +
        '<button data-sub-remove-index="' + i + '">Remove</button>' +
      '</div>';
    }
    body.innerHTML = rows || '<div class="muted">No items. Click Add Item.</div>';
  }
  function collectSubEditorValue() {
    if (__optionSubState.mode === 'array') {
      var body = byId('optionSubEditorBody');
      if (!body) { return []; }
      var list = body.querySelectorAll('input[data-sub-item-index]');
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var v = String(list[i].value || '').trim();
        if (v) { out.push(v); }
      }
      return out;
    }
    var raw = byId('optionSubEditorJson');
    return JSON.parse(String(raw ? raw.value : 'null'));
  }
  function openSubEditor(ek) {
    var host = byId('optionSchemaView');
    if (!host) { return; }
    var q = host.querySelector('[data-opt-key-enc="' + ek + '"]');
    if (!q) { return; }
    var tp = q.getAttribute('data-opt-type') || 'json';
    if (tp !== 'json') {
      setText('optionApplyResult', 'Sub editor is currently for json fields only.');
      return;
    }
    var val = null;
    try {
      val = parseOptionValue(q.value, 'json');
    } catch (e) {
      setText('optionApplyResult', JSON.stringify({ok: false, error: 'invalid json in field', detail: String(e)}, null, 2));
      return;
    }
    __optionSubState = {
      keyEnc: ek,
      mode: Array.isArray(val) && val.every(function (x) { return typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean'; }) ? 'array' : 'json',
      value: val,
    };

    var panel = byId('optionSubEditor');
    var title = byId('optionSubEditorTitle');
    var key = byId('optionSubEditorKey');
    var addBtn = byId('optionSubAddItemBtn');
    var body = byId('optionSubEditorBody');
    if (!panel || !title || !key || !addBtn || !body) { return; }

    title.textContent = 'Sub Option Editor';
    key.textContent = decodeURIComponent(ek);
    panel.hidden = false;
    if (__optionSubState.mode === 'array') {
      addBtn.style.display = 'inline-block';
      renderSubArrayEditor(Array.isArray(val) ? val : []);
    } else {
      addBtn.style.display = 'none';
      body.innerHTML = '<textarea id="optionSubEditorJson" class="sub-editor-json">' + esc(JSON.stringify(val, null, 2)) + '</textarea>';
    }
  }
  function closeSubEditor() {
    var panel = byId('optionSubEditor');
    if (panel) { panel.hidden = true; }
  }
  function autoSizeOptionTextArea(el) {
    if (!el || String(el.tagName || '').toLowerCase() !== 'textarea') { return; }
    el.style.height = 'auto';
    var h = Math.max(140, el.scrollHeight || 140);
    el.style.height = String(h) + 'px';
  }
  function autoSizeAllOptionTextAreas() {
    var host = byId('optionSchemaView');
    if (!host) { return; }
    var boxes = host.querySelectorAll('textarea[data-opt-type="json"]');
    for (var i = 0; i < boxes.length; i++) { autoSizeOptionTextArea(boxes[i]); }
  }
  function renderOptionSchemaFallback(payload) {
    var host = byId('optionSchemaView');
    if (!host) { return; }
    var schema = payload && payload.schema ? payload.schema : {categories: []};
    var cats = schema.categories || [];
    if (!cats.length) { host.textContent = 'No option fields available.'; return; }
    var html = '';
    for (var i = 0; i < cats.length; i++) {
      var c = cats[i] || {};
      var fields = c.fields || [];
      html += '<div class="opt-cat"><div class="opt-head">' + esc(c.title) + ' (' + fields.length + ')</div>';
      for (var j = 0; j < fields.length; j++) {
        var f = fields[j] || {};
        var ek = encodeURIComponent(String(f.key || ''));
        html += '<div class="opt-row">' +
          '<div><div><strong>' + esc(f.label || f.key) + '</strong></div><div class="opt-meta">' + esc(f.description || '') + '</div><div class="opt-key">' + esc(f.key) + ' (' + esc(f.type) + ')</div></div>' +
          '<div>' + optionControlHtml(f) + '</div>' +
          '<div><button data-opt-apply-enc="' + ek + '">Apply</button>' +
          (String(f.type || '') === 'json' ? ' <button data-opt-subedit-enc="' + ek + '">Sub Edit</button>' : '') +
          '</div>' +
        '</div>';
      }
      html += '</div>';
    }
    host.innerHTML = html;
    autoSizeAllOptionTextAreas();
  }
  function bindUiHandlers() {
    var nav = document.querySelectorAll('.nav-btn[data-target]');
    for (var i = 0; i < nav.length; i++) {
      if (nav[i].getAttribute && nav[i].getAttribute('onclick')) { continue; }
      nav[i].addEventListener('click', function (evt) {
        var target = evt.currentTarget ? evt.currentTarget.getAttribute('data-target') : null;
        if (!target) { return; }
        var sections = document.querySelectorAll('.section');
        for (var s = 0; s < sections.length; s++) { sections[s].classList.remove('show'); }
        var sec = byId('sec-' + target);
        if (sec) { sec.classList.add('show'); }
        var navs = document.querySelectorAll('.nav-btn[data-target]');
        for (var n = 0; n < navs.length; n++) { navs[n].classList.remove('active'); }
        if (evt.currentTarget && evt.currentTarget.classList) { evt.currentTarget.classList.add('active'); }
      });
    }
    var examples = document.querySelectorAll('.cmd-example[data-cmd]');
    for (var j = 0; j < examples.length; j++) {
      if (examples[j].getAttribute && examples[j].getAttribute('onclick')) { continue; }
      examples[j].addEventListener('click', function (evt) {
        var cmd = evt.currentTarget ? evt.currentTarget.getAttribute('data-cmd') : '';
        var line = byId('cmdLine');
        if (line && cmd) { line.value = cmd; }
      });
    }
    function wire(id, fn) {
      var el = byId(id);
      if (el && !(el.getAttribute && el.getAttribute('onclick'))) { el.addEventListener('click', fn); }
    }
    wire('refreshBtn', reloadAll);
    wire('selfCheckBtn', runSelfCheck);
    wire('pluginRunBtn', loadPluginControl);
    wire('transportApplyBtn', loadTransportControl);
    wire('configGetBtn', getConfig);
    wire('configSetBtn', setConfig);
    wire('userAddBtn', addUser);
    wire('userReloadBtn', reloadAll);
    wire('consoleRunBtn', runCommandLine);
    wire('consoleHelpBtn', loadCommandHelp);
    wire('optionsReloadBtn', loadOptionSchema);
    wire('optionsApplyBtn', applyDirtyOptions);
    wire('optionSubCloseBtn', closeSubEditor);
    wire('optionSubAddItemBtn', function () {
      if (__optionSubState.mode !== 'array') { return; }
      var body = byId('optionSubEditorBody');
      if (!body) { return; }
      var list = body.querySelectorAll('input[data-sub-item-index]');
      var arr = [];
      for (var i = 0; i < list.length; i++) { arr.push(String(list[i].value || '')); }
      arr.push('');
      renderSubArrayEditor(arr);
    });
    wire('optionSubApplyBtn', function () {
      if (!__optionSubState.keyEnc) { return; }
      try {
        var value = collectSubEditorValue();
        var ok = setOptionControlValue(__optionSubState.keyEnc, value, 'json');
        if (!ok) {
          setText('optionApplyResult', JSON.stringify({ok: false, error: 'target field not found'}, null, 2));
          return;
        }
        setText('optionApplyResult', JSON.stringify({ok: true, key: decodeURIComponent(__optionSubState.keyEnc), info: 'updated in field, click Apply/Apply Changed to save'}, null, 2));
        closeSubEditor();
      } catch (e) {
        setText('optionApplyResult', JSON.stringify({ok: false, error: String(e)}, null, 2));
      }
    });
    var usersTable = byId('users');
    if (usersTable) {
      usersTable.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var action = t.getAttribute('data-user-action');
        var username = t.getAttribute('data-username');
        if (!action || !username) { return; }
        if (action === 'update') { updateUser(username); }
        if (action === 'delete') { delUser(username); }
      });
    }
    var pview = byId('pluginItemsView');
    if (pview) {
      pview.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var name = t.getAttribute('data-plugin-apply');
        if (!name) { return; }
        var sel = pview.querySelector('select[data-plugin-name="' + name + '"]');
        var enabled = sel ? String(sel.value) === 'true' : true;
        var btn = t;
        setButtonBusy(btn, true, 'Applying...');
        setText('pluginResult', 'Applying plugin: ' + name + '...');
        setPluginEnabled(name, enabled, function (result) {
          setButtonBusy(btn, false);
          flashButtonState(btn, result && result.ok ? 'btn-success' : 'btn-fail');
        });
      });
    }
    var tview = byId('transportItemsView');
    if (tview) {
      tview.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var name = t.getAttribute('data-medium-apply');
        if (!name) { return; }
        var sel = tview.querySelector('select[data-medium-name="' + name + '"]');
        var enabled = sel ? String(sel.value) === 'true' : true;
        var btn = t;
        setButtonBusy(btn, true, 'Applying...');
        setText('transportResult', 'Applying transport: ' + name + '...');
        setTransportEnabled(name, enabled, function (result) {
          setButtonBusy(btn, false);
          flashButtonState(btn, result && result.ok ? 'btn-success' : 'btn-fail');
        });
      });
    }
    var opts = byId('optionSchemaView');
    if (opts) {
      opts.addEventListener('input', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var ek = t.getAttribute('data-opt-key-enc');
        var tp = t.getAttribute('data-opt-type') || 'json';
        if (!ek) { return; }
        __optionDraft[ek] = {key: decodeURIComponent(ek), value_type: tp, raw_value: t.value};
        autoSizeOptionTextArea(t);
      });
      opts.addEventListener('change', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var ek = t.getAttribute('data-opt-key-enc');
        var tp = t.getAttribute('data-opt-type') || 'json';
        if (!ek) { return; }
        __optionDraft[ek] = {key: decodeURIComponent(ek), value_type: tp, raw_value: t.value};
        autoSizeOptionTextArea(t);
      });
      opts.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var sk = t.getAttribute('data-opt-subedit-enc');
        if (sk) {
          openSubEditor(sk);
          return;
        }
        var ak = t.getAttribute('data-opt-apply-enc');
        if (!ak) { return; }
        var q = opts.querySelector('[data-opt-key-enc="' + ak + '"]');
        if (!q) { return; }
        var tp = q.getAttribute('data-opt-type') || 'json';
        var upd = null;
        try {
          upd = {key: decodeURIComponent(ak), value_type: tp, value: parseOptionValue(q.value, tp)};
        } catch (e) {
          setText('optionApplyResult', JSON.stringify({ok: false, error: String(e)}, null, 2));
          return;
        }
        var btn = t;
        setButtonBusy(btn, true, 'Sending...');
        setText('optionApplyResult', 'Applying option: ' + upd.key + '...');
        req('PUT', '/api/options', {updates: [upd]}, function (err, p) {
          var result = p || {ok: false, error: String(err || 'request failed')};
          var status = result.ok ? '✓' : '✗';
          setText('optionApplyResult', status + ' Option applied: ' + JSON.stringify(result, null, 2));
          if (result.ok) { setBanner('ok', 'Option "' + upd.key + '" applied'); }
          else { setBanner('bad', 'Failed: ' + (result.error || 'unknown error')); }
          setButtonBusy(btn, false);
          flashButtonState(btn, result.ok ? 'btn-success' : 'btn-fail');
          if (window.loadOptionSchema) { window.loadOptionSchema(); }
        });
      });
    }
    var subBody = byId('optionSubEditorBody');
    if (subBody) {
      subBody.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var idx = t.getAttribute('data-sub-remove-index');
        if (idx == null || idx === '') { return; }
        var list = subBody.querySelectorAll('input[data-sub-item-index]');
        var arr = [];
        for (var i = 0; i < list.length; i++) {
          if (String(i) === String(idx)) { continue; }
          arr.push(String(list[i].value || ''));
        }
        renderSubArrayEditor(arr);
      });
    }
  }
  window.reloadAll = window.reloadAll || reloadAll;
  window.switchSection = window.switchSection || switchSection;
  window.reloadUsers = window.reloadUsers || reloadUsers;
  window.loadUiOptions = window.loadUiOptions || loadUiOptions;
  window.saveUiOptions = window.saveUiOptions || saveUiOptions;
  window.toggleFullCmdOutput = window.toggleFullCmdOutput || toggleFullCmdOutput;
  window.setCmd = window.setCmd || setCmd;
  window.runCommandLine = window.runCommandLine || runCommandLine;
  window.loadCommandHelp = window.loadCommandHelp || loadCommandHelp;
  window.loadPluginControl = window.loadPluginControl || loadPluginControl;
  window.setPluginEnabled = window.setPluginEnabled || setPluginEnabled;
  window.loadTransportControl = window.loadTransportControl || loadTransportControl;
  window.setTransportEnabled = window.setTransportEnabled || setTransportEnabled;
  window.loadOptionSchema = window.loadOptionSchema || loadOptionSchema;
  window.applyDirtyOptions = window.applyDirtyOptions || applyDirtyOptions;
  window.getConfig = window.getConfig || getConfig;
  window.setConfig = window.setConfig || setConfig;
  window.addUser = window.addUser || addUser;
  window.updateUser = window.updateUser || updateUser;
  window.delUser = window.delUser || delUser;
  window.runSelfCheck = window.runSelfCheck || runSelfCheck;
  window.__OS_WEB_RUNTIME_LOADED = true;
  setBanner('warn', 'Connecting to web service...');
  setTimeout(bindUiHandlers, 100);
  setTimeout(function () { reloadAll(true); }, 50);
  setTimeout(loadUiOptions, 70);
  setTimeout(loadPluginControl, 90);
  setTimeout(loadTransportControl, 110);
  setTimeout(loadOptionSchema, 130);
  setInterval(function () { reloadAll(true); }, 3000);
  setTimeout(runSelfCheck, 350);
})();
