// ── State ─────────────────────────────────────────────────────────────────────
let heroes = [], maps = [];
let srChart = null, mapChart = null;
const PCT_CYCLE = [100, 75, 50, 25];
let baselineData = [];
let baselineSortCol = 'playtime_pct';
let baselineSortDir = 'desc';

// Session state
let activeSession = null;
let sessionTimerInterval = null;
let sessionMatches = [];

// Sessions page state
let pendingSessionExpand = null;

// Modal state
let modalIsHistorical = false;
let mModalMyHeroes = [];
let mModalEnemyHeroes = [];
let mModalBans = [];
let practiceSelection = null;
let pendingQueueFilename = null;

// ── API ───────────────────────────────────────────────────────────────────────
const api = {
  get:    (url)       => fetch(url).then(r => r.json()),
  post:   (url, body) => fetch(url, {method:'POST',  headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r => r.json()),
  put:    (url, body) => fetch(url, {method:'PUT',   headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r => r.json()),
  patch:  (url, body) => fetch(url, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).then(r => r.json()),
  delete: (url)       => fetch(url, {method:'DELETE'}).then(r => r.json()),
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

document.getElementById('add-historical-btn').addEventListener('click', () => {
  openGameModal(null, true);
});

function onPageEnter(page) {
  if (page === 'dashboard') loadDashboard();
  if (page === 'history')   loadHistory();
  if (page === 'analytics') loadAnalyticsTab('a-heroes');
  if (page === 'sessions')  loadSessionsPage();
  if (page === 'queue')     loadQueue();
  if (page === 'settings')  loadSettings();
  if (page === 'session')   loadSessionPage();
}

// ── Tab bars ──────────────────────────────────────────────────────────────────
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
function pct(v)    { return v != null ? (v * 100).toFixed(1) + '%' : '—'; }
function wrBar(wr) { return `<span class="wr-bar" style="width:${(wr*60).toFixed(0)}px"></span>`; }
function numFmt(n) { if (n == null) return '—'; return n >= 1000 ? (n/1000).toFixed(1)+'k' : n; }
function numOrNull(id) {
  const v = document.getElementById(id).value;
  return v === '' ? null : parseInt(v);
}
function formatDuration(totalSeconds) {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  [heroes, maps] = await Promise.all([api.get('/api/heroes'), api.get('/api/maps')]);
  populateMapSelects();
  buildModalHeroLists();
  populateHeroFilter();
  loadDashboard();
  checkQueue();
  setInterval(checkQueue, 10000);

  const { session } = await api.get('/api/sessions/active');
  if (session) {
    activeSession = session;
    updateSessionNavBtn();
    startSessionTimer();
  }
}

function populateMapSelects() {
  const modalSel = document.getElementById('m-map');
  const hFilter  = document.getElementById('h-map-filter');
  modalSel.innerHTML = '<option value="">Select map…</option>';
  hFilter.innerHTML  = '<option value="">All Maps</option>';
  const grouped = {};
  maps.forEach(m => {
    if (!grouped[m.game_mode]) grouped[m.game_mode] = [];
    grouped[m.game_mode].push(m);
  });
  Object.entries(grouped).forEach(([mode, mps]) => {
    const makeGroup = () => {
      const og = document.createElement('optgroup');
      og.label = mode;
      mps.forEach(m => { const o = document.createElement('option'); o.value = m.name; o.textContent = m.name; og.appendChild(o); });
      return og;
    };
    modalSel.appendChild(makeGroup());
    hFilter.appendChild(makeGroup());
  });
}

function populateHeroFilter() {
  const sel = document.getElementById('h-hero-filter');
  sel.innerHTML = '<option value="">All Heroes</option>';
  [...new Set(heroes.map(h => h.name))].sort().forEach(n => {
    const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o);
  });
}

// ── Hero chip rendering ───────────────────────────────────────────────────────
function roleClass(role) {
  return { Tank: 'tank', Damage: 'dps', Support: 'support' }[role] || 'unknown';
}

function renderHeroChipList(containerId, selectedArr) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  heroes.forEach(h => {
    const selected = selectedArr.find(e => e.hero === h.name);
    const rc = roleClass(h.role);
    const chip = document.createElement('div');
    chip.className = `hero-chip role-${rc}` + (selected ? ' selected' : '');
    chip.dataset.hero = h.name;
    chip.title = `${h.role} · ${h.sub_role} · ${h.primary_archetype}`;

    const dot = document.createElement('span'); dot.className = `role-dot ${rc}`;
    const label = document.createElement('span'); label.textContent = h.name;
    const pctBadge = document.createElement('span');
    pctBadge.className = 'pct-badge';
    pctBadge.textContent = selected ? selected.pct + '%' : '100%';

    chip.appendChild(dot); chip.appendChild(label); chip.appendChild(pctBadge);

    chip.addEventListener('click', (e) => {
      if (e.target === pctBadge && selectedArr.find(e => e.hero === h.name)) {
        const entry = selectedArr.find(e => e.hero === h.name);
        const idx = PCT_CYCLE.indexOf(entry.pct);
        entry.pct = PCT_CYCLE[(idx + 1) % PCT_CYCLE.length];
        pctBadge.textContent = entry.pct + '%';
      } else {
        const idx = selectedArr.findIndex(e => e.hero === h.name);
        if (idx >= 0) { selectedArr.splice(idx, 1); chip.classList.remove('selected'); }
        else { selectedArr.push({hero: h.name, pct: 100}); chip.classList.add('selected'); pctBadge.textContent = '100%'; }
      }
    });
    container.appendChild(chip);
  });
}

function renderBanChipList(containerId, selectedArr) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  heroes.forEach(h => {
    const selected = selectedArr.includes(h.name);
    const chip = document.createElement('div');
    chip.className = 'hero-chip' + (selected ? ' selected' : '');
    chip.textContent = h.name;
    chip.addEventListener('click', () => {
      const idx = selectedArr.indexOf(h.name);
      if (idx >= 0) { selectedArr.splice(idx, 1); chip.classList.remove('selected'); }
      else if (selectedArr.length < 5) { selectedArr.push(h.name); chip.classList.add('selected'); }
    });
    container.appendChild(chip);
  });
}

function buildModalHeroLists() {
  renderHeroChipList('m-my-heroes',    mModalMyHeroes);
  renderHeroChipList('m-enemy-heroes', mModalEnemyHeroes);
  renderBanChipList( 'm-bans',         mModalBans);
}

// ── SESSION NAV BUTTON ────────────────────────────────────────────────────────
function updateSessionNavBtn() {
  const btn    = document.getElementById('session-nav-btn');
  const textEl = document.getElementById('sess-nav-text');
  if (activeSession) {
    btn.classList.add('live');
    // Timer text updated by interval; set initial value immediately
    const elapsed = Math.floor((Date.now() - new Date(activeSession.started_at)) / 1000);
    textEl.textContent = '⏺ ' + formatDuration(elapsed);
  } else {
    btn.classList.remove('live');
    textEl.textContent = 'Live Session';
  }
}

function startSessionTimer() {
  if (sessionTimerInterval) clearInterval(sessionTimerInterval);
  sessionTimerInterval = setInterval(() => {
    if (!activeSession) { clearInterval(sessionTimerInterval); return; }
    const elapsed = Math.floor((Date.now() - new Date(activeSession.started_at)) / 1000);
    const str = formatDuration(elapsed);
    const navEl   = document.getElementById('sess-nav-text');
    const timerEl = document.getElementById('ss-timer');
    if (navEl)   navEl.textContent   = '⏺ ' + str;
    if (timerEl) timerEl.textContent = str;
  }, 1000);
}

// ── SESSION PAGE ──────────────────────────────────────────────────────────────
async function loadSessionPage() {
  const { session } = await api.get('/api/sessions/active');
  if (session) {
    activeSession = session;
    updateSessionNavBtn();
    startSessionTimer();
    const data = await api.get(`/api/sessions/${session.id}`);
    sessionMatches = data.matches || [];
    showActiveSession();
  } else {
    activeSession = null;
    updateSessionNavBtn();
    showIdleSession();
    loadRecentSessions();
  }
}

function showIdleSession() {
  document.getElementById('sess-idle').style.display    = 'block';
  document.getElementById('sess-active').style.display  = 'none';
  document.getElementById('sess-summary').style.display = 'none';
}

function showActiveSession() {
  document.getElementById('sess-idle').style.display    = 'none';
  document.getElementById('sess-active').style.display  = 'block';
  document.getElementById('sess-summary').style.display = 'none';

  // Restore focus mode from session
  const toggle = document.getElementById('sess-focus-toggle');
  toggle.checked = !!activeSession.focus_mode;
  setFocusMode(!!activeSession.focus_mode);

  // Goal display
  const goalEl = document.getElementById('sess-goal-text');
  goalEl.textContent = activeSession.goal || '';
  goalEl.className   = 'sess-goal' + (activeSession.goal ? '' : ' sess-goal-empty');
  if (!activeSession.goal) goalEl.textContent = 'No goal set';

  updateSessionStats();
  renderSessionGames();
  updateQueueHint();
}

function updateSessionStats() {
  const games  = sessionMatches.length;
  const wins   = sessionMatches.filter(m => m.outcome === 'Win').length;
  const losses = sessionMatches.filter(m => m.outcome === 'Loss').length;
  document.getElementById('ss-games').textContent  = games;
  document.getElementById('ss-wins').textContent   = wins;
  document.getElementById('ss-losses').textContent = losses;
  const wrEl = document.getElementById('ss-wr');
  wrEl.textContent  = games ? pct(wins / games) : '—';
  wrEl.className    = 'sess-stat-val' + (games ? ' ' + wrClass(wins / games) : '');

  // Rank delta
  const withRank = sessionMatches.filter(m => m.rank_score != null);
  const rdEl = document.getElementById('ss-rank-delta');
  if (withRank.length >= 2) {
    const delta = withRank[withRank.length - 1].rank_score - withRank[0].rank_score;
    rdEl.textContent = (delta >= 0 ? '+' : '') + delta.toFixed(0);
    rdEl.className   = 'sess-stat-val ' + (delta >= 0 ? 'wr-good' : 'wr-bad');
  } else {
    rdEl.textContent = '—';
    rdEl.className   = 'sess-stat-val';
  }
}

function renderSessionGames() {
  const list = document.getElementById('sess-games-list');
  if (!sessionMatches.length) {
    list.innerHTML = '<p style="color:var(--muted);padding:12px 0">No games yet.</p>';
    return;
  }
  list.innerHTML = [...sessionMatches].reverse().map(m => renderMatchCard(m)).join('');
  list.querySelectorAll('.match-card-header').forEach(h => {
    h.addEventListener('click', () => h.closest('.match-card').classList.toggle('expanded'));
  });
}

async function updateQueueHint() {
  const data = await api.get('/api/queue');
  const n    = data.queue.length;
  const el   = document.getElementById('sess-queue-hint');
  if (n > 0) {
    el.innerHTML = `<a href="#" id="queue-hint-link" style="color:var(--accent2)">${n} screenshot(s) pending — review in Queue tab</a>`;
    document.getElementById('queue-hint-link').addEventListener('click', e => {
      e.preventDefault();
      document.querySelector('.nav-btn[data-page="queue"]').click();
    });
  } else {
    el.textContent = '';
  }
}

function setFocusMode(enabled) {
  const container = document.getElementById('sess-active');
  if (enabled) container.classList.add('focus-mode');
  else         container.classList.remove('focus-mode');
}

async function loadRecentSessions() {
  const sessions = await api.get('/api/sessions');
  const el = document.getElementById('recent-sessions');
  const finished = sessions.filter(s => s.ended_at);
  if (!finished.length) {
    el.innerHTML = '<div class="loading" style="padding:20px 0">No completed sessions yet.</div>';
    return;
  }
  el.innerHTML = finished.slice(0, 10).map(s => {
    const games  = s.match_count || 0;
    const wins   = s.wins   || 0;
    const losses = s.losses || 0;
    const title  = s.name || (s.goal ? s.goal.slice(0, 60) : null) || new Date(s.started_at || s.date).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
    const dateStr = new Date(s.started_at || s.date).toLocaleDateString('en-US', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
    let durationStr = '—';
    if (s.started_at && s.ended_at) {
      const secs = Math.floor((new Date(s.ended_at) - new Date(s.started_at)) / 1000);
      durationStr = formatDuration(secs);
    }
    return `<div class="sess-card" onclick="viewSession(${s.id})">
      <div class="sess-card-title">${title}</div>
      <div class="sess-card-meta">
        <span>${dateStr}</span>
        <span>${games} games · ${wins}W–${losses}L</span>
        <span>${durationStr}</span>
        ${s.goal ? `<span style="color:var(--muted);font-style:italic">${s.goal.slice(0, 40)}</span>` : ''}
      </div>
    </div>`;
  }).join('');
}

function viewSession(id) {
  pendingSessionExpand = id;
  document.querySelector('.nav-btn[data-page="sessions"]').click();
}

// ── SESSIONS PAGE ─────────────────────────────────────────────────────────────
async function loadSessionsPage() {
  const el       = document.getElementById('sessions-list');
  el.innerHTML   = '<div class="loading" style="padding:24px 0;color:var(--dim)">Loading…</div>';
  const sessions = await api.get('/api/sessions');
  const finished = sessions.filter(s => s.ended_at);

  if (!finished.length) {
    el.innerHTML = '<div class="empty"><h3>No completed sessions yet</h3><p>Start a session to begin tracking your play.</p></div>';
    return;
  }

  el.innerHTML = `<div class="sessions-list">${finished.map(s => renderSessionHistCard(s)).join('')}</div>`;

  el.querySelectorAll('.sess-hist-header').forEach(header => {
    header.addEventListener('click', () => toggleSessionCard(header.closest('.sess-hist-card')));
  });

  if (pendingSessionExpand) {
    const expandId = pendingSessionExpand;
    pendingSessionExpand = null;
    const card = document.getElementById(`shc-${expandId}`);
    if (card) {
      await toggleSessionCard(card);
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function renderSessionHistCard(s) {
  const wins   = s.wins        || 0;
  const losses = s.losses      || 0;
  const games  = s.match_count || 0;
  const wr     = games ? wins / games : null;
  const title  = s.name
    || (s.goal ? s.goal.slice(0, 60) : null)
    || new Date(s.started_at || s.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  const dateStr = new Date(s.started_at || s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  let dur = '';
  if (s.started_at && s.ended_at) {
    const secs = Math.floor((new Date(s.ended_at) - new Date(s.started_at)) / 1000);
    dur = formatDuration(secs);
  }
  const metaParts = [dateStr, dur, games + 'G'].filter(Boolean);
  const wrHtml = wr != null ? `<span class="sess-hist-wr ${wrClass(wr)}">${pct(wr)}</span>` : '';

  return `<div class="sess-hist-card" id="shc-${s.id}">
    <div class="sess-hist-header">
      <span class="sess-hist-title">${title}</span>
      <span class="sess-hist-wl">
        <span class="wr-good">${wins}W</span><span style="color:var(--dim)"> – </span><span class="wr-bad">${losses}L</span>
      </span>
      ${wrHtml}
      <span class="sess-hist-meta">${metaParts.join(' · ')}</span>
      <span class="sess-hist-chevron">▼</span>
    </div>
    <div class="sess-hist-body" id="shb-${s.id}">
      <div class="loading" style="padding:16px 0;color:var(--dim)">Loading…</div>
    </div>
  </div>`;
}

async function toggleSessionCard(card) {
  const id = card.id.replace('shc-', '');
  if (!card.classList.contains('expanded') && !card.dataset.loaded) {
    const data    = await api.get(`/api/sessions/${id}`);
    const matches = data.matches || [];
    const body    = document.getElementById(`shb-${id}`);

    if (!matches.length) {
      body.innerHTML = '<div style="color:var(--dim);padding:16px 0;font-size:13px">No games logged in this session.</div>';
    } else {
      const spineHtml = buildSpine(matches);
      const goalHtml  = data.goal
        ? `<div style="font-size:12px;color:var(--muted);font-style:italic;margin-bottom:14px">Goal: ${data.goal}</div>`
        : '';
      body.innerHTML = `
        <div class="sess-spine-row">${spineHtml}</div>
        ${goalHtml}
        <div class="sess-matches">${[...matches].reverse().map(m => renderMatchCard(m)).join('')}</div>
      `;
      body.querySelectorAll('.match-card-header').forEach(h => {
        h.addEventListener('click', () => h.closest('.match-card').classList.toggle('expanded'));
      });
    }
    card.dataset.loaded = '1';
  }
  card.classList.toggle('expanded');
}

function buildSpine(matches) {
  const pips = matches.map(m => {
    const oc = m.outcome === 'Win' ? 'win' : m.outcome === 'Loss' ? 'loss' : 'draw';
    return `<span class="spine-pip ${oc}"></span>`;
  }).join('');
  // Streak summary
  let streak = 0, streakType = '';
  for (let i = matches.length - 1; i >= 0; i--) {
    const oc = matches[i].outcome;
    if (i === matches.length - 1) { streak = 1; streakType = oc; }
    else if (oc === streakType)   streak++;
    else break;
  }
  const streakHtml = streak > 1
    ? `<span class="spine-streak">${streak} ${streakType} streak</span>`
    : '';
  return `<div class="momentum-spine">${pips}${streakHtml}</div>`;
}

function openEditMatch(id) {
  // TODO: open modal pre-filled for editing — placeholder
  console.log('Edit match', id);
}

// ── START SESSION ─────────────────────────────────────────────────────────────
document.getElementById('s-start-btn').addEventListener('click', async () => {
  const goal       = document.getElementById('s-goal').value.trim();
  const focus_mode = document.getElementById('s-focus-check').checked;
  const result     = await api.post('/api/sessions', { goal, focus_mode });
  if (result.id) {
    const { session } = await api.get('/api/sessions/active');
    activeSession  = session;
    sessionMatches = [];
    updateSessionNavBtn();
    startSessionTimer();
    showActiveSession();
  }
});

// ── END SESSION ───────────────────────────────────────────────────────────────
document.getElementById('sess-end-btn').addEventListener('click', async () => {
  if (!activeSession) return;
  if (!confirm('End this session?')) return;
  await api.post(`/api/sessions/${activeSession.id}/end`, {});

  // Show summary
  const games  = sessionMatches.length;
  const wins   = sessionMatches.filter(m => m.outcome === 'Win').length;
  const losses = sessionMatches.filter(m => m.outcome === 'Loss').length;
  const elapsed = Math.floor((Date.now() - new Date(activeSession.started_at)) / 1000);
  const practiced = sessionMatches.filter(m => m.practiced === 'Y').length;
  const sortOf    = sessionMatches.filter(m => m.practiced === 'Sort of').length;

  let html = `<p style="font-size:20px;margin:8px 0"><strong>${wins}W – ${losses}L</strong> &nbsp;·&nbsp; ${formatDuration(elapsed)}</p>`;
  if (activeSession.goal) {
    html += `<p style="color:var(--muted);margin-top:8px">Goal: <em>${activeSession.goal}</em></p>`;
    if (games > 0) {
      html += `<p style="color:var(--muted)">Focused: ${practiced + sortOf}/${games} games</p>`;
    }
  }
  document.getElementById('sess-summary-content').innerHTML = html;

  activeSession = null;
  clearInterval(sessionTimerInterval);
  updateSessionNavBtn();

  document.getElementById('sess-idle').style.display    = 'none';
  document.getElementById('sess-active').style.display  = 'none';
  document.getElementById('sess-summary').style.display = 'block';
});

document.getElementById('sess-summary-dismiss').addEventListener('click', () => {
  showIdleSession();
  loadRecentSessions();
});

// ── FOCUS MODE TOGGLE ─────────────────────────────────────────────────────────
document.getElementById('sess-focus-toggle').addEventListener('change', async (e) => {
  setFocusMode(e.target.checked);
  if (activeSession) {
    await api.patch(`/api/sessions/${activeSession.id}`, { focus_mode: e.target.checked });
    activeSession.focus_mode = e.target.checked ? 1 : 0;
  }
});

// ── ADD GAME BUTTON ───────────────────────────────────────────────────────────
document.getElementById('sess-add-game-btn').addEventListener('click', () => {
  openGameModal(null, false);
});

// ── GAME MODAL ────────────────────────────────────────────────────────────────
function openGameModal(prefill, isHistorical) {
  modalIsHistorical  = isHistorical;
  practiceSelection  = null;
  pendingQueueFilename = prefill ? prefill._queueFilename || null : null;

  // Reset form
  document.getElementById('m-map').value          = '';
  document.getElementById('m-outcome').value      = '';
  document.getElementById('m-played-at').value    = '';
  document.getElementById('m-rank-tier').value    = '';
  document.getElementById('m-rank-div').value     = '';
  document.getElementById('m-rank-pct').value     = '';
  ['m-elims','m-deaths','m-assists','m-damage','m-healing','m-mitigation','m-game-length'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('m-notes').value          = '';
  document.getElementById('m-practice-notes').value = '';
  document.getElementById('modal-msg').textContent   = '';
  document.querySelectorAll('.practice-btn').forEach(b => b.classList.remove('selected'));
  document.querySelectorAll('[id^="mf-"]').forEach(el => {
    el.classList.remove('field-ocr-loading', 'field-ocr-low');
  });
  const banner = document.getElementById('modal-ocr-banner');
  banner.style.display = 'none';

  mModalMyHeroes.length    = 0;
  mModalEnemyHeroes.length = 0;
  mModalBans.length        = 0;

  // Apply prefill
  if (prefill) {
    if (prefill.map)          document.getElementById('m-map').value        = prefill.map;
    if (prefill.outcome)      document.getElementById('m-outcome').value    = prefill.outcome;
    if (prefill.game_length_s != null) document.getElementById('m-game-length').value = prefill.game_length_s;
    if (prefill.played_at)    document.getElementById('m-played-at').value  = prefill.played_at.slice(0, 16); // "YYYY-MM-DDTHH:MM"
    if (prefill.elims      != null) document.getElementById('m-elims').value       = prefill.elims;
    if (prefill.deaths     != null) document.getElementById('m-deaths').value      = prefill.deaths;
    if (prefill.assists    != null) document.getElementById('m-assists').value     = prefill.assists;
    if (prefill.damage     != null) document.getElementById('m-damage').value      = prefill.damage;
    if (prefill.healing    != null) document.getElementById('m-healing').value     = prefill.healing;
    if (prefill.mitigation != null) document.getElementById('m-mitigation').value  = prefill.mitigation;
    (prefill.my_heroes    || []).forEach(h => mModalMyHeroes.push(h));
    (prefill.enemy_heroes || []).forEach(h => mModalEnemyHeroes.push(h));

    if ((prefill.warnings || []).length) {
      banner.textContent    = 'OCR: ' + prefill.warnings.join('; ');
      banner.style.display  = 'block';
    }
    if (prefill.confidence != null && prefill.confidence < 0.6 && prefill.tab_type !== 'SUMMARY') {
      banner.textContent   = (banner.textContent ? banner.textContent + ' | ' : '') + `Low confidence (${(prefill.confidence*100).toFixed(0)}%) — review hero selections.`;
      banner.style.display = 'block';
    }
  }

  buildModalHeroLists();

  // Title
  document.getElementById('modal-title-text').textContent = isHistorical ? 'Add Historical Game' : 'Log Game';

  // Practice section visibility
  const practiceSection = document.getElementById('modal-practice-section');
  if (activeSession && !isHistorical) {
    practiceSection.style.display = 'block';
    const goalText = activeSession.goal || '';
    document.getElementById('modal-goal-display').textContent = goalText ? `"${goalText}"` : 'No goal set for this session.';
  } else {
    practiceSection.style.display = 'none';
  }

  document.getElementById('game-modal').style.display = 'flex';
}

function closeGameModal() {
  document.getElementById('game-modal').style.display = 'none';
}

document.getElementById('modal-close-btn').addEventListener('click',  closeGameModal);
document.getElementById('modal-cancel-btn').addEventListener('click', closeGameModal);
document.getElementById('game-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('game-modal')) closeGameModal();
});

document.querySelectorAll('.practice-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    practiceSelection = btn.dataset.val;
    document.querySelectorAll('.practice-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
  });
});

document.getElementById('modal-save-btn').addEventListener('click', saveModalGame);

async function saveModalGame() {
  const msgEl   = document.getElementById('modal-msg');
  const map     = document.getElementById('m-map').value;
  const outcome = document.getElementById('m-outcome').value;
  if (!map || !outcome) {
    msgEl.textContent  = 'Map and Outcome are required.';
    msgEl.style.color  = 'var(--loss)';
    return;
  }

  const rankTier = document.getElementById('m-rank-tier').value;
  const rankDiv  = document.getElementById('m-rank-div').value;
  const rankPct  = document.getElementById('m-rank-pct').value;
  const datetimeVal = document.getElementById('m-played-at').value;

  const payload = {
    map, outcome,
    my_heroes:     mModalMyHeroes,
    enemy_heroes:  mModalEnemyHeroes,
    bans:          mModalBans,
    rank_tier:     rankTier || '',
    rank_division: rankDiv  ? parseInt(rankDiv)     : null,
    rank_pct:      rankPct !== '' ? parseFloat(rankPct) : null,
    elims:         numOrNull('m-elims'),
    deaths:        numOrNull('m-deaths'),
    assists:       numOrNull('m-assists'),
    damage:        numOrNull('m-damage'),
    healing:       numOrNull('m-healing'),
    mitigation:    numOrNull('m-mitigation'),
    game_length_s: numOrNull('m-game-length'),
    notes:         document.getElementById('m-notes').value,
    data_source:   'manual',
    is_historical: modalIsHistorical,
    practiced:     (activeSession && !modalIsHistorical) ? practiceSelection : null,
    practice_notes: document.getElementById('m-practice-notes').value,
  };
  if (datetimeVal) payload.played_at = new Date(datetimeVal).toISOString();
  if (activeSession && !modalIsHistorical) payload.session_id = activeSession.id;

  const result = await api.post('/api/matches', payload);
  if (result.id) {
    msgEl.textContent = `Game #${result.id} saved.`;
    msgEl.style.color = 'var(--win)';

    if (pendingQueueFilename) {
      await api.delete(`/api/queue/${encodeURIComponent(pendingQueueFilename)}`);
      pendingQueueFilename = null;
      checkQueue();
    }

    Object.keys(analyticsLoaded).forEach(k => delete analyticsLoaded[k]);

    if (activeSession && !modalIsHistorical) {
      const data   = await api.get(`/api/sessions/${activeSession.id}`);
      sessionMatches = data.matches || [];
      updateSessionStats();
      renderSessionGames();
    }

    setTimeout(closeGameModal, 600);
  } else {
    msgEl.textContent = JSON.stringify(result);
    msgEl.style.color = 'var(--loss)';
  }
}

// ── DASHBOARD ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
  const [dash, sr, mapWr, heroWr, baseline, sessions] = await Promise.all([
    api.get('/api/analytics/dashboard'),
    api.get('/api/analytics/sr-timeline'),
    api.get('/api/analytics/map-winrates'),
    api.get('/api/analytics/hero-winrates'),
    api.get('/api/baseline'),
    api.get('/api/sessions'),
  ]);

  const total = dash.total || 0;
  document.getElementById('d-total').textContent = total;

  const wrEl  = document.getElementById('d-wr');
  const wrVal = total ? dash.win_rate : null;
  wrEl.textContent = pct(wrVal);
  wrEl.className   = 'value ' + (wrVal ? wrClass(wrVal) : '');
  document.getElementById('d-wr-sub').textContent = total ? `${dash.wins} W` : '';

  const wr20El = document.getElementById('d-wr20');
  wr20El.textContent = pct(dash.win_rate_last20 || null);
  wr20El.className   = 'value ' + (dash.win_rate_last20 ? wrClass(dash.win_rate_last20) : '');

  const streakEl = document.getElementById('d-streak');
  if (dash.streak > 0) {
    streakEl.textContent = `${dash.streak} ${dash.streak_type}`;
    streakEl.className   = 'value ' + (dash.streak_type === 'Win' ? 'wr-good' : 'wr-bad');
  } else {
    streakEl.textContent = '—';
  }

  document.getElementById('d-hero').textContent = dash.best_hero || '—';
  document.getElementById('d-map').textContent  = dash.best_map  || '—';

  renderRanks(dash.ranks || []);
  renderDashSessions(sessions);
  renderImproving(dash);
  renderSrChart(sr);
  renderMapChart(mapWr.slice(0, 8));
  renderHeroWrTable(heroWr.slice(0, 15));
  renderBaselineTable(baseline);
}

function renderDashSessions(sessions) {
  const el       = document.getElementById('dash-recent-sessions');
  const finished = sessions.filter(s => s.ended_at).slice(0, 5);
  if (!finished.length) {
    el.innerHTML = '<div style="padding:16px 0;color:var(--dim);font-size:13px">No completed sessions yet — start one to see it here.</div>';
    return;
  }
  el.innerHTML = finished.map(s => {
    const wins    = s.wins   || 0;
    const losses  = s.losses || 0;
    const games   = s.match_count || 0;
    const wr      = games ? wins / games : null;
    const title   = s.name || (s.goal ? s.goal.slice(0, 50) : null)
                  || new Date(s.started_at || s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const dateStr = new Date(s.started_at || s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    let dur = '';
    if (s.started_at && s.ended_at) {
      const secs = Math.floor((new Date(s.ended_at) - new Date(s.started_at)) / 1000);
      dur = formatDuration(secs);
    }
    const wrStr = wr != null ? `${pct(wr)} WR` : '';
    return `<div class="dash-sess-card" onclick="viewSession(${s.id})">
      <div class="dash-sess-card-title">${title}</div>
      <div class="dash-sess-card-wl">
        <span class="wl-w">${wins}W</span><span class="wl-sep">–</span><span class="wl-l">${losses}L</span>
      </div>
      <div class="dash-sess-card-meta">${[dateStr, wrStr, dur].filter(Boolean).join(' · ')}</div>
    </div>`;
  }).join('');
}

function renderImproving(dash) {
  const el      = document.getElementById('dash-improving');
  const overall = dash.win_rate;
  const last20  = dash.win_rate_last20;
  if (overall == null || dash.total < 5) {
    el.innerHTML = '<div style="color:var(--dim);font-size:13px">Need more games to compare.</div>';
    return;
  }
  const delta    = last20 != null ? last20 - overall : null;
  const deltaPct = delta != null ? (delta * 100).toFixed(1) : null;
  const dir      = delta == null ? 'flat' : delta > 0.02 ? 'up' : delta < -0.02 ? 'down' : 'flat';
  const arrow    = { up: '↑', down: '↓', flat: '→' }[dir];
  const label20  = last20 != null ? `<span class="improving-big ${wrClass(last20)}">${pct(last20)}</span>` : '<span class="improving-big" style="color:var(--dim)">—</span>';
  const deltaHtml = deltaPct != null
    ? `<span class="improving-delta ${dir}">${arrow} ${deltaPct > 0 ? '+' : ''}${deltaPct}%</span>`
    : '';

  el.innerHTML = `
    <div class="improving-label" style="margin-bottom:6px">Last 20 games</div>
    <div class="improving-row">
      ${label20}
      ${deltaHtml}
    </div>
    <div style="font-size:12px;color:var(--dim)">vs all-time ${pct(overall)} · ${dash.total} games total</div>
    ${dir === 'up'   ? '<div style="font-size:12px;color:var(--win);margin-top:8px">Trending up — recent form is above your average.</div>'  : ''}
    ${dir === 'down' ? '<div style="font-size:12px;color:var(--loss);margin-top:8px">Recent form is below your average — room to recalibrate.</div>' : ''}
    ${dir === 'flat' ? '<div style="font-size:12px;color:var(--muted);margin-top:8px">Consistent — recent form matches your overall average.</div>' : ''}
  `;
}

function renderSrChart(data) {
  const ctx = document.getElementById('sr-chart').getContext('2d');
  if (srChart) srChart.destroy();
  if (!data.length) return;
  srChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map((_, i) => i + 1),
      datasets: [{ data: data.map(d => d.rank_score), borderColor: '#e0518a',
        backgroundColor: 'rgba(224,81,138,.1)', pointRadius: 2, tension: 0.3, fill: true }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: {display:false}, tooltip: { callbacks: { label: ctx => {
        const d = data[ctx.dataIndex];
        return `${d.rank_tier} ${d.rank_division} — ${d.map} (${d.outcome})`;
      }}}},
      scales: { x: {display:false}, y: {grid:{color:'#1e2d45'}, ticks:{color:'#94a3b8', font:{size:11}}} }
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
      datasets: [{ data: data.map(d => +(d.win_rate*100).toFixed(1)),
        backgroundColor: data.map(d => d.win_rate >= 0.55 ? '#22c55e' : d.win_rate >= 0.45 ? '#facc15' : '#ef4444') }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: {display:false} },
      scales: { x: {min:0, max:100, grid:{color:'#1e2d45'}, ticks:{color:'#94a3b8', font:{size:11}}},
                y: {grid:{display:false}, ticks:{color:'#94a3b8', font:{size:11}}} }
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
  const ROLE_CSS = { Tank: 'tank-card', Damage: 'damage-card', Support: 'support-card', 'Open Queue': 'open-card' };
  const div = document.createElement('div');
  div.id = 'rank-cards';
  div.innerHTML = ranks.map(r =>
    `<div class="stat-card ${ROLE_CSS[r.role] || ''}">
       <div class="label">${r.role}</div>
       <div class="value">${r.rank_tier} ${r.rank_division}</div>
     </div>`
  ).join('');
  el.after(div);
}

function heroSlug(name) { return (name || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
function getHeroRole(heroName) {
  const slug  = heroSlug(heroName);
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
  const sorted = [...baselineData].sort((a, b) => {
    let av = a[baselineSortCol], bv = b[baselineSortCol];
    if (baselineSortCol === 'hero') { av = av || ''; bv = bv || ''; }
    else { av = av ?? -1; bv = bv ?? -1; }
    if (av < bv) return baselineSortDir === 'asc' ? -1 : 1;
    if (av > bv) return baselineSortDir === 'asc' ?  1 : -1;
    return 0;
  });
  const ROLE_ORDER = ['Tank','Damage','Support','Unknown'];
  const ROLE_RC    = { Tank:'tank', Damage:'dps', Support:'support', Unknown:'unknown' };
  const grouped    = {};
  ROLE_ORDER.forEach(r => grouped[r] = []);
  sorted.forEach(h => { const role = getHeroRole(h.hero); (grouped[role] || grouped['Unknown']).push(h); });
  const arrow = col => {
    if (col !== baselineSortCol) return '<span style="color:var(--dim)">⇅</span>';
    return baselineSortDir === 'asc' ? '↑' : '↓';
  };
  const cols = [
    { key:'hero',         label:'Hero' },
    { key:'playtime_pct', label:'Playtime' },
    { key:'games_played', label:'Games' },
    { key:'win_rate',     label:'Win Rate' },
  ];
  let html = `<table><thead><tr>${cols.map(c =>
    `<th style="cursor:pointer;user-select:none;white-space:nowrap" data-col="${c.key}">${c.label} ${arrow(c.key)}</th>`
  ).join('')}</tr></thead><tbody>`;
  ROLE_ORDER.forEach(role => {
    const rows = grouped[role];
    if (!rows || !rows.length) return;
    const rc = ROLE_RC[role] || 'unknown';
    html += `<tr class="role-row ${rc}"><td colspan="4">${role}</td></tr>`;
    rows.forEach(h => {
      html += `<tr>
        <td>${h.hero}</td>
        <td class="num">${(h.playtime_pct||0).toFixed(1)}%</td>
        <td class="num">${h.games_played||'—'}</td>
        <td><span class="${h.win_rate != null ? wrClass(h.win_rate) : ''}">${h.win_rate != null ? pct(h.win_rate) : '—'}</span></td>
      </tr>`;
    });
  });
  html += '</tbody></table>';
  el.innerHTML = html;
  el.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (col === baselineSortCol) baselineSortDir = baselineSortDir === 'desc' ? 'asc' : 'desc';
      else { baselineSortCol = col; baselineSortDir = col === 'hero' ? 'asc' : 'desc'; }
      renderBaselineSorted();
    });
  });
}

// ── HISTORY ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  const map     = document.getElementById('h-map-filter').value;
  const outcome = document.getElementById('h-outcome-filter').value;
  const hero    = document.getElementById('h-hero-filter').value;
  const params  = new URLSearchParams();
  if (map)     params.set('map', map);
  if (outcome) params.set('outcome', outcome);
  if (hero)    params.set('hero', hero);
  const data  = await api.get('/api/matches?' + params);
  const listEl = document.getElementById('history-list');

  if (!data.matches.length) {
    listEl.innerHTML = '<div class="empty"><h3>No matches yet</h3><p>Log a game or drop a screenshot into your inbox folder to get started.</p></div>';
    return;
  }

  listEl.innerHTML = data.matches.map(m => renderMatchCard(m)).join('');

  listEl.querySelectorAll('.match-card-header').forEach(header => {
    header.addEventListener('click', () => {
      header.closest('.match-card').classList.toggle('expanded');
    });
  });
}

function renderMatchCard(m) {
  const myH    = JSON.parse(m.my_heroes    || '[]');
  const enemyH = JSON.parse(m.enemy_heroes || '[]');
  const bans   = JSON.parse(m.bans         || '[]');
  const date   = new Date(m.played_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  const oc     = m.outcome === 'Win' ? 'win' : m.outcome === 'Loss' ? 'loss' : 'draw';

  // Heroes — role-colored names
  const heroStr = myH.map(h => {
    const rc     = roleClass(getHeroRole(h.hero));
    const pctStr = myH.length > 1 ? ` <span style="color:var(--dim);font-size:11px">${h.pct}%</span>` : '';
    return `<span style="color:var(--${rc === 'unknown' ? 'muted' : rc})">${h.hero}${pctStr}</span>`;
  }).join('<span style="color:var(--dim)"> · </span>') || '—';

  // KDA compact
  const kda = [m.elims != null ? `${m.elims}E` : null, m.deaths != null ? `${m.deaths}D` : null, m.assists != null ? `${m.assists}A` : null].filter(Boolean).join('/');

  // Rank chip
  const rankHtml = m.rank_tier
    ? `<span class="match-card-sr">${m.rank_tier} ${m.rank_division}${m.rank_pct != null ? ' · ' + m.rank_pct + '%' : ''}</span>`
    : '';

  // Expanded body
  const statsHtml   = buildStatsRow(m);
  const enemyStr    = enemyH.map(h => h.hero).join(', ') || '—';
  const bansHtml    = bans.length ? `<div><div class="section-label">Bans</div><div style="font-size:13px">${bans.join(', ')}</div></div>` : '';
  const stackHtml   = m.stack_size > 1 ? `<div><div class="section-label">Stack</div><div style="font-size:13px">×${m.stack_size}</div></div>` : '';
  const notesHtml   = m.notes ? `<div style="margin-top:12px;font-size:13px;color:var(--muted);border-left:2px solid var(--border);padding-left:10px">${m.notes}</div>` : '';
  const pracDot     = m.practiced ? { Y: 'practiced-y', 'Sort of': 'practiced-so', N: 'practiced-n' }[m.practiced] || '' : '';
  const pracHtml    = m.practiced
    ? `<div style="display:flex;align-items:center;gap:6px;margin-top:10px"><span class="practiced-dot ${pracDot}"></span><span style="font-size:12px;color:var(--muted)">Goal focus: ${m.practiced}${m.practice_notes ? ' — ' + m.practice_notes : ''}</span></div>`
    : '';

  return `<div class="match-card ${oc}" id="mc-${m.id}">
    <div class="match-card-header">
      <span class="match-card-outcome outcome-${m.outcome}">${m.outcome}</span>
      <span class="match-card-map">${m.map}</span>
      <span class="match-card-heroes">${heroStr}</span>
      ${kda ? `<span class="match-card-kda">${kda}</span>` : ''}
      <span style="font-size:12px;color:var(--dim);flex-shrink:0;white-space:nowrap">${date}</span>
      ${rankHtml}
      <span class="match-card-chevron">▼</span>
    </div>
    <div class="match-card-body">
      ${statsHtml}
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-top:14px">
        <div>
          <div class="section-label">Enemy Comp</div>
          <div style="font-size:13px">${m.enemy_comp || '—'}</div>
          <div style="font-size:12px;color:var(--dim);margin-top:2px">${enemyStr}</div>
        </div>
        ${bansHtml}
        ${stackHtml}
      </div>
      ${notesHtml}
      ${pracHtml}
      <div style="display:flex;gap:8px;margin-top:16px">
        <button class="btn btn-secondary btn-sm" onclick="openEditMatch(${m.id})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteMatch(${m.id})">Delete</button>
      </div>
    </div>
  </div>`;
}

function buildStatsRow(m) {
  const stats = [
    { label: 'Elims',      value: m.elims      != null ? m.elims                : null },
    { label: 'Deaths',     value: m.deaths     != null ? m.deaths               : null },
    { label: 'Assists',    value: m.assists    != null ? m.assists               : null },
    { label: 'Damage',     value: m.damage     != null ? numFmt(m.damage)        : null },
    { label: 'Healing',    value: m.healing    != null ? numFmt(m.healing)       : null },
    { label: 'Mitigation', value: m.mitigation != null ? numFmt(m.mitigation)    : null },
  ].filter(s => s.value != null);
  if (!stats.length) return '';
  return `<div class="stat-strip">${stats.map(s =>
    `<div class="stat-strip-item"><div class="stat-strip-label">${s.label}</div><div class="stat-strip-value">${s.value}</div></div>`
  ).join('')}</div>`;
}

document.getElementById('h-filter-btn').addEventListener('click', loadHistory);

async function deleteMatch(id) {
  if (!confirm('Delete this match?')) return;
  await api.delete(`/api/matches/${id}`);
  loadHistory();
}

// ── ANALYTICS ─────────────────────────────────────────────────────────────────
// ── ANALYTICS HELPERS ─────────────────────────────────────────────────────────
function aBarColor(wr) {
  if (wr >= 0.55) return 'var(--win)';
  if (wr >= 0.45) return 'var(--gold)';
  return 'var(--loss)';
}

function renderARow({ label, sub, wr, barFrac, barColor, gamesStr, conf, extra }) {
  const frac  = barFrac != null ? barFrac : (wr ?? 0);
  const barW  = Math.round(Math.min(frac, 1) * 100);
  const color = barColor ?? (wr != null ? aBarColor(wr) : 'var(--accent)');
  const valStr = wr != null ? pct(wr) : '';
  const valCls = wr != null ? wrClass(wr) : '';
  return `<div class="a-row">
    <span class="a-label">${label}</span>
    ${sub ? `<span class="a-sub">${sub}</span>` : ''}
    <span class="a-bar-wrap"><span class="a-bar" style="width:${barW}%;background:${color}"></span></span>
    ${valStr ? `<span class="a-pct ${valCls}">${valStr}</span>` : '<span class="a-pct"></span>'}
    ${gamesStr ? `<span class="a-games">${gamesStr}</span>` : '<span class="a-games"></span>'}
    ${conf ? '<span class="conf-tag">low n</span>' : ''}
    ${extra ?? ''}
  </div>`;
}

function aEmpty(msg) {
  return `<div class="empty" style="padding:20px 0"><p>${msg}</p></div>`;
}

// ── ANALYTICS ─────────────────────────────────────────────────────────────────
const analyticsLoaded = {};
async function loadAnalyticsTab(tab) {
  if (analyticsLoaded[tab]) return;
  analyticsLoaded[tab] = true;

  if (tab === 'a-heroes') {
    const data = await api.get('/api/analytics/hero-winrates');
    if (!data.length) {
      ['a-heroes-conc-body','a-heroes-wr-body'].forEach(id => document.getElementById(id).innerHTML = aEmpty('No games logged yet.'));
      document.getElementById('a-heroes-conc-ans').textContent = '';
      document.getElementById('a-heroes-wr-ans').textContent   = '';
      return;
    }
    const totalW  = data.reduce((s, h) => s + h.weighted_games, 0);
    const byUsage = [...data].sort((a, b) => b.weighted_games - a.weighted_games);
    const topPct  = totalW > 0 ? Math.round(byUsage[0].weighted_games / totalW * 100) : 0;

    document.getElementById('a-heroes-conc-ans').textContent = topPct >= 60
      ? `One-trick risk — ${byUsage[0].hero} is ${topPct}% of your playtime.`
      : topPct >= 40
        ? `Main lean — ${byUsage[0].hero} at ${topPct}% across a pool of ${data.length}.`
        : `Diversified pool of ${data.length} heroes, top at ${topPct}%.`;

    document.getElementById('a-heroes-conc-body').innerHTML = byUsage.map(h => {
      const usagePct = totalW > 0 ? h.weighted_games / totalW : 0;
      return renderARow({
        label: h.hero,
        sub: `${Math.round(h.weighted_games)}G`,
        barFrac: usagePct,
        barColor: 'var(--accent)',
        gamesStr: `${Math.round(usagePct * 100)}%`,
        conf: h.weighted_games < 5,
      });
    }).join('');

    const byWR = [...data].sort((a, b) => b.win_rate - a.win_rate);
    const qual  = byWR.filter(h => h.weighted_games >= 3);
    document.getElementById('a-heroes-wr-ans').textContent = qual.length < 2
      ? 'Need 3+ games per hero to compare win rates.'
      : `Best: ${qual[0].hero} (${pct(qual[0].win_rate)}). Worst: ${qual[qual.length-1].hero} (${pct(qual[qual.length-1].win_rate)}).`;

    document.getElementById('a-heroes-wr-body').innerHTML = byWR.map(h =>
      renderARow({ label: h.hero, sub: h.weighted_games >= 3 ? null : '', wr: h.win_rate, gamesStr: Math.round(h.weighted_games)+'G', conf: h.weighted_games < 5 })
    ).join('');
  }

  if (tab === 'a-maps') {
    const data = await api.get('/api/analytics/map-winrates');
    if (!data.length) { document.getElementById('a-maps-body').innerHTML = aEmpty('No map data yet.'); return; }
    const sorted = [...data].sort((a, b) => b.win_rate - a.win_rate);
    const qual   = sorted.filter(m => m.games >= 3);
    document.getElementById('a-maps-ans').textContent = qual.length < 2
      ? 'Need more variety to compare maps.'
      : `Best: ${qual[0].map} (${pct(qual[0].win_rate)}). Worst: ${qual[qual.length-1].map} (${pct(qual[qual.length-1].win_rate)}).`;
    document.getElementById('a-maps-body').innerHTML = sorted.map(m =>
      renderARow({ label: m.map, sub: m.game_mode, wr: m.win_rate, gamesStr: m.games+'G', conf: m.games < 5 })
    ).join('');
  }

  if (tab === 'a-comp') {
    const data = await api.get('/api/analytics/comp-matchups');
    if (!data.length) { document.getElementById('a-comp-body').innerHTML = aEmpty('No matchup data yet.'); return; }
    // Aggregate to enemy-archetype grain
    const agg = {};
    data.forEach(r => {
      if (!agg[r.enemy_comp]) agg[r.enemy_comp] = { wins: 0, games: 0 };
      agg[r.enemy_comp].wins  += Math.round(r.win_rate * r.games);
      agg[r.enemy_comp].games += r.games;
    });
    const aggArr = Object.entries(agg)
      .map(([ec, { wins, games }]) => ({ enemy_comp: ec, win_rate: wins / games, games }))
      .sort((a, b) => a.win_rate - b.win_rate);
    const worst = aggArr[0];
    document.getElementById('a-comp-ans').textContent =
      `Hardest matchup: vs ${worst.enemy_comp} (${pct(worst.win_rate)}, ${worst.games} games).`;
    document.getElementById('a-comp-body').innerHTML = aggArr.map(r =>
      renderARow({ label: `vs ${r.enemy_comp}`, wr: r.win_rate, gamesStr: r.games+'G', conf: r.games < 5 })
    ).join('');
  }

  if (tab === 'a-enemy') {
    const [vhData, hmData] = await Promise.all([
      api.get('/api/analytics/vs-enemy-hero'),
      api.get('/api/analytics/hero-map'),
    ]);
    if (!vhData.length) {
      document.getElementById('a-enemy-body').innerHTML = aEmpty('No vs-hero data yet.');
    } else {
      const sorted  = [...vhData].sort((a, b) => a.win_rate - b.win_rate);
      const qual    = sorted.filter(r => r.games >= 3);
      const nemesis = qual[0] ?? sorted[0];
      document.getElementById('a-enemy-ans').textContent =
        `Nemesis: ${nemesis.enemy_hero} — you win ${pct(nemesis.win_rate)} in ${nemesis.games} games.`;
      document.getElementById('a-enemy-body').innerHTML = sorted.map(r =>
        renderARow({ label: r.enemy_hero, wr: r.win_rate, gamesStr: r.games+'G', conf: r.games < 5 })
      ).join('');
    }
    if (!hmData.length) {
      document.getElementById('a-heromap-body').innerHTML = aEmpty('No hero × map data yet.');
    } else {
      const sorted = [...hmData].sort((a, b) => b.win_rate - a.win_rate).slice(0, 25);
      const top    = sorted[0];
      document.getElementById('a-heromap-ans').textContent =
        `Best combo: ${top.hero} on ${top.map} (${pct(top.win_rate)}, ${Math.round(top.weighted_games)}G).`;
      document.getElementById('a-heromap-body').innerHTML = sorted.map(r =>
        renderARow({ label: `${r.hero} on ${r.map}`, sub: r.comp_affinity, wr: r.win_rate, gamesStr: Math.round(r.weighted_games)+'G', conf: r.weighted_games < 5 })
      ).join('');
    }
  }

  if (tab === 'a-teammates') {
    const data = await api.get('/api/analytics/teammate-winrates');
    if (!data.length) { document.getElementById('a-teammates-body').innerHTML = aEmpty('No consistent teammate data yet.'); return; }
    const sorted = [...data].sort((a, b) => b.win_rate - a.win_rate);
    const qual   = sorted.filter(r => r.games >= 3);
    document.getElementById('a-teammates-ans').textContent = !qual.length
      ? 'Need 3+ shared games to rank teammates.'
      : `Best synergy: ${qual[0].player} (${pct(qual[0].win_rate)}, ${qual[0].games} games).`;
    document.getElementById('a-teammates-body').innerHTML = sorted.map(r =>
      renderARow({ label: r.player, sub: r.alias || null, wr: r.win_rate, gamesStr: r.games+'G', conf: r.games < 5 })
    ).join('');
  }

  if (tab === 'a-bans') {
    const data = await api.get('/api/analytics/ban-stats');
    if (!data.length) { document.getElementById('a-bans-body').innerHTML = aEmpty('No ban data recorded yet.'); return; }
    const sorted = [...data].sort((a, b) => b.ban_count - a.ban_count);
    const top    = sorted[0];
    document.getElementById('a-bans-ans').textContent =
      `Most banned: ${top.hero} (${top.ban_count}×). Your WR with them banned: ${pct(top.win_rate_when_banned)}.`;
    const maxBans = sorted[0].ban_count;
    document.getElementById('a-bans-body').innerHTML = sorted.map(r =>
      renderARow({
        label: r.hero,
        sub: `${pct(r.ban_rate)} ban rate`,
        barFrac: r.ban_count / maxBans,
        barColor: 'var(--accent)',
        wr: r.win_rate_when_banned,
        gamesStr: r.ban_count+'×',
        extra: `<span class="a-pct ${wrClass(r.win_rate_when_banned)}" style="width:auto;margin-left:4px">${pct(r.win_rate_when_banned)} WR</span>`,
      })
    ).join('');
  }

  if (tab === 'a-stack') {
    const data = await api.get('/api/analytics/stack-winrates');
    if (!data.length) { document.getElementById('a-stack-body').innerHTML = aEmpty('No stack data yet.'); return; }
    const best = [...data].sort((a, b) => b.win_rate - a.win_rate)[0];
    const solo = data.find(r => r.label === 'Solo' || r.label === '1');
    document.getElementById('a-stack-ans').textContent = best.label === (solo?.label)
      ? `You perform best solo (${pct(best.win_rate)}).`
      : `Stack of ${best.label} gives your best win rate at ${pct(best.win_rate)}.${solo ? ` Solo: ${pct(solo.win_rate)}.` : ''}`;
    document.getElementById('a-stack-body').innerHTML = data.map(r =>
      renderARow({ label: r.label, wr: r.win_rate, gamesStr: r.games+'G', conf: r.games < 5 })
    ).join('');
  }
}

// ── QUEUE ─────────────────────────────────────────────────────────────────────
async function checkQueue() {
  const data  = await api.get('/api/queue');
  const n     = data.queue.length;
  const badge = document.getElementById('queue-badge');
  badge.textContent    = n;
  badge.style.display  = n > 0 ? 'inline' : 'none';
  if (activeSession) updateQueueHint();
}

document.getElementById('q-parse-btn').addEventListener('click', async () => {
  const path = document.getElementById('q-manual-path').value.trim();
  const msg  = document.getElementById('q-parse-msg');
  if (!path) { msg.textContent = 'Enter a file path.'; msg.style.color = 'var(--loss)'; return; }
  msg.textContent = 'Parsing…'; msg.style.color = 'var(--muted)';
  const result = await api.post('/api/queue/parse-file', { path });
  if (result.ok) {
    msg.textContent = 'Parsed — check the queue below.';
    msg.style.color = 'var(--win)';
    loadQueue();
    checkQueue();
  } else {
    msg.textContent = result.detail || 'Error parsing file.';
    msg.style.color = 'var(--loss)';
  }
});

async function loadQueue() {
  const data    = await api.get('/api/queue');
  const emptyEl = document.getElementById('queue-empty');
  const listEl  = document.getElementById('queue-list');
  if (!data.queue.length) { emptyEl.style.display = 'flex'; listEl.innerHTML = ''; return; }
  emptyEl.style.display = 'none';
  listEl.innerHTML = data.queue.map((item, i) => {
    const p        = item.parsed || {};
    const tabType  = p.tab_type || '';
    const tabClass = tabType.toLowerCase() || 'unknown';
    const tabBadge = tabType ? `<span class="tab-badge ${tabClass}">${tabType}</span>` : '';

    let detailHtml = '';
    if (tabType === 'SUMMARY') {
      const len = p.game_length_s
        ? Math.floor(p.game_length_s / 60) + ':' + String(p.game_length_s % 60).padStart(2, '0')
        : '—';
      const dt  = p.played_at ? new Date(p.played_at).toLocaleString() : '—';
      const heroes = (p.my_heroes || []).map(h => h.hero).join(', ') || '—';
      detailHtml = `<div class="queue-item-detail">
        <strong>${p.map || '—'}</strong>
        &nbsp;·&nbsp; <span class="outcome-${p.outcome}">${p.outcome || '—'}</span>
        &nbsp;·&nbsp; ${len} &nbsp;·&nbsp; ${dt}
        ${heroes !== '—' ? `<br><span style="font-size:12px;color:var(--dim)">Heroes: ${heroes}</span>` : ''}
      </div>`;
    } else if (tabType === 'TEAM') {
      const stats = ['elims','assists','deaths','damage','healing','mitigation']
        .map(k => p[k] != null ? `${k[0].toUpperCase() + k.slice(1, 3)}: <strong>${p[k]}</strong>` : null)
        .filter(Boolean).join(' &nbsp;·&nbsp; ');
      const heroes = (p.my_heroes || []).map(h => h.hero).join(', ') || '—';
      detailHtml = `<div class="queue-item-detail">
        ${stats || 'No stats parsed'}
        <br><span style="font-size:12px;color:var(--dim)">Heroes: ${heroes}</span>
      </div>`;
    } else if (tabType === 'PERSONAL') {
      const hero = (p.my_heroes || [])[0]?.hero || '—';
      detailHtml = `<div class="queue-item-detail">Detected hero: <strong>${hero}</strong> · Hero-specific stats not yet parsed.</div>`;
    } else {
      detailHtml = `<div class="queue-item-detail" style="color:var(--dim)">Could not detect tab type.</div>`;
    }

    const warnings = (p.warnings || []).filter(w => !w.startsWith('Map and outcome'));
    return `<div class="card" style="margin-bottom:10px">
      <div class="queue-item-header">
        <span class="queue-item-filename">${item.filename}</span>${tabBadge}
      </div>
      ${item.error ? `<div class="alert alert-warn">Parse error: ${item.error}</div>` : ''}
      ${warnings.map(w => `<div class="alert alert-warn">${w}</div>`).join('')}
      ${detailHtml}
      <div class="queue-item-actions">
        <button class="btn btn-primary btn-sm" onclick="confirmQueueItem(${i})">Confirm &amp; Edit</button>
        <button class="btn btn-danger btn-sm"  onclick="discardQueueItem('${item.filename}', ${i})">Discard</button>
      </div>
    </div>`;
  }).join('');
}

async function confirmQueueItem(idx) {
  const data = await api.get('/api/queue');
  const item = data.queue[idx];
  if (!item) return;
  const p = { ...(item.parsed || {}), _queueFilename: item.filename };
  openGameModal(p, false);
}

async function discardQueueItem(filename) {
  await api.delete(`/api/queue/${encodeURIComponent(filename)}`);
  loadQueue();
  checkQueue();
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
let settingsData = {};
async function loadSettings() {
  settingsData = await api.get('/api/settings');
  document.getElementById('s-battletag').value = settingsData.battletag || '';
  document.getElementById('s-username').value  = settingsData.username  || '';
  document.getElementById('s-inbox').value     = settingsData.inbox_folder || '';
  renderTrackedPlayers();
  loadMapConfig();
}

function renderTrackedPlayers() {
  const el      = document.getElementById('tracked-list');
  const players = settingsData.tracked_players || [];
  el.innerHTML  = players.map(p =>
    `<div class="tracked-player-row">
       <span class="tracked-player-name">${p.name}</span>
       <span class="tracked-player-alias">${p.alias || ''}</span>
       <button class="btn btn-secondary btn-sm" onclick="removeTrackedPlayer('${p.name}')">✕</button>
     </div>`
  ).join('') || '<p style="color:var(--muted);font-size:13px">No tracked players yet.</p>';
}

async function saveSettings() {
  settingsData.battletag    = document.getElementById('s-battletag').value;
  settingsData.username     = document.getElementById('s-username').value;
  settingsData.inbox_folder = document.getElementById('s-inbox').value;
  return api.put('/api/settings', settingsData);
}

document.getElementById('s-save-btn').addEventListener('click', async () => {
  const msg = document.getElementById('s-msg');
  const result = await saveSettings();
  msg.textContent = result.ok ? 'Saved.' : 'Error saving.';
  msg.style.color = result.ok ? 'var(--win)' : 'var(--loss)';
});

document.getElementById('s-restart-btn').addEventListener('click', async () => {
  const msg = document.getElementById('s-msg');
  msg.textContent = 'Saving…';
  msg.style.color = 'var(--muted)';
  const saveResult = await saveSettings();
  if (!saveResult.ok) { msg.textContent = 'Error saving settings.'; msg.style.color = 'var(--loss)'; return; }
  const restartResult = await api.post('/api/watcher/restart', {});
  msg.textContent = restartResult.ok
    ? `Saved. Watcher restarted → ${settingsData.inbox_folder}`
    : 'Saved, but watcher restart failed.';
  msg.style.color = restartResult.ok ? 'var(--win)' : 'var(--gold)';
});

document.getElementById('s-add-player-btn').addEventListener('click', () => {
  const name  = document.getElementById('s-player-name').value.trim();
  const alias = document.getElementById('s-player-alias').value.trim();
  if (!name) return;
  if (!settingsData.tracked_players) settingsData.tracked_players = [];
  if (!settingsData.tracked_players.find(p => p.name === name)) settingsData.tracked_players.push({name, alias});
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
  tbody.innerHTML = maps.map(m => {
    const current = (m.comp_affinity || 'Neutral').split('|');
    const boxes   = ['Dive','Poke','Brawl'].map(a =>
      `<label style="margin-right:10px;white-space:nowrap">
         <input type="checkbox" value="${a}"${current.includes(a) ? ' checked' : ''}> ${a}</label>`
    ).join('');
    return `<tr>
       <td>${m.name}</td><td style="color:var(--muted)">${m.game_mode}</td>
       <td>${boxes}<span style="color:var(--muted);font-size:12px">none = Neutral</span></td>
       <td><button class="btn btn-secondary btn-sm" data-map="${m.name}" onclick="saveMapAffinity(this)">Save</button></td>
     </tr>`;
  }).join('');
}

async function saveMapAffinity(btn) {
  const mapName = btn.dataset.map;
  const checked = [...btn.closest('tr').querySelectorAll('input[type=checkbox]:checked')].map(c => c.value);
  const affinity = checked.length ? checked.join('|') : 'Neutral';
  await api.put(`/api/maps/${encodeURIComponent(mapName)}`, {comp_affinity: affinity});
  maps = await api.get('/api/maps');
  Object.keys(analyticsLoaded).forEach(k => delete analyticsLoaded[k]);
}

document.getElementById('baseline-fetch-btn').addEventListener('click', async () => {
  const btn = document.getElementById('baseline-fetch-btn');
  const msg = document.getElementById('baseline-msg');
  btn.disabled    = true;
  msg.textContent = 'Fetching…';
  try {
    const result    = await api.post('/api/baseline/fetch', {});
    msg.textContent = `Fetched ${result.heroes_fetched || 0} heroes.`;
    msg.style.color = 'var(--win)';
  } catch(e) {
    msg.textContent = 'Error: ' + e.message;
    msg.style.color = 'var(--loss)';
  } finally {
    btn.disabled = false;
  }
});

// ── BOOT ──────────────────────────────────────────────────────────────────────
init();
