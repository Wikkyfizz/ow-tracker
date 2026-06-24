// ── State ─────────────────────────────────────────────────────────────────────
let heroes = [], maps = [];
let mySelectedHeroes = [];   // [{hero, pct}]
let enemySelectedHeroes = [];
let selectedBans = [];
let srChart = null, mapChart = null;
const PCT_CYCLE = [100, 75, 50, 25];
let baselineData = [];
let baselineSortCol = 'playtime_pct';
let baselineSortDir = 'desc';

// ── API ───────────────────────────────────────────────────────────────────────
const api = {
  get: (url) => fetch(url).then(r => r.json()),
  post: (url, body) => fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r => r.json()),
  put: (url, body) => fetch(url, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r => r.json()),
  delete: (url) => fetch(url, {method:'DELETE'}).then(r => r.json()),
};

// ── Nav ───────────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn[data-page]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn[data-page]').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-' + btn.dataset.page).classList.add('active');
    onPageEnter(btn.dataset.page);
  });
});

function onPageEnter(page) {
  if (page === 'dashboard') loadDashboard();
  if (page === 'history') loadHistory();
  if (page === 'analytics') loadAnalyticsTab('a-heroes');
  if (page === 'queue') loadQueue();
  if (page === 'settings') loadSettings();
}

// ── Tab bars inside pages ─────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
  btn.addEventListener('click', () => {
    const parent = btn.closest('.page');
    parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    parent.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
    loadAnalyticsTab(btn.dataset.tab);
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function wrClass(wr) {
  if (wr >= 0.55) return 'wr-good';
  if (wr >= 0.45) return 'wr-mid';
  return 'wr-bad';
}
function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
function wrBar(wr) { return `<span class="wr-bar" style="width:${(wr*60).toFixed(0)}px"></span>`; }
function numFmt(n) { if (n == null) return '—'; return n >= 1000 ? (n/1000).toFixed(1)+'k' : n; }

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  [heroes, maps] = await Promise.all([api.get('/api/heroes'), api.get('/api/maps')]);
  populateMapSelects();
  buildHeroLists();
  populateHeroFilter();
  loadDashboard();
  checkQueue();
  setInterval(checkQueue, 10000);
}

function populateMapSelects() {
  const sel = document.getElementById('f-map');
  sel.innerHTML = '<option value="">Select map…</option>';
  const hFilter = document.getElementById('h-map-filter');
  hFilter.innerHTML = '<option value="">All Maps</option>';
  const grouped = {};
  maps.forEach(m => {
    if (!grouped[m.game_mode]) grouped[m.game_mode] = [];
    grouped[m.game_mode].push(m);
  });
  Object.entries(grouped).forEach(([mode, mps]) => {
    const og = document.createElement('optgroup');
    og.label = mode;
    mps.forEach(m => { const o = document.createElement('option'); o.value = m.name; o.textContent = m.name; og.appendChild(o); });
    sel.appendChild(og.cloneNode(true));
    const og2 = og.cloneNode(true);
    hFilter.appendChild(og2);
  });
}

function populateHeroFilter() {
  const sel = document.getElementById('h-hero-filter');
  sel.innerHTML = '<option value="">All Heroes</option>';
  [...new Set(heroes.map(h => h.name))].sort().forEach(n => {
    const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o);
  });
}

function buildHeroLists() {
  renderHeroChipList('f-my-heroes', mySelectedHeroes, 'my');
  renderHeroChipList('f-enemy-heroes', enemySelectedHeroes, 'enemy');
  renderBanChips();
}

function renderHeroChipList(containerId, selectedArr, side) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  heroes.forEach(h => {
    const selected = selectedArr.find(e => e.hero === h.name);
    const chip = document.createElement('div');
    chip.className = 'hero-chip' + (selected ? ' selected' : '');
    chip.dataset.hero = h.name;
    chip.title = `${h.role} • ${h.sub_role} • ${h.primary_archetype}`;

    const label = document.createElement('span');
    label.textContent = h.name;

    const pctBadge = document.createElement('span');
    pctBadge.className = 'pct-badge';
    pctBadge.textContent = selected ? selected.pct + '%' : '100%';

    chip.appendChild(label);
    chip.appendChild(pctBadge);

    chip.addEventListener('click', (e) => {
      if (e.target === pctBadge && selectedArr.find(e => e.hero === h.name)) {
        // cycle pct
        const entry = selectedArr.find(e => e.hero === h.name);
        const idx = PCT_CYCLE.indexOf(entry.pct);
        entry.pct = PCT_CYCLE[(idx + 1) % PCT_CYCLE.length];
        pctBadge.textContent = entry.pct + '%';
      } else {
        // toggle selection
        const idx = selectedArr.findIndex(e => e.hero === h.name);
        if (idx >= 0) {
          selectedArr.splice(idx, 1);
          chip.classList.remove('selected');
        } else {
          selectedArr.push({hero: h.name, pct: 100});
          chip.classList.add('selected');
          pctBadge.textContent = '100%';
        }
      }
    });

    container.appendChild(chip);
  });
}

function renderBanChips() {
  const container = document.getElementById('f-bans');
  container.innerHTML = '';
  heroes.forEach(h => {
    const selected = selectedBans.includes(h.name);
    const chip = document.createElement('div');
    chip.className = 'hero-chip' + (selected ? ' selected' : '');
    chip.textContent = h.name;
    chip.addEventListener('click', () => {
      const idx = selectedBans.indexOf(h.name);
      if (idx >= 0) {
        selectedBans.splice(idx, 1);
        chip.classList.remove('selected');
      } else if (selectedBans.length < 5) {
        selectedBans.push(h.name);
        chip.classList.add('selected');
      }
    });
    container.appendChild(chip);
  });
}

// ── DASHBOARD ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  const [dash, sr, mapWr, heroWr, baseline] = await Promise.all([
    api.get('/api/analytics/dashboard'),
    api.get('/api/analytics/sr-timeline'),
    api.get('/api/analytics/map-winrates'),
    api.get('/api/analytics/hero-winrates'),
    api.get('/api/baseline'),
  ]);

  const total = dash.total || 0;
  document.getElementById('d-total').textContent = total;

  const wrEl = document.getElementById('d-wr');
  const wrVal = total ? dash.win_rate : null;
  wrEl.textContent = pct(wrVal);
  wrEl.className = 'value ' + (wrVal ? wrClass(wrVal) : '');
  document.getElementById('d-wr-sub').textContent = total ? `${dash.wins} W` : '';

  const wr20El = document.getElementById('d-wr20');
  wr20El.textContent = pct(dash.win_rate_last20 || null);
  wr20El.className = 'value ' + (dash.win_rate_last20 ? wrClass(dash.win_rate_last20) : '');

  const streakEl = document.getElementById('d-streak');
  if (dash.streak > 0) {
    streakEl.textContent = `${dash.streak} ${dash.streak_type}`;
    streakEl.className = 'value ' + (dash.streak_type === 'Win' ? 'wr-good' : 'wr-bad');
  } else {
    streakEl.textContent = '—';
  }

  document.getElementById('d-hero').textContent = dash.best_hero || '—';
  document.getElementById('d-map').textContent = dash.best_map || '—';

  renderRanks(dash.ranks || []);
  renderSrChart(sr);
  renderMapChart(mapWr.slice(0, 8));
  renderHeroWrTable(heroWr.slice(0, 15));
  renderBaselineTable(baseline);
}

function renderSrChart(data) {
  const ctx = document.getElementById('sr-chart').getContext('2d');
  if (srChart) srChart.destroy();
  if (!data.length) return;
  srChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map((_, i) => i + 1),
      datasets: [{
        data: data.map(d => d.rank_score),
        borderColor: '#f97316',
        backgroundColor: 'rgba(249,115,22,.1)',
        pointRadius: 2,
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {legend:{display:false}, tooltip:{callbacks:{label: ctx => {
        const d = data[ctx.dataIndex];
        return `${d.rank_tier} ${d.rank_division} — ${d.map} (${d.outcome})`;
      }}}},
      scales: {
        x: {display:false},
        y: {grid:{color:'#1e2d45'}, ticks:{color:'#94a3b8', font:{size:11}}},
      }
    }
  });
}

function renderMapChart(data) {
  const ctx = document.getElementById('map-chart').getContext('2d');
  if (mapChart) mapChart.destroy();
  if (!data.length) return;
  mapChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.map.replace('Watchpoint: ','WP: ')),
      datasets: [{
        data: data.map(d => +(d.win_rate*100).toFixed(1)),
        backgroundColor: data.map(d => d.win_rate >= 0.55 ? '#22c55e' : d.win_rate >= 0.45 ? '#facc15' : '#ef4444'),
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {legend:{display:false}},
      scales: {
        x: {min:0, max:100, grid:{color:'#1e2d45'}, ticks:{color:'#94a3b8', font:{size:11}}},
        y: {grid:{display:false}, ticks:{color:'#94a3b8', font:{size:11}}},
      }
    }
  });
}

function renderHeroWrTable(data) {
  const tbody = document.getElementById('hero-wr-table');
  if (!data.length) { tbody.innerHTML = '<div class="empty"><p>No hero data yet.</p></div>'; return; }
  tbody.innerHTML = `<table><thead><tr><th>Hero</th><th>Win Rate</th><th>W.Games</th></tr></thead>
    <tbody>${data.map(h => `<tr>
      <td>${h.hero}</td>
      <td><span class="${wrClass(h.win_rate)}">${pct(h.win_rate)}</span> ${wrBar(h.win_rate)}</td>
      <td>${h.weighted_games}</td>
    </tr>`).join('')}</tbody></table>`;
}

function renderRanks(ranks) {
  const el = document.getElementById('d-streak').closest('.dash-grid');
  const existing = document.getElementById('rank-cards');
  if (existing) existing.remove();
  if (!ranks.length) return;
  const div = document.createElement('div');
  div.id = 'rank-cards';
  div.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px';
  div.innerHTML = ranks.map(r =>
    `<div class="stat-card" style="flex:1;min-width:120px">
       <div class="label">${r.role}</div>
       <div class="value" style="font-size:17px">${r.rank_tier} ${r.rank_division}</div>
     </div>`
  ).join('');
  el.after(div);
}

// Normalize hero name for role lookup: strip punctuation/spaces, lowercase
function heroSlug(name) {
  return (name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function getHeroRole(heroName) {
  const slug = heroSlug(heroName);
  const match = heroes.find(h => heroSlug(h.name) === slug);
  return match ? match.role : 'Unknown';
}

function renderBaselineTable(data) {
  const el = document.getElementById('baseline-table');
  if (!data.heroes || !data.heroes.length) {
    el.innerHTML = '<div class="loading">No baseline data. Go to Settings → Fetch Baseline.</div>';
    return;
  }
  baselineData = data.heroes;
  renderBaselineSorted();
}

function renderBaselineSorted() {
  const el = document.getElementById('baseline-table');

  // Sort
  const sorted = [...baselineData].sort((a, b) => {
    let av = a[baselineSortCol], bv = b[baselineSortCol];
    if (baselineSortCol === 'hero') { av = av || ''; bv = bv || ''; }
    else { av = av ?? -1; bv = bv ?? -1; }
    if (av < bv) return baselineSortDir === 'asc' ? -1 : 1;
    if (av > bv) return baselineSortDir === 'asc' ? 1 : -1;
    return 0;
  });

  // Group by role in display order
  const ROLE_ORDER = ['Tank', 'Damage', 'Support', 'Unknown'];
  const grouped = {};
  ROLE_ORDER.forEach(r => grouped[r] = []);
  sorted.forEach(h => {
    const role = getHeroRole(h.hero);
    (grouped[role] || (grouped['Unknown'] = grouped['Unknown'] || []));
    (grouped[role] || grouped['Unknown']).push(h);
  });

  const arrow = (col) => {
    if (col !== baselineSortCol) return '<span style="color:var(--faint)">⇅</span>';
    return baselineSortDir === 'asc' ? '↑' : '↓';
  };

  const thStyle = 'cursor:pointer;user-select:none;white-space:nowrap';
  const cols = [
    { key: 'hero',         label: 'Hero' },
    { key: 'playtime_pct', label: 'Playtime' },
    { key: 'games_played', label: 'Games' },
    { key: 'win_rate',     label: 'Win Rate' },
  ];

  let html = `<table><thead><tr>${cols.map(c =>
    `<th style="${thStyle}" data-col="${c.key}">${c.label} ${arrow(c.key)}</th>`
  ).join('')}</tr></thead><tbody>`;

  const ROLE_COLORS = { Tank: '#38bdf8', Damage: '#f97316', Support: '#22c55e' };

  ROLE_ORDER.forEach(role => {
    const rows = grouped[role];
    if (!rows || !rows.length) return;
    const color = ROLE_COLORS[role] || 'var(--muted)';
    html += `<tr><td colspan="4" style="background:var(--surface);color:${color};font-size:11px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;padding:6px 10px;">${role}</td></tr>`;
    rows.forEach(h => {
      html += `<tr>
        <td>${h.hero}</td>
        <td>${(h.playtime_pct||0).toFixed(1)}%</td>
        <td>${h.games_played||'—'}</td>
        <td><span class="${h.win_rate != null ? wrClass(h.win_rate) : ''}">${h.win_rate != null ? pct(h.win_rate) : '—'}</span></td>
      </tr>`;
    });
  });

  html += '</tbody></table>';
  el.innerHTML = html;

  // Attach sort handlers
  el.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (col === baselineSortCol) {
        baselineSortDir = baselineSortDir === 'desc' ? 'asc' : 'desc';
      } else {
        baselineSortCol = col;
        baselineSortDir = col === 'hero' ? 'asc' : 'desc';
      }
      renderBaselineSorted();
    });
  });
}

// ── HISTORY ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  const map = document.getElementById('h-map-filter').value;
  const outcome = document.getElementById('h-outcome-filter').value;
  const hero = document.getElementById('h-hero-filter').value;
  const params = new URLSearchParams();
  if (map) params.set('map', map);
  if (outcome) params.set('outcome', outcome);
  if (hero) params.set('hero', hero);

  const data = await api.get('/api/matches?' + params);
  const tbody = document.getElementById('history-body');

  if (!data.matches.length) {
    tbody.innerHTML = '<tr><td colspan="12" class="empty"><p>No matches yet.</p></td></tr>';
    return;
  }

  tbody.innerHTML = data.matches.map(m => {
    const myH = JSON.parse(m.my_heroes || '[]');
    const heroStr = myH.map(h => `${h.hero}${myH.length > 1 ? ' '+h.pct+'%' : ''}`).join(', ');
    const date = new Date(m.played_at).toLocaleDateString('en-US', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
    const rankStr = m.rank_tier ? `${m.rank_tier} ${m.rank_division} ${m.rank_pct ? m.rank_pct+'%' : ''}` : '—';
    return `<tr>
      <td>${m.id}</td>
      <td style="white-space:nowrap">${date}</td>
      <td>${m.map}</td>
      <td class="outcome-${m.outcome}">${m.outcome}</td>
      <td style="max-width:180px">${heroStr || '—'}</td>
      <td>${m.enemy_comp || '—'}</td>
      <td>${numFmt(m.elims)}</td>
      <td>${numFmt(m.deaths)}</td>
      <td>${numFmt(m.damage)}</td>
      <td style="font-size:12px">${rankStr}</td>
      <td>${m.stack_size > 1 ? '×'+m.stack_size : '—'}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="deleteMatch(${m.id})">✕</button></td>
    </tr>`;
  }).join('');
}

document.getElementById('h-filter-btn').addEventListener('click', loadHistory);

async function deleteMatch(id) {
  if (!confirm('Delete this match?')) return;
  await api.delete(`/api/matches/${id}`);
  loadHistory();
}

// ── ANALYTICS ─────────────────────────────────────────────────────────────────
const analyticsLoaded = {};
async function loadAnalyticsTab(tab) {
  if (analyticsLoaded[tab]) return;
  analyticsLoaded[tab] = true;

  if (tab === 'a-heroes') {
    const data = await api.get('/api/analytics/hero-winrates');
    document.getElementById('t-hero-wr').innerHTML = data.map(h =>
      `<tr><td>${h.hero}</td>
       <td><span class="${wrClass(h.win_rate)}">${pct(h.win_rate)}</span> ${wrBar(h.win_rate)}</td>
       <td>${h.weighted_games}</td>
       <td>${wrBar(h.win_rate)}</td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No data yet</td></tr>';
  }

  if (tab === 'a-maps') {
    const data = await api.get('/api/analytics/map-winrates');
    document.getElementById('t-map-wr').innerHTML = data.map(m =>
      `<tr><td>${m.map}</td><td>${m.game_mode}</td><td>${m.comp_affinity}</td>
       <td><span class="${wrClass(m.win_rate)}">${pct(m.win_rate)}</span></td>
       <td>${m.games} (${m.wins}W)</td>
       <td>${wrBar(m.win_rate)}</td></tr>`
    ).join('') || '<tr><td colspan="6" class="empty">No data yet</td></tr>';
  }

  if (tab === 'a-comp') {
    const data = await api.get('/api/analytics/comp-matchups');
    document.getElementById('t-comp-mu').innerHTML = data.map(r =>
      `<tr><td>${r.my_comp}</td><td>${r.enemy_comp}</td>
       <td><span class="${wrClass(r.win_rate)}">${pct(r.win_rate)}</span></td>
       <td>${r.games}</td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No data yet</td></tr>';
  }

  if (tab === 'a-enemy') {
    const [vhData, hmData] = await Promise.all([
      api.get('/api/analytics/vs-enemy-hero'),
      api.get('/api/analytics/hero-map'),
    ]);
    document.getElementById('t-vs-hero').innerHTML = vhData.map(r =>
      `<tr><td>${r.enemy_hero}</td>
       <td><span class="${wrClass(r.win_rate)}">${pct(r.win_rate)}</span></td>
       <td>${r.games}</td></tr>`
    ).join('') || '<tr><td colspan="3" class="empty">No data</td></tr>';
    document.getElementById('t-hero-map').innerHTML = hmData.slice(0,30).map(r =>
      `<tr><td>${r.hero}</td><td>${r.map}</td><td>${r.comp_affinity}</td>
       <td><span class="${wrClass(r.win_rate)}">${pct(r.win_rate)}</span></td>
       <td>${r.weighted_games}</td></tr>`
    ).join('') || '<tr><td colspan="5" class="empty">No data</td></tr>';
  }

  if (tab === 'a-teammates') {
    const data = await api.get('/api/analytics/teammate-winrates');
    document.getElementById('t-teammates').innerHTML = data.map(r =>
      `<tr><td>${r.player}</td><td>${r.alias||'—'}</td>
       <td><span class="${wrClass(r.win_rate)}">${pct(r.win_rate)}</span></td>
       <td>${r.games}</td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No data</td></tr>';
  }

  if (tab === 'a-bans') {
    const data = await api.get('/api/analytics/ban-stats');
    document.getElementById('t-bans').innerHTML = data.map(r =>
      `<tr><td>${r.hero}</td><td>${r.ban_count}</td>
       <td>${pct(r.ban_rate)}</td>
       <td><span class="${wrClass(r.win_rate_when_banned)}">${pct(r.win_rate_when_banned)}</span></td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No ban data yet</td></tr>';
  }

  if (tab === 'a-stack') {
    const data = await api.get('/api/analytics/stack-winrates');
    document.getElementById('t-stack').innerHTML = data.map(r =>
      `<tr><td>${r.label}</td>
       <td><span class="${wrClass(r.win_rate)}">${pct(r.win_rate)}</span></td>
       <td>${r.games}</td>
       <td>${wrBar(r.win_rate)}</td></tr>`
    ).join('') || '<tr><td colspan="4" class="empty">No data yet</td></tr>';
  }
}

// ── QUEUE ─────────────────────────────────────────────────────────────────────
async function checkQueue() {
  const data = await api.get('/api/queue');
  const n = data.queue.length;
  const badge = document.getElementById('queue-badge');
  badge.textContent = n;
  badge.style.display = n > 0 ? 'inline' : 'none';
}

async function loadQueue() {
  const data = await api.get('/api/queue');
  const emptyEl = document.getElementById('queue-empty');
  const listEl = document.getElementById('queue-list');

  if (!data.queue.length) {
    emptyEl.style.display = 'block';
    listEl.innerHTML = '';
    return;
  }
  emptyEl.style.display = 'none';
  listEl.innerHTML = data.queue.map((item, i) => {
    const p = item.parsed || {};
    return `<div class="card" style="margin-bottom:12px" id="queue-item-${i}">
      <h2>📸 ${item.filename}</h2>
      ${item.error ? `<div class="alert alert-warn">Parse error: ${item.error}</div>` : ''}
      ${(p.warnings||[]).map(w => `<div class="alert alert-warn">${w}</div>`).join('')}
      <p style="margin-bottom:12px;color:var(--muted)">Map: <strong>${p.map||'?'}</strong> &nbsp;|&nbsp; Outcome: <strong class="outcome-${p.outcome}">${p.outcome||'?'}</strong> &nbsp;|&nbsp; Confidence: ${((p.confidence||0)*100).toFixed(0)}%</p>
      <p style="margin-bottom:8px">Detected heroes: ${(p.my_heroes||[]).map(h=>h.hero).join(', ')||'—'}</p>
      <div style="display:flex; gap:8px; margin-top:12px">
        <button class="btn btn-primary btn-sm" onclick="confirmQueueItem(${i})">Confirm & Edit</button>
        <button class="btn btn-danger btn-sm" onclick="discardQueueItem('${item.filename}', ${i})">Discard</button>
      </div>
    </div>`;
  }).join('');
}

async function confirmQueueItem(idx) {
  const data = await api.get('/api/queue');
  const item = data.queue[idx];
  if (!item) return;
  const p = item.parsed || {};
  // Pre-fill the add form
  document.querySelector('.nav-btn[data-page="add"]').click();
  document.getElementById('f-map').value = p.map || '';
  document.getElementById('f-outcome').value = p.outcome || '';
  if (p.elims != null) document.getElementById('f-elims').value = p.elims;
  if (p.deaths != null) document.getElementById('f-deaths').value = p.deaths;
  if (p.assists != null) document.getElementById('f-assists').value = p.assists;
  if (p.damage != null) document.getElementById('f-damage').value = p.damage;
  if (p.healing != null) document.getElementById('f-healing').value = p.healing;
  if (p.mitigation != null) document.getElementById('f-mitigation').value = p.mitigation;

  mySelectedHeroes.length = 0;
  (p.my_heroes || []).forEach(h => mySelectedHeroes.push(h));
  enemySelectedHeroes.length = 0;
  (p.enemy_heroes || []).forEach(h => enemySelectedHeroes.push(h));
  buildHeroLists();

  document.getElementById('f-notes').value = `[Screenshot: ${item.filename}]`;
  document.getElementById('parse-hint').textContent = `Pre-filled from ${item.filename}. Review and adjust, then save.`;
  document.getElementById('parse-hint').className = 'alert alert-success';

  // Store filename to discard from queue on submit
  document.getElementById('match-form').dataset.queueFilename = item.filename;
}

async function discardQueueItem(filename, idx) {
  await api.delete(`/api/queue/${encodeURIComponent(filename)}`);
  loadQueue();
  checkQueue();
}

// ── ADD MATCH FORM ────────────────────────────────────────────────────────────
document.getElementById('match-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msgEl = document.getElementById('form-msg');
  msgEl.textContent = '';

  const map = document.getElementById('f-map').value;
  const outcome = document.getElementById('f-outcome').value;
  if (!map || !outcome) { msgEl.textContent = 'Map and Outcome are required.'; msgEl.style.color = '#ef4444'; return; }

  const rankTier = document.getElementById('f-rank-tier').value;
  const rankDiv = document.getElementById('f-rank-div').value;
  const rankPct = document.getElementById('f-rank-pct').value;

  const payload = {
    map, outcome,
    my_heroes: mySelectedHeroes,
    enemy_heroes: enemySelectedHeroes,
    bans: selectedBans,
    rank_tier: rankTier || '',
    rank_division: rankDiv ? parseInt(rankDiv) : null,
    rank_pct: rankPct !== '' ? parseFloat(rankPct) : null,
    elims: numOrNull('f-elims'), deaths: numOrNull('f-deaths'), assists: numOrNull('f-assists'),
    damage: numOrNull('f-damage'), healing: numOrNull('f-healing'), mitigation: numOrNull('f-mitigation'),
    game_length_s: numOrNull('f-game-length'),
    notes: document.getElementById('f-notes').value,
    data_source: 'manual',
  };

  const datetimeVal = document.getElementById('f-played-at').value;
  if (datetimeVal) payload.played_at = new Date(datetimeVal).toISOString();

  const result = await api.post('/api/matches', payload);
  if (result.id) {
    msgEl.textContent = `Match #${result.id} saved.`;
    msgEl.style.color = '#22c55e';
    // discard queue item if this came from queue
    const qf = e.target.dataset.queueFilename;
    if (qf) { await api.delete(`/api/queue/${encodeURIComponent(qf)}`); delete e.target.dataset.queueFilename; }
    clearForm();
    Object.keys(analyticsLoaded).forEach(k => delete analyticsLoaded[k]);
    checkQueue();
  } else {
    msgEl.textContent = JSON.stringify(result);
    msgEl.style.color = '#ef4444';
  }
});

document.getElementById('form-clear-btn').addEventListener('click', clearForm);

function clearForm() {
  document.getElementById('match-form').reset();
  mySelectedHeroes.length = 0;
  enemySelectedHeroes.length = 0;
  selectedBans.length = 0;
  buildHeroLists();
  document.getElementById('form-msg').textContent = '';
  document.getElementById('parse-hint').textContent = 'Tip: Drop a screenshot in your inbox folder and it\'ll appear in the Queue tab pre-filled.';
  document.getElementById('parse-hint').className = 'alert alert-info';
}

function numOrNull(id) {
  const v = document.getElementById(id).value;
  return v === '' ? null : parseInt(v);
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
let settingsData = {};
async function loadSettings() {
  settingsData = await api.get('/api/settings');
  document.getElementById('s-battletag').value = settingsData.battletag || '';
  document.getElementById('s-username').value = settingsData.username || '';
  document.getElementById('s-inbox').value = settingsData.inbox_folder || '';
  renderTrackedPlayers();
  loadMapConfig();
}

function renderTrackedPlayers() {
  const el = document.getElementById('tracked-list');
  const players = settingsData.tracked_players || [];
  el.innerHTML = players.map(p =>
    `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
       <span>${p.name}</span>
       <span style="color:var(--muted)">${p.alias}</span>
       <button class="btn btn-secondary btn-sm" onclick="removeTrackedPlayer('${p.name}')">✕</button>
     </div>`
  ).join('') || '<p style="color:var(--muted)">No tracked players yet.</p>';
}

document.getElementById('s-save-btn').addEventListener('click', async () => {
  settingsData.battletag = document.getElementById('s-battletag').value;
  settingsData.username = document.getElementById('s-username').value;
  settingsData.inbox_folder = document.getElementById('s-inbox').value;
  const result = await api.put('/api/settings', settingsData);
  const msg = document.getElementById('s-msg');
  msg.textContent = result.ok ? 'Saved.' : 'Error saving.';
  msg.style.color = result.ok ? '#22c55e' : '#ef4444';
});

document.getElementById('s-add-player-btn').addEventListener('click', () => {
  const name = document.getElementById('s-player-name').value.trim();
  const alias = document.getElementById('s-player-alias').value.trim();
  if (!name) return;
  if (!settingsData.tracked_players) settingsData.tracked_players = [];
  if (!settingsData.tracked_players.find(p => p.name === name)) {
    settingsData.tracked_players.push({name, alias});
  }
  document.getElementById('s-player-name').value = '';
  document.getElementById('s-player-alias').value = '';
  renderTrackedPlayers();
});

function removeTrackedPlayer(name) {
  settingsData.tracked_players = (settingsData.tracked_players || []).filter(p => p.name !== name);
  renderTrackedPlayers();
}

async function loadMapConfig() {
  const tbody = document.getElementById('map-config-body');
  tbody.innerHTML = maps.map(m =>
    `<tr>
       <td>${m.name}</td><td style="color:var(--muted)">${m.game_mode}</td>
       <td>
         <select data-map="${m.name}" class="map-affinity-sel" style="padding:4px 6px">
           ${['Dive','Poke','Brawl','Neutral'].map(a =>
             `<option${m.comp_affinity===a?' selected':''}>${a}</option>`).join('')}
         </select>
       </td>
       <td><button class="btn btn-secondary btn-sm" onclick="saveMapAffinity('${m.name}')">Save</button></td>
     </tr>`
  ).join('');
}

async function saveMapAffinity(mapName) {
  const sel = document.querySelector(`[data-map="${mapName}"]`);
  await api.put(`/api/maps/${encodeURIComponent(mapName)}`, {comp_affinity: sel.value, notes: ''});
  maps = await api.get('/api/maps');
  Object.keys(analyticsLoaded).forEach(k => delete analyticsLoaded[k]);
}

document.getElementById('baseline-fetch-btn').addEventListener('click', async () => {
  const btn = document.getElementById('baseline-fetch-btn');
  const msg = document.getElementById('baseline-msg');
  btn.disabled = true;
  msg.textContent = 'Fetching…';
  try {
    const result = await api.post('/api/baseline/fetch', {});
    msg.textContent = `Fetched ${result.heroes_fetched || 0} heroes.`;
    msg.style.color = '#22c55e';
  } catch(e) {
    msg.textContent = 'Error: ' + e.message;
    msg.style.color = '#ef4444';
  } finally {
    btn.disabled = false;
  }
});

// ── BOOT ──────────────────────────────────────────────────────────────────────
init();
