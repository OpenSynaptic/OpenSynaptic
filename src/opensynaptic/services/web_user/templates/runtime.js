
(function () {
  var __jsonVerbose = false;
  var __visualCommandOptionMap = {};
  var __visualCommandFieldsMap = {};
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
  function applyJsonModeState() {
    var body = document.body;
    if (body && body.classList) {
      body.classList.toggle('json-collapsed', !__jsonVerbose);
    }
    var btn = byId('jsonToggleBtn');
    if (btn) {
      btn.textContent = __jsonVerbose ? 'JSON: ON' : 'JSON: OFF';
      btn.classList.toggle('primary', __jsonVerbose);
    }
    try { window.localStorage.setItem('os_web_json_verbose', __jsonVerbose ? '1' : '0'); } catch (_e) {}
  }
  function initJsonMode() {
    try {
      var raw = window.localStorage.getItem('os_web_json_verbose');
      __jsonVerbose = String(raw || '0') === '1';
    } catch (_e) {
      __jsonVerbose = false;
    }
    applyJsonModeState();
  }
  function toggleJsonMode() {
    __jsonVerbose = !__jsonVerbose;
    applyJsonModeState();
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
    var d = payload && payload.dashboard ? payload.dashboard : (payload && payload.overview ? payload.overview : {});
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
    hydrateDisplaySections(d.display_providers || null, d.display_sections || null);
  }
  function renderUsersTable(rows) {
    var data = rows || [];
    var html = '';
    for (var i = 0; i < data.length; i++) {
      var u = data[i] || {};
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
  }
  function displayValueHtml(value) {
    if (value == null) { return '<span class="muted">null</span>'; }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return '<div class="display-plain">' + escHtml(value) + '</div>';
    }
    return '<pre class="display-json">' + escHtml(JSON.stringify(value, null, 2)) + '</pre>';
  }
  function tableValueHtml(value) {
    var rows = [];
    if (Array.isArray(value)) {
      rows = value;
    } else if (value && typeof value === 'object') {
      rows = [value];
    }
    if (!rows.length) {
      return '<span class="muted">No table rows.</span>';
    }
    var cols = [];
    if (rows[0] && typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
      for (var key in rows[0]) {
        if (Object.prototype.hasOwnProperty.call(rows[0], key)) { cols.push(String(key)); }
      }
    }
    if (!cols.length) {
      return displayValueHtml(value);
    }
    var head = '';
    for (var i = 0; i < cols.length; i++) {
      head += '<th>' + escHtml(cols[i]) + '</th>';
    }
    var body = '';
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r] || {};
      var cells = '';
      for (var c = 0; c < cols.length; c++) {
        cells += '<td>' + escHtml(row[cols[c]]) + '</td>';
      }
      body += '<tr>' + cells + '</tr>';
    }
    return '<table class="http-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>';
  }
  function sanitizeHtml(rawHtml) {
    var host = document.createElement('div');
    host.innerHTML = String(rawHtml == null ? '' : rawHtml);
    var blockedTags = ['script', 'style', 'iframe', 'object', 'embed', 'link', 'meta'];
    for (var i = 0; i < blockedTags.length; i++) {
      var nodes = host.getElementsByTagName(blockedTags[i]);
      while (nodes && nodes.length) {
        var node = nodes[0];
        if (node && node.parentNode) { node.parentNode.removeChild(node); }
      }
    }
    var all = host.getElementsByTagName('*');
    for (var j = 0; j < all.length; j++) {
      var el = all[j];
      if (!el || !el.attributes) { continue; }
      var attrs = [];
      for (var k = 0; k < el.attributes.length; k++) {
        attrs.push(el.attributes[k].name);
      }
      for (var a = 0; a < attrs.length; a++) {
        var name = String(attrs[a] || '').toLowerCase();
        var value = String(el.getAttribute(attrs[a]) || '');
        if (name.indexOf('on') === 0) {
          el.removeAttribute(attrs[a]);
          continue;
        }
        if ((name === 'href' || name === 'src') && /^\s*javascript:/i.test(value)) {
          el.removeAttribute(attrs[a]);
        }
      }
    }
    return host.innerHTML;
  }
  function renderDisplayEntry(entry) {
    var fmt = String((entry && entry.format) || 'json').toLowerCase();
    var mode = String((entry && entry.render_mode) || 'safe_html').toLowerCase();
    var data = entry ? entry.data : null;
    if (fmt === 'html') {
      if (mode === 'json_only') {
        return displayValueHtml(data);
      }
      var html = String(data == null ? '' : data);
      if (mode !== 'trusted_html') {
        html = sanitizeHtml(html);
      }
      return '<div class="display-html">' + html + '</div>';
    }
    if (fmt === 'table') {
      return tableValueHtml(data);
    }
    return displayValueHtml(data);
  }
  function renderDisplayCards(entries) {
    var host = byId('displaySectionsView');
    if (!host) { return; }
    if (!entries || !entries.length) {
      host.innerHTML = '<span class="muted">No display sections registered.</span>';
      return;
    }
    var grouped = {};
    for (var i = 0; i < entries.length; i++) {
      var it = entries[i] || {};
      var category = String(it.category || 'plugin');
      if (!grouped[category]) { grouped[category] = []; }
      grouped[category].push(it);
    }
    var html = '';
    for (var cat in grouped) {
      if (!Object.prototype.hasOwnProperty.call(grouped, cat)) { continue; }
      var list = grouped[cat] || [];
      var block = '';
      for (var j = 0; j < list.length; j++) {
        var item = list[j] || {};
        var label = item.display_name || item.section_path || item.section_id || 'section';
        var badge = '<span class="muted">format=' + escHtml(item.format || 'json') + ' mode=' + escHtml(item.render_mode || 'safe_html') + '</span>';
        block += '<div class="display-card">' +
          '<div class="display-title">' + escHtml(label) + ' ' + badge + '</div>' +
          renderDisplayEntry(item) +
          '</div>';
      }
      html += '<div class="opt-cat"><div class="opt-head">' + escHtml(cat) + ' (' + list.length + ')</div>' + block + '</div>';
    }
    host.innerHTML = html;
  }
  function renderDisplaySections(sectionMap) {
    var entries = [];
    if (sectionMap && typeof sectionMap === 'object') {
      for (var category in sectionMap) {
        if (!Object.prototype.hasOwnProperty.call(sectionMap, category)) { continue; }
        var sections = sectionMap[category] || {};
        for (var sid in sections) {
          if (!Object.prototype.hasOwnProperty.call(sections, sid)) { continue; }
          entries.push({
            category: category,
            section_id: sid,
            section_path: category + ':' + sid,
            display_name: sid,
            format: 'json',
            render_mode: 'safe_html',
            data: sections[sid],
          });
        }
      }
    }
    renderDisplayCards(entries);
  }
  function renderDisplayProviders(meta) {
    var host = byId('displayProvidersView');
    if (!host) { return; }
    var providers = meta && meta.providers ? meta.providers : [];
    host.textContent = JSON.stringify({
      total_providers: meta && meta.total_providers ? meta.total_providers : providers.length,
      categories: (meta && meta.categories) || [],
      providers: providers,
    }, null, 2);
  }
  function requestDisplaySection(path, fmt, cb) {
    req('GET', '/api/display/render/' + path + '?format=' + encodeURIComponent(fmt), null, function (err, payload) {
      if (err || !payload || !payload.ok) {
        cb(err || new Error('render failed'), null);
        return;
      }
      cb(null, payload);
    });
  }
  function normalizeFormatOrder(provider) {
    var mode = String((provider && provider.render_mode) || 'safe_html').toLowerCase();
    if (mode === 'json_only') { return ['json']; }
    var preferred = String((provider && provider.preferred_format) || 'json').toLowerCase();
    var supported = (provider && provider.supported_formats && provider.supported_formats.length) ? provider.supported_formats.slice(0) : ['json'];
    var seen = {};
    var order = [];
    function addFmt(v) {
      var token = String(v || '').toLowerCase();
      if (!token || seen[token]) { return; }
      seen[token] = true;
      order.push(token);
    }
    addFmt(preferred);
    for (var i = 0; i < supported.length; i++) { addFmt(supported[i]); }
    addFmt('json');
    return order;
  }
  function fetchProviderSection(provider, cb) {
    var sectionPath = String((provider && provider.section_path) || ((provider && provider.plugin_name ? provider.plugin_name : '') + ':' + (provider && provider.section_id ? provider.section_id : '')));
    if (!sectionPath || sectionPath.indexOf(':') < 0) {
      cb({
        category: (provider && provider.category) || 'plugin',
        section_path: sectionPath,
        display_name: (provider && provider.display_name) || sectionPath,
        format: 'json',
        render_mode: (provider && provider.render_mode) || 'safe_html',
        data: {error: 'invalid section path'},
      });
      return;
    }
    var formatOrder = normalizeFormatOrder(provider);
    function tryAt(idx) {
      if (idx >= formatOrder.length) {
        cb({
          category: (provider && provider.category) || 'plugin',
          section_path: sectionPath,
          display_name: (provider && provider.display_name) || sectionPath,
          format: 'json',
          render_mode: (provider && provider.render_mode) || 'safe_html',
          data: {error: 'render failed'},
        });
        return;
      }
      var fmt = formatOrder[idx];
      requestDisplaySection(sectionPath, fmt, function (err, payload) {
        if (err || !payload) {
          tryAt(idx + 1);
          return;
        }
        cb({
          category: (provider && provider.category) || 'plugin',
          section_path: sectionPath,
          section_id: provider && provider.section_id,
          display_name: (provider && provider.display_name) || sectionPath,
          format: payload.resolved_format || payload.format || fmt,
          render_mode: (provider && provider.render_mode) || payload.render_mode || 'safe_html',
          data: payload.data,
        });
      });
    }
    tryAt(0);
  }
  function loadDisplaySectionsFromProviders(meta, fallbackSectionMap) {
    var providers = meta && meta.providers ? meta.providers : [];
    if (!providers.length) {
      renderDisplaySections(fallbackSectionMap || null);
      return;
    }
    var out = [];
    var pending = providers.length;
    function doneOne(entry) {
      out.push(entry);
      pending -= 1;
      if (pending <= 0) {
        renderDisplayCards(out);
      }
    }
    for (var i = 0; i < providers.length; i++) {
      fetchProviderSection(providers[i], doneOne);
    }
  }
  function hydrateDisplaySections(meta, fallbackSectionMap) {
    if (meta && meta.providers && meta.providers.length) {
      renderDisplayProviders(meta);
      loadDisplaySectionsFromProviders(meta, fallbackSectionMap);
      return;
    }
    req('GET', '/api/display/providers', null, function (pErr, providerPayload) {
      var resolvedMeta = (!pErr && providerPayload && providerPayload.metadata) ? providerPayload.metadata : null;
      renderDisplayProviders(resolvedMeta || {});
      if (resolvedMeta && resolvedMeta.providers && resolvedMeta.providers.length) {
        loadDisplaySectionsFromProviders(resolvedMeta, fallbackSectionMap);
        return;
      }
      renderDisplaySections(fallbackSectionMap || null);
    });
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
  function switchPluginPane(name) {
    var target = String(name || '').trim();
    if (!target) { return; }
    var panes = ['config', 'commands', 'visual'];
    for (var i = 0; i < panes.length; i++) {
      var k = panes[i];
      var paneEl = byId('pluginPane-' + k);
      var btnEl = byId('pluginPaneBtn-' + k);
      if (paneEl && paneEl.classList) { paneEl.classList.toggle('show', k === target); }
      if (btnEl && btnEl.classList) { btnEl.classList.toggle('active', k === target); }
    }
  }
  function reloadUsers() {
    req('GET', '/users', null, function (err, usersPayload) {
      if (err || !usersPayload) { return; }
      renderUsersTable(usersPayload.users || []);
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
    req('GET', '/api/dashboard', null, function (err, payload) {
      if (err || !payload) {
        req('GET', '/api/overview', null, function (legacyErr, legacyPayload) {
          if (legacyErr || !legacyPayload) {
            setText('perfStatsView', 'Failed to load overview/dashboard.');
            setHtml('httpStatsView', '<span class="muted">Failed to load HTTP stats.</span>');
            done(false);
            return;
          }
          renderOverview(legacyPayload);
          reloadUsers();
          req('GET', '/api/display/all?format=json', null, function (_dErr, displayPayload) {
            hydrateDisplaySections(null, !(_dErr || !displayPayload) ? (displayPayload.sections || {}) : null);
          });
          done(true);
        });
        return;
      }
      renderOverview(payload);
      var dashboard = payload.dashboard || {};
      if (dashboard.users && dashboard.users.length != null) {
        renderUsersTable(dashboard.users);
      } else {
        reloadUsers();
      }
      hydrateDisplaySections(dashboard.display_providers || null, dashboard.display_sections || null);
      done(true);
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
    var html = '<div class="plugin-list">';
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      var name = String(it.name || '');
      var mode = String(it.mode || 'manual');
      var mounted = it.mounted ? 'mounted' : 'not-mounted';
      var loaded = it.loaded ? 'loaded' : 'idle';
      var enableBtn = it.enabled
        ? '<button data-plugin-set-enabled="false" data-plugin-name="' + name + '">Disable</button>'
        : '<button class="primary" data-plugin-set-enabled="true" data-plugin-name="' + name + '">Enable</button>';
      html += '<div class="plugin-card">' +
        '<div class="plugin-card-head"><strong>' + name + '</strong><span class="plugin-badge">' + (it.enabled ? 'enabled' : 'disabled') + '</span></div>' +
        '<div class="opt-meta"><span class="plugin-badge">mode=' + mode + '</span><span class="plugin-badge">' + mounted + '</span><span class="plugin-badge">' + loaded + '</span></div>' +
        '<div class="plugin-actions">' +
        enableBtn + ' <button data-plugin-config-open="' + name + '">Config</button> <button data-plugin-visual-open="' + name + '">Visual</button>' +
        '</div>' +
        '</div>';
    }
    html += '</div>';
    view.innerHTML = html;
  }
  function updatePluginConfigPicker(items) {
    var select = byId('pluginConfigName');
    if (!select) { return; }
    var rows = items || [];
    var html = '';
    for (var i = 0; i < rows.length; i++) {
      var name = String((rows[i] || {}).name || '');
      if (!name) { continue; }
      html += '<option value="' + escHtml(name) + '">' + escHtml(name) + '</option>';
    }
    select.innerHTML = html || '<option value="">(no plugins)</option>';
    var cmdSelect = byId('pluginCommandName');
    if (cmdSelect) { cmdSelect.innerHTML = select.innerHTML; }
  }
  function loadPluginControl() {
    req('GET', '/api/plugins', null, function (err, payload) {
      if (err || !payload) {
        setText('pluginItemsView', 'Failed to load plugins: ' + String(err || 'request failed'));
        return;
      }
      renderPluginItems(payload);
      updatePluginConfigPicker(payload.items || []);
      setText('pluginResult', JSON.stringify(payload, null, 2));
      var picker = byId('pluginConfigName');
      var selected = String(picker ? picker.value : '').trim();
      if (!selected) {
        var rows = payload.items || [];
        if (rows.length) { selected = String((rows[0] || {}).name || '').trim(); }
      }
      if (selected) {
        if (picker) { picker.value = selected; }
        var cmdPicker = byId('pluginCommandName');
        if (cmdPicker) { cmdPicker.value = selected; }
        loadPluginConfigSchema(selected);
        loadPluginCommands(selected);
      }
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
  var __pluginOptionDraft = {};
  function renderPluginConfigSchema(payload) {
    var host = byId('pluginConfigSchemaView');
    if (!host) { return; }
    var schema = payload && payload.schema ? payload.schema : {categories: []};
    var cats = schema.categories || [];
    if (!cats.length) {
      host.textContent = 'No plugin config fields available.';
      return;
    }
    var html = '';
    for (var i = 0; i < cats.length; i++) {
      var c = cats[i] || {};
      var fields = c.fields || [];
      html += '<div class="opt-cat"><div class="opt-head">' + escHtml(c.title || c.id || 'Plugin Config') + ' (' + fields.length + ')</div>';
      for (var j = 0; j < fields.length; j++) {
        var f = fields[j] || {};
        var ek = encodeURIComponent(String(f.key || ''));
        html += '<div class="opt-row">' +
          '<div><div><strong>' + escHtml(f.label || f.key || 'field') + '</strong></div><div class="opt-meta">' + escHtml(f.description || '') + '</div><div class="opt-key">' + escHtml(f.key || '') + ' (' + escHtml(f.type || 'json') + ')</div></div>' +
          '<div>' + optionControlHtml(f) + '</div>' +
          '<div><button data-plugin-opt-apply-enc="' + ek + '">Apply</button></div>' +
          '</div>';
      }
      html += '</div>';
    }
    host.innerHTML = html;
    __pluginOptionDraft = {};
    autoSizeAllOptionTextAreas();
  }
  function loadPluginConfigSchema(pluginName) {
    var select = byId('pluginConfigName');
    var name = String(pluginName || (select ? select.value : '') || '').trim();
    if (!name) {
      setText('pluginConfigResult', JSON.stringify({ok: false, error: 'plugin is required'}, null, 2));
      return;
    }
    req('GET', '/api/plugins/config?plugin=' + encodeURIComponent(name) + '&only_writable=1', null, function (err, payload) {
      if (err || !payload) {
        setText('pluginConfigResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
        return;
      }
      renderPluginConfigSchema(payload);
      setText('pluginConfigResult', JSON.stringify(payload, null, 2));
    });
  }
  function openPluginConfig(pluginName) {
    var name = String(pluginName || '').trim();
    if (!name) { return; }
    switchSection('plugins');
    switchPluginPane('config');
    var picker = byId('pluginConfigName');
    if (picker) { picker.value = name; }
    setText('pluginConfigResult', 'Loading plugin config: ' + name + ' ...');
    loadPluginConfigSchema(name);
    loadPluginCommands(name);
    var panel = byId('pluginConfigSchemaView');
    if (panel && panel.scrollIntoView) {
      panel.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }
  function openPluginVisual(pluginName) {
    var name = String(pluginName || '').trim();
    if (!name) { return; }
    switchSection('plugins');
    switchPluginPane('visual');
    var picker = byId('pluginConfigName');
    if (picker) { picker.value = name; }
    var cmdPicker = byId('pluginCommandName');
    if (cmdPicker) { cmdPicker.value = name; }
    loadPluginCommands(name);
    loadPluginVisualSchema(name);
  }
  function parsePluginCmdArgs(raw) {
    var text = String(raw || '').trim();
    if (!text) { return []; }
    if (text.charAt(0) === '[') {
      try {
        var arr = JSON.parse(text);
        return Array.isArray(arr) ? arr : [];
      } catch (_e) {
        return [];
      }
    }
    return text.split(/\s+/).filter(function (x) { return !!x; });
  }
  function renderPluginCommands(plugin, commands) {
    var host = byId('pluginCommandListView');
    if (!host) { return; }
    var rows = commands || [];
    if (!rows.length) {
      host.innerHTML = '<span class="muted">No commands found for plugin: ' + escHtml(plugin || '') + '</span>';
      return;
    }
    var html = '';
    for (var i = 0; i < rows.length; i++) {
      var it = rows[i] || {};
      var name = String(it.name || '');
      var desc = String(it.description || '');
      html += '<div class="plugin-command-row">' +
        '<div><strong>' + escHtml(name) + '</strong><div class="opt-meta">' + escHtml(desc || 'No description') + '</div></div>' +
        '<div><button data-plugin-cmd-run="' + escHtml(name) + '">Run</button></div>' +
        '</div>';
    }
    host.innerHTML = html;
  }
  function loadPluginCommands(pluginName) {
    var select = byId('pluginCommandName');
    var name = String(pluginName || (select ? select.value : '') || '').trim();
    if (!name) {
      setText('pluginCommandResult', JSON.stringify({ok: false, error: 'plugin is required'}, null, 2));
      return;
    }
    req('GET', '/api/plugins/commands?plugin=' + encodeURIComponent(name), null, function (err, payload) {
      if (err || !payload) {
        setText('pluginCommandResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
        return;
      }
      renderPluginCommands(name, payload.commands || []);
      setText('pluginCommandResult', JSON.stringify(payload, null, 2));
      loadPluginVisualSchema(name);
    });
  }
  function visualFieldControl(plugin, cmdName, field, idx) {
    var f = field || {};
    var fType = String(f.type || 'str').toLowerCase();
    var fName = String(f.name || '');
    var key = escHtml(String(plugin + '|' + cmdName + '|' + idx));
    var val = f.default == null ? '' : String(f.default);
    
    if (fType === 'bool') {
      var isChecked = val === 'true' || val === true || val === 1 || val === '1';
      return '<input type="checkbox" ' + (isChecked ? 'checked' : '') + ' data-vf-key="' + key + '" data-vf-name="' + escHtml(fName) + '" data-vf-type="' + escHtml(fType) + '" style="height:auto;width:auto;">';
    }
    
    if (fType === 'select') {
      var options = '';
      var choices = Array.isArray(f.choices) ? f.choices : [];
      for (var i = 0; i < choices.length; i++) {
        var ch = String(choices[i]);
        options += '<option value="' + escHtml(ch) + '" ' + (ch === val ? 'selected' : '') + '>' + escHtml(ch) + '</option>';
      }
      return '<select data-vf-key="' + key + '" data-vf-name="' + escHtml(fName) + '" data-vf-type="' + escHtml(fType) + '">' + options + '</select>';
    }
    var inputType = (fType === 'int' || fType === 'float') ? 'number' : 'text';
    return '<input type="' + inputType + '" value="' + escHtml(val) + '" data-vf-key="' + key + '" data-vf-name="' + escHtml(fName) + '" data-vf-type="' + escHtml(fType) + '">';
  }
  function visualPresetStorageKey(plugin, cmd) {
    return 'os_web_plugin_preset_' + String(plugin || '') + '__' + String(cmd || '');
  }
  function listVisualPresets(plugin, cmd) {
    try {
      var raw = window.localStorage.getItem(visualPresetStorageKey(plugin, cmd));
      var parsed = JSON.parse(String(raw || '[]'));
      return Array.isArray(parsed) ? parsed : [];
    } catch (_e) {
      return [];
    }
  }
  function saveVisualPreset(plugin, cmd, name, args) {
    var title = String(name || '').trim();
    if (!title) { return {ok: false, error: 'preset name required'}; }
    var rows = listVisualPresets(plugin, cmd);
    var filtered = [];
    for (var i = 0; i < rows.length; i++) {
      var it = rows[i] || {};
      if (String(it.name || '') !== title) { filtered.push(it); }
    }
    // Clean up args: remove any standalone "false" values that shouldn't be there
    var cleanedArgs = [];
    for (var i = 0; i < args.length; i++) {
      var arg = String(args[i] || '').trim();
      if (arg && (arg === 'false' || arg === 'true')) {
        // Skip boolean literal values that shouldn't be in args
        continue;
      }
      if (arg.indexOf('--') === 0) {
        // This is a flag - check if next item is "false"
        if (i + 1 < args.length) {
          var nxt = String(args[i + 1] || '').trim();
          if (nxt === 'false') {
            // Skip the "false" value and skip this flag too
            i += 1;
            continue;
          }
        }
        cleanedArgs.push(arg);
      } else {
        // Regular value
        cleanedArgs.push(arg);
      }
    }
    filtered.push({name: title, args: cleanedArgs});
    try {
      window.localStorage.setItem(visualPresetStorageKey(plugin, cmd), JSON.stringify(filtered));
      return {ok: true};
    } catch (e) {
      return {ok: false, error: String(e)};
    }
  }
  function deleteVisualPreset(plugin, cmd, name) {
    var title = String(name || '').trim();
    var rows = listVisualPresets(plugin, cmd);
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var it = rows[i] || {};
      if (String(it.name || '') !== title) { out.push(it); }
    }
    try {
      window.localStorage.setItem(visualPresetStorageKey(plugin, cmd), JSON.stringify(out));
      return {ok: true};
    } catch (e) {
      return {ok: false, error: String(e)};
    }
  }
  function renderPresetControls(plugin, cmd) {
    var presets = listVisualPresets(plugin, cmd);
    var options = '<option value="">(preset)</option>';
    for (var i = 0; i < presets.length; i++) {
      var it = presets[i] || {};
      var name = String(it.name || '').trim();
      if (!name) { continue; }
      options += '<option value="' + escHtml(name) + '">' + escHtml(name) + '</option>';
    }
    return '' +
      '<div class="visual-preset-row">' +
      '<select data-visual-preset-select="' + escHtml(plugin + '|' + cmd) + '">' + options + '</select>' +
      '<input data-visual-preset-name="' + escHtml(plugin + '|' + cmd) + '" placeholder="Preset name">' +
      '<button data-visual-preset-save="' + escHtml(plugin) + '" data-visual-preset-cmd="' + escHtml(cmd) + '">Save</button>' +
      '<button data-visual-preset-load="' + escHtml(plugin) + '" data-visual-preset-cmd="' + escHtml(cmd) + '">Load</button>' +
      '<button data-visual-preset-delete="' + escHtml(plugin) + '" data-visual-preset-cmd="' + escHtml(cmd) + '">Delete</button>' +
      '</div>';
  }
  function renderPluginVisualActions(plugin, schema) {
    var host = byId('pluginVisualActionsView');
    if (!host) { return; }
    var sections = schema && schema.sections ? schema.sections : [];
    if (!sections.length) {
      host.innerHTML = '<span class="muted">No visual actions for plugin: ' + escHtml(plugin || '') + '</span>';
      return;
    }
    var html = '';
    __visualCommandOptionMap = {};
    __visualCommandFieldsMap = {};
    for (var i = 0; i < sections.length; i++) {
      var sec = sections[i] || {};
      var cmds = sec.commands || [];
      html += '<div class="opt-cat"><div class="opt-head">' + escHtml(sec.title || sec.id || 'Section') + '</div>';
      for (var j = 0; j < cmds.length; j++) {
        var cmd = cmds[j] || {};
        var cName = String(cmd.name || '');
        var fields = cmd.fields || [];
        var advanced = cmd.advanced_fields || [];
        var key = String(plugin + '|' + cName);
        var known = [];
        for (var a = 0; a < fields.length; a++) {
          var f0 = fields[a] || {};
          if (f0.name) { known.push(String(f0.name)); }
        }
        for (var b = 0; b < advanced.length; b++) {
          var f1 = advanced[b] || {};
          if (f1.name && known.indexOf(String(f1.name)) < 0) { known.push(String(f1.name)); }
        }
        var extras = Array.isArray(cmd.extra_options) ? cmd.extra_options : [];
        for (var c = 0; c < extras.length; c++) {
          var opt = String(extras[c] || '').trim();
          if (opt && known.indexOf(opt) < 0) { known.push(opt); }
        }
        __visualCommandOptionMap[key] = known;
        __visualCommandFieldsMap[key] = known.slice(0);
        var fieldsHtml = '';
        for (var k = 0; k < fields.length; k++) {
          var field = fields[k] || {};
          fieldsHtml += '<div class="visual-field-grid"><span class="muted">' + escHtml(field.name || 'arg') + '</span>' + visualFieldControl(plugin, cName, field, k) + '</div>';
        }
        var advancedHtml = '';
        if (advanced.length) {
          var advRows = '';
          for (var m = 0; m < advanced.length; m++) {
            var advField = advanced[m] || {};
            advRows += '<div class="visual-field-grid"><span class="muted">' + escHtml(advField.name || 'arg') + '</span>' + visualFieldControl(plugin, cName, advField, fields.length + m) + '</div>';
          }
          advancedHtml = '<details><summary>Advanced</summary>' + advRows + '</details>';
        }
        html += '<div class="visual-command-card">' +
          '<div class="display-title">' + escHtml(cmd.label || cName) + '</div>' +
          '<div class="opt-meta">' + escHtml(cmd.description || '') + '</div>' +
          (fieldsHtml || '<div class="opt-meta">No additional fields</div>') +
          advancedHtml +
          renderPresetControls(plugin, cName) +
          '<div class="visual-extra-list" data-visual-extra-list="' + escHtml(plugin + '|' + cName) + '"></div>' +
          '<div class="visual-action-bar"><button data-visual-add-plugin="' + escHtml(plugin) + '" data-visual-add-cmd="' + escHtml(cName) + '">New Param</button> <button data-visual-run-plugin="' + escHtml(plugin) + '" data-visual-run-cmd="' + escHtml(cName) + '">Run</button></div>' +
          '</div>';
      }
      html += '</div>';
    }
    host.innerHTML = html;
  }
  function appendVisualExtraArgRow(host, plugin, cmd, keyValue, rawValue) {
    if (!host) { return; }
    var key = String(plugin + '|' + cmd);
    var list = host.querySelector('[data-visual-extra-list="' + key + '"]');
    if (!list) { return; }
    var options = __visualCommandOptionMap[key] || [];
    var optionsHtml = '<option value="">--arg-name</option>';
    for (var i = 0; i < options.length; i++) {
      var token = String(options[i] || '').trim();
      if (!token) { continue; }
      optionsHtml += '<option value="' + escHtml(token) + '" ' + (token === String(keyValue || '') ? 'selected' : '') + '>' + escHtml(token) + '</option>';
    }
    var row = document.createElement('div');
    row.className = 'visual-extra-row';
    row.innerHTML = '' +
      '<select data-visual-extra-name="1" data-visual-extra-plugin="' + escHtml(plugin) + '" data-visual-extra-cmd="' + escHtml(cmd) + '">' + optionsHtml + '</select>' +
      '<input data-visual-extra-value="1" data-visual-extra-plugin="' + escHtml(plugin) + '" data-visual-extra-cmd="' + escHtml(cmd) + '" placeholder="value" value="' + escHtml(rawValue || '') + '">' +
      '<button data-visual-remove-extra="1">Remove</button>';
    list.appendChild(row);
  }
  function parseVisualArgs(host, plugin, cmd) {
    var args = [];
    if (!host) { return args; }
    var keyPrefix = String(plugin + '|' + cmd + '|');
    var inputs = host.querySelectorAll('[data-vf-key]');
    for (var i = 0; i < inputs.length; i++) {
      var node = inputs[i];
      var key = String(node.getAttribute('data-vf-key') || '');
      if (key.indexOf(keyPrefix) !== 0) { continue; }
      var argName = String(node.getAttribute('data-vf-name') || '').trim();
      var typ = String(node.getAttribute('data-vf-type') || 'str').trim();
      
      if (typ === 'bool') {
        // For boolean flags, only include the flag if checkbox is checked
        if (node.checked) {
          args.push(argName);
        }
      } else {
        var raw = String(node.value || '').trim();
        if (!argName || !raw) { continue; }
        args.push(argName);
        if (typ === 'int') { args.push(String(parseInt(raw, 10))); }
        else if (typ === 'float') { args.push(String(parseFloat(raw))); }
        else { args.push(raw); }
      }
    }
    var extraNames = host.querySelectorAll('[data-visual-extra-name="1"][data-visual-extra-plugin="' + plugin + '"][data-visual-extra-cmd="' + cmd + '"]');
    for (var j = 0; j < extraNames.length; j++) {
      var nameNode = extraNames[j];
      var valueNode = null;
      var row = nameNode.parentNode;
      if (row && row.querySelector) {
        valueNode = row.querySelector('[data-visual-extra-value="1"]');
      }
      var argName = String(nameNode.value || '').trim();
      if (!argName) { continue; }
      args.push(argName);
      var argValue = String(valueNode && valueNode.value != null ? valueNode.value : '').trim();
      // Skip if value is empty or literally "false" (likely user error)
      if (argValue && argValue.toLowerCase() !== 'false') { 
        args.push(argValue); 
      }
    }
    return args;
  }
  function loadPluginVisualSchema(pluginName) {
    var select = byId('pluginCommandName');
    var name = String(pluginName || (select ? select.value : '') || '').trim();
    if (!name) {
      setText('pluginVisualResult', JSON.stringify({ok: false, error: 'plugin is required'}, null, 2));
      return;
    }
    req('GET', '/api/plugins/visual-schema?plugin=' + encodeURIComponent(name), null, function (err, payload) {
      if (err || !payload) {
        setText('pluginVisualResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
        return;
      }
      renderPluginVisualActions(name, payload);
      setText('pluginVisualResult', JSON.stringify(payload, null, 2));
    });
  }
  function runPluginVisualAction(plugin, cmd) {
    var host = byId('pluginVisualActionsView');
    var args = parseVisualArgs(host, String(plugin || ''), String(cmd || ''));
    runPluginCommand(plugin, cmd, args);
  }
  function applyVisualPreset(host, plugin, cmd, presetArgs) {
    var key = String(plugin + '|' + cmd);
    var tokens = Array.isArray(presetArgs) ? presetArgs : [];
    var fieldNodes = host.querySelectorAll('[data-vf-key]');
    for (var i = 0; i < fieldNodes.length; i++) {
      var n = fieldNodes[i];
      var argName = String(n.getAttribute('data-vf-name') || '');
      if (!argName) { continue; }
      var typ = String(n.getAttribute('data-vf-type') || 'str');
      if (typ === 'bool') {
        n.checked = false;
      } else {
        n.value = '';
      }
    }
    var list = host.querySelector('[data-visual-extra-list="' + key + '"]');
    if (list) { list.innerHTML = ''; }
    for (var j = 0; j < tokens.length; j++) {
      var token = String(tokens[j] || '').trim();
      if (!token || token.indexOf('--') !== 0) { continue; }
      var val = '';
      if (j + 1 < tokens.length) {
        var nxt = String(tokens[j + 1] || '');
        if (nxt.indexOf('--') !== 0) { val = nxt; j += 1; }
      }
      var target = null;
      for (var k = 0; k < fieldNodes.length; k++) {
        var node = fieldNodes[k];
        if (String(node.getAttribute('data-vf-name') || '') === token) { target = node; break; }
      }
      if (target) {
        var targetType = String(target.getAttribute('data-vf-type') || 'str');
        if (targetType === 'bool') {
          // For boolean flags, just set checked if token is present (presence = true)
          target.checked = true;
        } else {
          target.value = val;
        }
      } else {
        appendVisualExtraArgRow(host, plugin, cmd, token, val);
      }
    }
  }
  function runPluginCommand(pluginName, cmdName) {
    var plugin = String(pluginName || '').trim();
    var cmd = String(cmdName || '').trim();
    var explicitArgs = arguments.length > 2 ? arguments[2] : null;
    if (!plugin || !cmd) {
      setText('pluginCommandResult', JSON.stringify({ok: false, error: 'plugin/cmd required'}, null, 2));
      return;
    }
    var argsEl = byId('pluginCommandArgs');
    var args = Array.isArray(explicitArgs) ? explicitArgs : parsePluginCmdArgs(argsEl ? argsEl.value : '');
    setText('pluginCommandResult', 'Running ' + plugin + ' ' + cmd + ' ...');
    req('POST', '/api/plugins', {plugin: plugin, action: 'cmd', sub_cmd: cmd, args: args}, function (err, payload) {
      var out = payload || {ok: false, error: String(err || 'request failed')};
      setText('pluginCommandResult', JSON.stringify(out, null, 2));
      if (out && out.ok) { setBanner('ok', 'Command finished: ' + plugin + ' ' + cmd); }
      else { setBanner('bad', 'Command failed: ' + plugin + ' ' + cmd); }
    });
  }
  function applyPluginConfigChanges() {
    var select = byId('pluginConfigName');
    var name = String(select ? select.value : '').trim();
    if (!name) {
      setText('pluginConfigResult', JSON.stringify({ok: false, error: 'plugin is required'}, null, 2));
      return;
    }
    var updates = [];
    for (var key in __pluginOptionDraft) {
      if (!Object.prototype.hasOwnProperty.call(__pluginOptionDraft, key)) { continue; }
      var it = __pluginOptionDraft[key];
      try {
        updates.push({key: it.key, value_type: it.value_type, value: parseOptionValue(it.raw_value, it.value_type)});
      } catch (e) {
        setText('pluginConfigResult', JSON.stringify({ok: false, key: it.key, error: String(e)}, null, 2));
        return;
      }
    }
    if (!updates.length) {
      setText('pluginConfigResult', JSON.stringify({ok: true, changed: [], info: 'no plugin config changes'}, null, 2));
      return;
    }
    req('PUT', '/api/plugins/config', {plugin: name, updates: updates}, function (err, payload) {
      var out = payload || {ok: false, error: String(err || 'request failed')};
      setText('pluginConfigResult', JSON.stringify(out, null, 2));
      if (out && out.ok) {
        __pluginOptionDraft = {};
        setBanner('ok', 'Plugin config updated: ' + name);
        loadPluginConfigSchema(name);
      } else {
        setBanner('bad', 'Plugin config update failed: ' + name);
      }
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
  function optionShortcutHtml(f) {
    var key = String((f && f.key) || '');
    var value = f ? f.value : null;
    if (!Array.isArray(value) || !value.length) { return ''; }
    if (key.indexOf('.expose_sections') >= 0) {
      var parts = '';
      for (var i = 0; i < value.length; i++) {
        var sec = String(value[i] || '').trim();
        if (!sec) { continue; }
        parts += '<button data-jump-section="' + esc(sec) + '">' + esc(sec) + '</button> ';
      }
      return parts ? '<div class="row"><span class="muted">Jump to section:</span>' + parts + '</div>' : '';
    }
    if (key.indexOf('.writable_config_prefixes') >= 0) {
      var rows = '';
      for (var j = 0; j < value.length; j++) {
        var prefix = String(value[j] || '').trim();
        if (!prefix) { continue; }
        rows += '<button data-jump-prefix="' + esc(prefix) + '">' + esc(prefix) + '</button> ';
      }
      return rows ? '<div class="row"><span class="muted">Quick open key prefix:</span>' + rows + '</div>' : '';
    }
    return '';
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
          '<div>' + optionControlHtml(f) + optionShortcutHtml(f) + '</div>' +
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
    wire('jsonToggleBtn', toggleJsonMode);
    wire('selfCheckBtn', runSelfCheck);
    wire('pluginRunBtn', loadPluginControl);
    wire('pluginConfigLoadBtn', function () { loadPluginConfigSchema(); });
    wire('pluginConfigApplyBtn', applyPluginConfigChanges);
    wire('pluginCommandLoadBtn', function () { loadPluginCommands(); });
    var cfgSelect = byId('pluginConfigName');
    var cmdSelect = byId('pluginCommandName');
    if (cfgSelect) {
      cfgSelect.addEventListener('change', function () {
        var v = String(cfgSelect.value || '').trim();
        if (cmdSelect) { cmdSelect.value = v; }
        if (v) {
          loadPluginConfigSchema(v);
          loadPluginCommands(v);
        }
      });
    }
    if (cmdSelect) {
      cmdSelect.addEventListener('change', function () {
        var v = String(cmdSelect.value || '').trim();
        if (cfgSelect) { cfgSelect.value = v; }
        if (v) {
          loadPluginCommands(v);
          loadPluginConfigSchema(v);
        }
      });
    }
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
        var cfgName = t.getAttribute('data-plugin-config-open');
        if (cfgName) { openPluginConfig(cfgName); return; }
        var visName = t.getAttribute('data-plugin-visual-open');
        if (visName) { openPluginVisual(visName); return; }
        var name = t.getAttribute('data-plugin-name') || t.getAttribute('data-plugin-apply');
        if (!name) { return; }
        var enabledAttr = t.getAttribute('data-plugin-set-enabled');
        var enabled = enabledAttr == null ? true : String(enabledAttr) === 'true';
        var btn = t;
        setButtonBusy(btn, true, 'Applying...');
        setText('pluginResult', 'Applying plugin: ' + name + '...');
        setPluginEnabled(name, enabled, function (result) {
          setButtonBusy(btn, false);
          flashButtonState(btn, result && result.ok ? 'btn-success' : 'btn-fail');
        });
      });
    }
    var pconf = byId('pluginConfigSchemaView');
    if (pconf) {
      pconf.addEventListener('input', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var ek = t.getAttribute('data-opt-key-enc');
        var tp = t.getAttribute('data-opt-type') || 'json';
        if (!ek) { return; }
        __pluginOptionDraft[ek] = {key: decodeURIComponent(ek), value_type: tp, raw_value: t.value};
        autoSizeOptionTextArea(t);
      });
      pconf.addEventListener('change', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var ek = t.getAttribute('data-opt-key-enc');
        var tp = t.getAttribute('data-opt-type') || 'json';
        if (!ek) { return; }
        __pluginOptionDraft[ek] = {key: decodeURIComponent(ek), value_type: tp, raw_value: t.value};
        autoSizeOptionTextArea(t);
      });
      pconf.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var ak = t.getAttribute('data-plugin-opt-apply-enc');
        if (!ak) { return; }
        var q = pconf.querySelector('[data-opt-key-enc="' + ak + '"]');
        if (!q) { return; }
        var tp = q.getAttribute('data-opt-type') || 'json';
        var select = byId('pluginConfigName');
        var plugin = String(select ? select.value : '').trim();
        if (!plugin) {
          setText('pluginConfigResult', JSON.stringify({ok: false, error: 'plugin is required'}, null, 2));
          return;
        }
        var upd = null;
        try {
          upd = {key: decodeURIComponent(ak), value_type: tp, value: parseOptionValue(q.value, tp)};
        } catch (e) {
          setText('pluginConfigResult', JSON.stringify({ok: false, error: String(e)}, null, 2));
          return;
        }
        req('PUT', '/api/plugins/config', {plugin: plugin, updates: [upd]}, function (err, payload) {
          var out = payload || {ok: false, error: String(err || 'request failed')};
          setText('pluginConfigResult', JSON.stringify(out, null, 2));
          if (out && out.ok) {
            setBanner('ok', 'Plugin config updated: ' + plugin);
            loadPluginConfigSchema(plugin);
          } else {
            setBanner('bad', 'Plugin config update failed: ' + plugin);
          }
        });
      });
    }
    var pcmd = byId('pluginCommandListView');
    if (pcmd) {
      pcmd.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var cmd = t.getAttribute('data-plugin-cmd-run');
        if (!cmd) { return; }
        var select = byId('pluginCommandName');
        var plugin = String(select ? select.value : '').trim();
        runPluginCommand(plugin, cmd);
      });
    }
    var pvisual = byId('pluginVisualActionsView');
    if (pvisual) {
      pvisual.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var psPlugin = t.getAttribute('data-visual-preset-save');
        var psCmd = t.getAttribute('data-visual-preset-cmd');
        if (psPlugin && psCmd) {
          var argsForSave = parseVisualArgs(pvisual, psPlugin, psCmd);
          var nameInput = pvisual.querySelector('[data-visual-preset-name="' + psPlugin + '|' + psCmd + '"]');
          var presetName = String(nameInput && nameInput.value ? nameInput.value : '').trim();
          var sv = saveVisualPreset(psPlugin, psCmd, presetName, argsForSave);
          if (!sv.ok) {
            setText('pluginVisualResult', JSON.stringify(sv, null, 2));
            return;
          }
          loadPluginVisualSchema(psPlugin);
          setText('pluginVisualResult', JSON.stringify({ok: true, plugin: psPlugin, command: psCmd, preset: presetName}, null, 2));
          return;
        }
        var plPlugin = t.getAttribute('data-visual-preset-load');
        var plCmd = t.getAttribute('data-visual-preset-cmd');
        if (plPlugin && plCmd) {
          var select = pvisual.querySelector('[data-visual-preset-select="' + plPlugin + '|' + plCmd + '"]');
          var targetName = String(select && select.value ? select.value : '').trim();
          if (!targetName) { return; }
          var rows = listVisualPresets(plPlugin, plCmd);
          var match = null;
          for (var i = 0; i < rows.length; i++) {
            if (String((rows[i] || {}).name || '') === targetName) { match = rows[i]; break; }
          }
          if (!match) { return; }
          applyVisualPreset(pvisual, plPlugin, plCmd, match.args || []);
          setText('pluginVisualResult', JSON.stringify({ok: true, plugin: plPlugin, command: plCmd, preset: targetName, loaded: true}, null, 2));
          return;
        }
        var pdPlugin = t.getAttribute('data-visual-preset-delete');
        var pdCmd = t.getAttribute('data-visual-preset-cmd');
        if (pdPlugin && pdCmd) {
          var sel = pvisual.querySelector('[data-visual-preset-select="' + pdPlugin + '|' + pdCmd + '"]');
          var delName = String(sel && sel.value ? sel.value : '').trim();
          if (!delName) { return; }
          var dv = deleteVisualPreset(pdPlugin, pdCmd, delName);
          if (!dv.ok) {
            setText('pluginVisualResult', JSON.stringify(dv, null, 2));
            return;
          }
          loadPluginVisualSchema(pdPlugin);
          setText('pluginVisualResult', JSON.stringify({ok: true, plugin: pdPlugin, command: pdCmd, preset: delName, deleted: true}, null, 2));
          return;
        }
        var addPlugin = t.getAttribute('data-visual-add-plugin');
        var addCmd = t.getAttribute('data-visual-add-cmd');
        if (addPlugin && addCmd) {
          appendVisualExtraArgRow(pvisual, addPlugin, addCmd, '', '');
          return;
        }
        var removeExtra = t.getAttribute('data-visual-remove-extra');
        if (removeExtra) {
          var row = t.parentNode;
          if (row && row.parentNode) { row.parentNode.removeChild(row); }
          return;
        }
        var plugin = t.getAttribute('data-visual-run-plugin');
        var cmd = t.getAttribute('data-visual-run-cmd');
        if (!plugin || !cmd) { return; }
        runPluginVisualAction(plugin, cmd);
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
        var jumpSection = t.getAttribute('data-jump-section');
        if (jumpSection) {
          switchSection(jumpSection);
          return;
        }
        var jumpPrefix = t.getAttribute('data-jump-prefix');
        if (jumpPrefix) {
          switchSection('config');
          var keyInput = byId('cfgKey');
          if (keyInput) { keyInput.value = String(jumpPrefix); }
          return;
        }
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
  window.switchPluginPane = window.switchPluginPane || switchPluginPane;
  window.reloadUsers = window.reloadUsers || reloadUsers;
  window.loadUiOptions = window.loadUiOptions || loadUiOptions;
  window.saveUiOptions = window.saveUiOptions || saveUiOptions;
  window.toggleFullCmdOutput = window.toggleFullCmdOutput || toggleFullCmdOutput;
  window.setCmd = window.setCmd || setCmd;
  window.runCommandLine = window.runCommandLine || runCommandLine;
  window.loadCommandHelp = window.loadCommandHelp || loadCommandHelp;
  window.loadPluginControl = window.loadPluginControl || loadPluginControl;
  window.setPluginEnabled = window.setPluginEnabled || setPluginEnabled;
  window.loadPluginConfigSchema = window.loadPluginConfigSchema || loadPluginConfigSchema;
  window.applyPluginConfigChanges = window.applyPluginConfigChanges || applyPluginConfigChanges;
  window.openPluginConfig = window.openPluginConfig || openPluginConfig;
  window.openPluginVisual = window.openPluginVisual || openPluginVisual;
  window.loadPluginCommands = window.loadPluginCommands || loadPluginCommands;
  window.runPluginCommand = window.runPluginCommand || runPluginCommand;
  window.loadPluginVisualSchema = window.loadPluginVisualSchema || loadPluginVisualSchema;
  window.runPluginVisualAction = window.runPluginVisualAction || runPluginVisualAction;
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
  window.toggleJsonMode = window.toggleJsonMode || toggleJsonMode;
  window.__OS_WEB_RUNTIME_LOADED = true;
  
  // Clean up any corrupted visual presets from localStorage
  function cleanupVisualPresets() {
    try {
      for (var i = 0; i < window.localStorage.length; i++) {
        var key = window.localStorage.key(i);
        if (key && key.indexOf('os_web_plugin_preset_') === 0) {
          var val = window.localStorage.getItem(key);
          var parsed = JSON.parse(val);
          if (Array.isArray(parsed)) {
            var cleaned = false;
            for (var j = 0; j < parsed.length; j++) {
              var preset = parsed[j] || {};
              var args = preset.args || [];
              // Check for and remove "false" values from args
              for (var k = 0; k < args.length; k++) {
                if (String(args[k]).trim() === 'false') {
                  args.splice(k, 1);
                  cleaned = true;
                  k--;
                }
              }
            }
            if (cleaned) {
              window.localStorage.setItem(key, JSON.stringify(parsed));
            }
          }
        }
      }
    } catch (e) {
      // Silently ignore cleanup errors
    }
  }
  cleanupVisualPresets();
  
  initJsonMode();
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
