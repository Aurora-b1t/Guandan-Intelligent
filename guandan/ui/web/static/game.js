/* ================================================================
   Guandan Web UI — Frontend Logic
   ================================================================ */

let gameState = null;
let selectedCards = new Set();       // card IDs selected in main hand
let activeStrip = null;              // index of selected combo strip (or null)
let debugMode = true;                // default ON
let flatLayout = false;              // false = vertical columns, true = horizontal
let comboStrips = [];                // [{cardIds: [id,...]}, ...]
let aiDebugOpen = false;             // AI debug panel
let pollTimer = null;                // polling interval ID

const SUIT_CHARS = {0: '♣', 1: '♦', 2: '♥', 3: '♠', 4: ''};
const SUIT_NAMES = {0: 'C', 1: 'D', 2: 'H', 3: 'S', 4: ''};
const PLAYER_NAMES = ['你', 'AI-右家', 'AI-对家', 'AI-左家'];

// ==================================================================
// API
// ==================================================================

async function fetchState() {
  const r = await fetch('/api/state');
  gameState = await r.json();
  render();
  if (debugMode) fetchDebug();
  if (aiDebugOpen) fetchAILog();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const r = await fetch('/api/state');
    gameState = await r.json();
    render();
    if (debugMode) fetchDebug();
    if (aiDebugOpen) fetchAILog();
    if (gameState.my_turn || gameState.game_over || gameState.round_over) {
      stopPolling();
    }
  }, 400);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function playCards() {
  if (!myTurn) return;
  let cardIds;

  if (activeStrip !== null && activeStrip < comboStrips.length) {
    cardIds = comboStrips[activeStrip].cardIds;
  } else if (selectedCards.size > 0) {
    cardIds = Array.from(selectedCards);
  } else {
    return;
  }

  const r = await fetch('/api/play', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({card_ids: cardIds}),
  });
  gameState = await r.json();
  selectedCards.clear();
  activeStrip = null;
  if (cardIds) {
    const playedSet = new Set(cardIds);
    comboStrips = comboStrips.filter(s => {
      s.cardIds = s.cardIds.filter(id => !playedSet.has(id));
      return s.cardIds.length > 0;
    });
  }
  // Auto-close suggestion panel after playing
  document.getElementById('suggest-panel').style.display = 'none';
  render();
  if (debugMode) fetchDebug();
}

async function passTurn() {
  if (!myTurn) return;
  const r = await fetch('/api/pass', {method: 'POST'});
  gameState = await r.json();
  selectedCards.clear();
  activeStrip = null;
  document.getElementById('suggest-panel').style.display = 'none';
  render();
  if (debugMode) fetchDebug();
}

async function newGame() {
  const r = await fetch('/api/new_game', {method: 'POST'});
  gameState = await r.json();
  selectedCards.clear();
  activeStrip = null;
  comboStrips = [];
  render();
  if (debugMode) fetchDebug();
}

async function newRound() {
  const r = await fetch('/api/new_round', {method: 'POST'});
  gameState = await r.json();
  selectedCards.clear();
  activeStrip = null;
  comboStrips = [];
  render();
  if (debugMode) fetchDebug();
}

async function showHint() {
  if (!myTurn || !gameState) return;
  const r = await fetch('/api/hint');
  const data = await r.json();
  selectedCards.clear();
  activeStrip = null;
  if (data.card_ids) {
    for (const id of data.card_ids) selectedCards.add(id);
  }
  render();
}

async function fetchDebug() {
  const r = await fetch('/api/debug');
  const data = await r.json();
  if (data.hands) renderDebugHands(data.hands);
}

// ==================================================================
// Combo organizer
// ==================================================================

function organizeCombo() {
  if (selectedCards.size === 0) return;
  const cardIds = Array.from(selectedCards);
  comboStrips.push({cardIds: cardIds});
  selectedCards.clear();
  activeStrip = comboStrips.length - 1;
  render();
}

function selectStrip(index) {
  if (activeStrip === index) {
    // Deselect
    activeStrip = null;
  } else {
    activeStrip = index;
    selectedCards.clear();
  }
  render();
}

function removeStrip(index) {
  comboStrips.splice(index, 1);
  if (activeStrip === index) activeStrip = null;
  else if (activeStrip > index) activeStrip--;
  render();
}

// ==================================================================
// Layout toggle
// ==================================================================

function toggleLayout() {
  flatLayout = !flatLayout;
  const btn = document.getElementById('btn-layout');
  btn.textContent = flatLayout ? '纵排' : '横排';
  render();
}

// ==================================================================
// Debug toggle
// ==================================================================

function toggleDebug() {
  debugMode = !debugMode;
  const btn = document.getElementById('btn-debug');
  btn.className = debugMode ? '' : 'off';
  btn.textContent = debugMode ? '隐藏牌面' : '显示牌面';

  if (debugMode) {
    fetchDebug();
  } else {
    for (let p = 0; p < 4; p++) {
      const el = document.getElementById('debug-hand-' + p);
      if (el) el.style.display = 'none';
    }
  }
}

// ==================================================================
// Render
// ==================================================================

function render() {
  if (!gameState) return;
  myTurn = gameState.my_turn;

  document.getElementById('info-level').textContent = gameState.level;
  document.getElementById('info-round').textContent = gameState.round;
  document.getElementById('info-trick').textContent = gameState.trick;
  document.getElementById('info-team0').textContent = gameState.team_level_0 || gameState.level;
  document.getElementById('info-team1').textContent = gameState.team_level_1 || gameState.level;

  for (let p = 0; p < 4; p++) {
    const info = gameState.players[p];
    document.getElementById('size-' + p).textContent = info.hand_size;
    const ft = document.getElementById('finish-' + p);
    ft.style.display = info.finished ? 'inline' : 'none';
    const zone = document.getElementById('zone-' + p);
    zone.classList.toggle('finished', info.finished);
    // Highlight thinking AI
    const thinking = gameState.ai_thinking_player;
    zone.classList.toggle('thinking-zone', thinking >= 0 && thinking === p);
  }

  renderTrickHistory(gameState.trick_history || []);
  renderHand(gameState.my_hand);
  renderComboStrips();

  document.getElementById('btn-play').disabled = !myTurn || (selectedCards.size === 0 && activeStrip === null);
  document.getElementById('btn-pass').disabled = !myTurn || !gameState.can_pass;
  document.getElementById('btn-hint').disabled = !myTurn;
  document.getElementById('btn-suggest').disabled = !myTurn;
  document.getElementById('btn-organize').disabled = selectedCards.size === 0;
  // Auto-play button state
  const autoBtn = document.getElementById('btn-auto-play');
  const isAuto = gameState.auto_play;
  autoBtn.textContent = isAuto ? '停止自动' : '自动对局';
  autoBtn.style.background = isAuto ? '#c0392b' : '#555';
  document.getElementById('btn-new-round').style.display =
    (gameState.round_over && !gameState.game_over) ? 'inline-block' : 'none';

  const msgEl = document.getElementById('message');
  msgEl.textContent = gameState.message || '';
  msgEl.className = gameState.error ? 'error' : '';
  if (gameState.message === 'AI思考中...' || gameState.ai_running) {
    msgEl.classList.add('thinking');
    document.getElementById('btn-play').disabled = true;
    document.getElementById('btn-pass').disabled = true;
    startPolling();
  } else if (gameState.my_turn) {
    stopPolling();
  }

  renderHistory(gameState.round_results || []);
}

function renderTrickHistory(history) {
  for (let p = 0; p < 4; p++) {
    document.getElementById('play-' + p).innerHTML = '';
  }
  if (!history || history.length === 0) return;

  for (const entry of history) {
    const zone = document.getElementById('play-' + entry.player);
    if (!zone) continue;
    if (entry.pass) {
      zone.innerHTML = '<span class="pass-text">过</span>';
    } else if (entry.combo) {
      let html = '<span class="combo-tag">' + (entry.combo.type_cn || entry.combo.type) + '</span> ';
      for (const c of entry.combo.cards) html += cardHTML(c, true);
      zone.innerHTML = html;
    }
  }
}

function renderHand(hand) {
  const container = document.getElementById('my-hand');
  container.innerHTML = '';
  container.className = flatLayout ? 'flat-layout' : '';

  if (!hand || hand.length === 0) {
    container.innerHTML = '<span style="color:#888;padding:20px">手牌已出完</span>';
    return;
  }

  // Remove cards that are in combo strips from the main hand display
  const stripCardIds = new Set();
  for (const strip of comboStrips) {
    for (const id of strip.cardIds) stripCardIds.add(id);
  }
  const displayHand = hand.filter(c => !stripCardIds.has(c.id));

  if (!flatLayout) {
    // Column layout: group by rank
    const byRank = {};
    for (const c of displayHand) {
      if (!byRank[c.rank]) byRank[c.rank] = [];
      byRank[c.rank].push(c);
    }
    const ranks = Object.keys(byRank).map(Number).sort((a, b) => a - b);

    for (const rank of ranks) {
      const cards = byRank[rank];
      cards.sort((a, b) => a.suit - b.suit);

      const col = document.createElement('div');
      col.className = 'rank-column';
      col.title = cards.length + '张 ' + cards[0].rank_name;
      col.onclick = (e) => {
        e.stopPropagation();
        const allSel = cards.every(c => selectedCards.has(c.id));
        if (allSel) cards.forEach(c => selectedCards.delete(c.id));
        else cards.forEach(c => selectedCards.add(c.id));
        activeStrip = null;
        render();
      };

      for (const c of cards) {
        col.appendChild(createCardElement(c));
      }
      container.appendChild(col);
    }
  } else {
    // Flat layout
    const sorted = [...displayHand].sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return a.suit - b.suit;
    });
    for (const c of sorted) {
      container.appendChild(createCardElement(c));
    }
  }
}

function createCardElement(c) {
  const sel = selectedCards.has(c.id) ? ' selected' : '';
  const wild = c.is_wild ? ' wild' : '';
  let suitClass;
  if (c.is_joker) {
    suitClass = c.rank_name === 'SJ' ? 'joker-black' : 'joker-red';
  } else {
    suitClass = 'suit-' + SUIT_NAMES[c.suit];
  }
  const div = document.createElement('div');
  div.className = 'card' + sel + wild + ' ' + suitClass;
  div.setAttribute('data-card-id', c.id);
  div.onclick = (e) => {
    e.stopPropagation();
    toggleCard(c.id);
  };
  div.innerHTML =
    '<span class="card-rank">' + c.rank_name + '</span>' +
    '<span class="card-suit-big">' + SUIT_CHARS[c.suit] + '</span>';
  return div;
}

function cardHTML(c, small) {
  let suitClass;
  if (c.is_joker) {
    suitClass = c.rank_name === 'SJ' ? 'joker-black' : 'joker-red';
  } else {
    suitClass = 'suit-' + SUIT_NAMES[c.suit];
  }
  const wild = c.is_wild ? ' wild' : '';
  return '<div class="card' + wild + ' ' + suitClass + '">' +
    '<span class="card-rank">' + c.rank_name + '</span>' +
    '<span class="card-suit-big">' + SUIT_CHARS[c.suit] + '</span>' +
    '</div>';
}

function renderComboStrips() {
  const container = document.getElementById('combo-strips');
  container.innerHTML = '';

  for (let i = 0; i < comboStrips.length; i++) {
    const strip = comboStrips[i];
    const selClass = (activeStrip === i) ? ' selected-strip' : '';

    // Build the strip
    const stripEl = document.createElement('div');
    stripEl.className = 'combo-strip' + selClass;
    stripEl.title = '点击选中出牌，悬停显示删除';
    stripEl.onclick = (e) => {
      e.stopPropagation();
      selectStrip(i);
    };

    // Get card objects from gameState for display
    const handMap = {};
    if (gameState && gameState.my_hand) {
      for (const c of gameState.my_hand) handMap[c.id] = c;
    }

    for (const id of strip.cardIds) {
      const c = handMap[id];
      if (c) {
        stripEl.innerHTML += cardHTML(c, true);
      }
    }

    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.className = 'strip-close';
    closeBtn.textContent = '×';
    closeBtn.onclick = (e) => {
      e.stopPropagation();
      removeStrip(i);
    };
    stripEl.appendChild(closeBtn);

    container.appendChild(stripEl);
  }
}

function renderHistory(roundResults) {
  const hist = document.getElementById('history');
  if (!roundResults || roundResults.length === 0) { hist.innerHTML = ''; return; }
  hist.innerHTML = roundResults.map((rr, i) => {
    const names = rr.positions.map(p => p.name).join(' → ');
    const winLabel = rr.winning_team === 0 ? '我方' : '对方';
    return '<span class="history-item">#' + (i + 1) + ': ' + names + ' | ' + winLabel + '+' + rr.level_change + '级</span>';
  }).join('');
}

function renderDebugHands(hands) {
  if (!hands || !debugMode) return;
  for (const h of hands) {
    const el = document.getElementById('debug-hand-' + h.player);
    if (!el) continue;
    el.style.display = 'flex';
    let html = '';
    for (const c of h.cards) html += cardHTML(c, true);
    el.innerHTML = html;
  }
}

// ==================================================================
// Interaction
// ==================================================================

function toggleCard(cardId) {
  if (!myTurn) return;
  if (selectedCards.has(cardId)) {
    selectedCards.delete(cardId);
  } else {
    selectedCards.add(cardId);
  }
  activeStrip = null;  // deselect strip when manually selecting cards
  render();
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    if (myTurn && (selectedCards.size > 0 || activeStrip !== null)) playCards();
  } else if (e.key === ' ') {
    e.preventDefault();
    if (myTurn && gameState && gameState.can_pass) passTurn();
  } else if (e.key === 'd' && e.ctrlKey) {
    e.preventDefault();
    toggleDebug();
  }
});

// ==================================================================
// AI Debug Panel
// ==================================================================

function toggleAIDebug() {
  aiDebugOpen = !aiDebugOpen;
  const panel = document.getElementById('ai-debug-panel');
  const btn = document.getElementById('btn-ai-debug');
  if (aiDebugOpen) {
    panel.classList.add('show');
    btn.classList.add('active');
    fetchAILog();
  } else {
    panel.classList.remove('show');
    btn.classList.remove('active');
  }
}

async function fetchAILog() {
  const r = await fetch('/api/ai_log');
  const data = await r.json();
  renderAILog(data);
}

async function clearAILog() {
  await fetch('/api/ai_log/clear', {method: 'POST'});
  document.getElementById('ai-debug-content').innerHTML =
    '<div style="color:#888;padding:10px">日志已清空</div>';
}

function renderAILog(data) {
  const container = document.getElementById('ai-debug-content');
  if (!data || !data.entries || data.entries.length === 0) {
    container.innerHTML = '<div style="color:#888;padding:10px">暂无AI决策记录</div>';
    return;
  }

  // Config summary line
  let configLine = '';
  if (currentConfig) {
    const labels = {heuristic:'启发式', monte_carlo:'蒙特卡洛', random:'随机'};
    configLine = '<div style="font-size:0.75em;color:#888;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid #333">全局: ' +
      (labels[currentConfig.global_model] || currentConfig.global_model);
    for (const p of [1,2,3]) {
      const pc = (currentConfig.players || {})[p] || {};
      if (pc.model) configLine += ' | ' + ['','右','对','左'][p] + '家: ' + (labels[pc.model]||pc.model);
    }
    configLine += '</div>';
  }

  // Group entries by decision cycle
  let html = '';
  let currentCycle = null;

  for (const entry of data.entries) {
    const playerName = ['你', '右AI', '对AI', '左AI'][entry.player] || 'P' + entry.player;

    if (entry.type === 'decision_start') {
      // Start a new decision block
      if (currentCycle) html += '</div>';
      html += '<div class="ai-log-entry">';
      html += '<div class="entry-header">';
      html += '<span class="entry-player">' + playerName + '</span>';
      html += '<span class="entry-type">' + (entry.data.agent || 'Heuristic') + '</span>';
      html += '<span class="entry-time">手牌' + (entry.data.hand_size || '?') + '张</span>';
      html += '</div>';
      currentCycle = entry;
    } else if (entry.type === 'candidates') {
      // Render candidate table
      const candidates = entry.data.candidates || [];
      if (candidates.length > 0) {
        html += '<table class="ai-candidates-table">';
        html += '<tr><th>牌型</th><th>牌</th><th>张数</th><th class="score-col">评分</th></tr>';
        let bestScore = -Infinity;
        for (const c of candidates) {
          if (c.score > bestScore) bestScore = c.score;
        }
        for (const c of candidates) {
          const isBest = c.score === bestScore;
          const rowClass = isBest ? 'best-row' : '';
          html += '<tr class="' + rowClass + '">';
          html += '<td>' + c.type + '</td>';
          html += '<td>' + (c.cards || []).join(' ') + '</td>';
          html += '<td>' + c.length + '</td>';
          html += '<td class="score-col">' + c.score.toFixed(1) + '</td>';
          html += '</tr>';
        }
        html += '</table>';
      }
    } else if (entry.type === 'decision_end') {
      const choice = entry.data.choice || '?';
      const elapsed = entry.data.elapsed_ms || 0;
      html += '<div style="font-size:0.75em;color:#aaa">';
      html += '选择: <b style="color:#27ae60">' + choice + '</b>';
      html += ' <span style="color:#666">(' + elapsed + 'ms)</span>';
      html += '</div>';
      if (entry.data.candidates_scored) {
        html += '<table class="ai-candidates-table">';
        html += '<tr><th>候选</th><th class="score-col">胜率</th></tr>';
        for (const c of entry.data.candidates_scored) {
          html += '<tr>';
          html += '<td>' + (c.type || '?') + ' ' + (c.cards || []).join(' ') + '</td>';
          html += '<td class="score-col">' + (c.win_rate * 100).toFixed(1) + '%</td>';
          html += '</tr>';
        }
        html += '</table>';
      }
    }
  }
  if (currentCycle) html += '</div>';

  container.innerHTML = configLine + html;
  container.scrollTop = container.scrollHeight;
}

// ==================================================================
// Auto-play toggle
// ==================================================================

async function toggleAutoPlay() {
  const btn = document.getElementById('btn-auto-play');
  const isAuto = btn.textContent.includes('停止');
  const r = await fetch('/api/auto_play', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: !isAuto}),
  });
  const d = await r.json();
  btn.textContent = d.auto_play ? '停止自动' : '自动对局';
  btn.style.background = d.auto_play ? '#c0392b' : '#555';
  if (d.auto_play) {
    selectedCards.clear();
    activeStrip = null;
    fetchState();  // will start auto-play polling
  }
}

// ==================================================================
// AI Suggestion (semi-auto human assist)
// ==================================================================

async function aiSuggest() {
  if (!myTurn || !gameState) return;
  const panel = document.getElementById('suggest-panel');
  const content = document.getElementById('suggest-content');
  panel.style.display = 'block';
  content.innerHTML = '<span style="color:#aaa">AI 正在分析...</span>';

  const r = await fetch('/api/suggest');
  const d = await r.json();
  if (!d.candidates || d.candidates.length === 0) {
    const canPass = gameState && gameState.can_pass;
    content.innerHTML = '<span style="color:#e67e22">' +
      (canPass ? '手牌中没有任何能压过牌桌的牌型，建议过牌' : '你是首家，但AI未找到合适的出牌建议') +
      '</span>';
    return;
  }

  let html = '<table style="width:100%;font-size:0.82em;border-collapse:collapse">';
  html += '<tr style="color:#999"><th>牌型</th><th>牌面</th><th style="text-align:right">胜率</th><th></th></tr>';
  let bestRate = d.candidates[0]?.win_rate || 0;
  for (const c of d.candidates.slice(0, 8)) {
    const isBest = c.win_rate === bestRate;
    const bg = isBest ? 'background:rgba(39,174,96,0.15)' : '';
    const color = isBest ? 'color:#27ae60' : 'color:#ccc';
    const rate = (c.win_rate * 100).toFixed(1) + '%';
    const cards = (c.cards || []).join(' ');
    html += `<tr style="${bg};${color};border-bottom:1px solid rgba(255,255,255,0.04)">
      <td>${c.type||'?'}</td><td>${cards}</td><td style="text-align:right;font-weight:bold">${rate}</td>
      <td style="white-space:nowrap;padding-left:12px">
        <button onclick="selectSuggested('${(c.cards||[]).join(',')}', this)" style="background:#555;color:#ccc;border:none;padding:1px 6px;border-radius:3px;cursor:pointer;font-size:0.7em">选中</button>
        <button onclick="playSuggested('${(c.cards||[]).join(',')}')" style="background:#27ae60;color:#fff;border:none;padding:1px 8px;border-radius:3px;cursor:pointer;font-size:0.75em;margin-left:2px">出牌</button>
      </td>
    </tr>`;
  }
  html += '</table>';
  content.innerHTML = html;
}

function selectSuggested(displayStrs, btnEl) {
  const displays = displayStrs.split(',');
  const hand = gameState.my_hand;
  const neededIds = [];
  const usedIds = new Set();
  for (const d of displays) {
    const card = hand.find(c => c.display === d.trim() && !usedIds.has(c.id));
    if (card) { neededIds.push(card.id); usedIds.add(card.id); }
  }
  const allSelected = neededIds.length > 0 && neededIds.every(id => selectedCards.has(id));
  if (allSelected) {
    neededIds.forEach(id => selectedCards.delete(id));
    if (btnEl) btnEl.textContent = '选中';
  } else {
    selectedCards.clear();
    neededIds.forEach(id => selectedCards.add(id));
    if (btnEl) btnEl.textContent = '取消';
  }
  render();
}

async function playSuggested(displayStrs) {
  // Always select these cards (don't toggle), then play
  const displays = displayStrs.split(',');
  selectedCards.clear();
  const hand = gameState.my_hand;
  const usedIds = new Set();
  for (const d of displays) {
    const card = hand.find(c => c.display === d.trim() && !usedIds.has(c.id));
    if (card) { selectedCards.add(card.id); usedIds.add(card.id); }
  }
  if (selectedCards.size > 0) {
    await playCards();
  }
}

// ==================================================================
// AI Evaluate (analyze currently selected cards)
// ==================================================================

async function aiEvaluate() {
  const panel = document.getElementById('suggest-panel');
  const content = document.getElementById('suggest-content');
  panel.style.display = 'block';

  const cardIds = selectedCards ? Array.from(selectedCards) : [];
  content.innerHTML = '<span style="color:#aaa">AI 分析中...</span>';

  const r = await fetch('/api/evaluate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({card_ids: cardIds}),
  });
  const d = await r.json();

  if (d.info) {
    content.innerHTML = `<span style="color:#daa520">${d.info}</span>`;
    return;
  }
  if (d.error) {
    content.innerHTML = `<span style="color:#e74c3c">${d.error}</span>`;
    return;
  }

  const rateStr = d.win_rate != null ? ` | 胜率: <b style="color:#27ae60">${(d.win_rate*100).toFixed(1)}%</b>` : '';
  const rDiff = d.rounds_before - d.rounds_after;
  content.innerHTML = `
    <div style="font-size:0.85em">
      <span style="color:#daa520">${d.combo_type}</span>
      <span> ${(d.cards||[]).join(' ')}</span>
      ${d.is_bomb ? '<span style="color:#e74c3c"> 炸弹</span>' : ''}
    </div>
    <div style="font-size:0.78em;color:#aaa;margin-top:4px">
      轮次: ${d.rounds_before} → ${d.rounds_after} (${rDiff>=0?'-'+rDiff:'+'+Math.abs(rDiff)}轮)${rateStr}
    </div>`;
}

// ==================================================================
// AI Config Panel
// ==================================================================

let configOpen = false;
let availableModels = [];
let modelDefaults = {};
let currentConfig = {};
let configTab = 'global';

function switchConfigTab(tab) {
  configTab = tab;
  document.querySelectorAll('.cfg-tab').forEach(b => b.classList.remove('active'));
  const tabBtn = document.getElementById('cfg-tab-' + tab);
  if (tabBtn) tabBtn.classList.add('active');
  ['global','p0','p1','p2','p3'].forEach(t => {
    const el = document.getElementById('cfg-tabcontent-' + t);
    if (el) el.style.display = t === tab ? 'block' : 'none';
  });
}

async function toggleConfig() {
  configOpen = !configOpen;
  const panel = document.getElementById('config-panel');
  panel.style.display = configOpen ? 'block' : 'none';
  if (configOpen) { await fetchConfig(); switchConfigTab('global'); }
}

async function fetchConfig() {
  const r = await fetch('/api/config');
  const d = await r.json();
  availableModels = d.available_models || [];
  modelDefaults = d.model_defaults || {};
  currentConfig = d.config || {};


  // Build tab content for global and each player
  buildConfigTab('global', '全局', currentConfig.global_model, null);
  for (const p of [0,1,2,3]) {
    const pc = currentConfig.players[p] || {};
    const playerNames = ['你', '右家', '对家', '左家'];
    buildConfigTab('p' + p, playerNames[p], pc.model || currentConfig.global_model, p);
  }
}

function buildConfigTab(tabId, title, model, playerId) {
  const container = document.getElementById('cfg-tabcontent-' + tabId);
  if (!container) return;
  const isGlobal = playerId === null;
  const labels = {heuristic:'启发式', monte_carlo:'蒙特卡洛', random:'随机'};
  const modelOpts = availableModels.map(m =>
    `<option value="${m}" ${model===m?'selected':''}>${labels[m]||m}</option>`
  ).join('');

  const selId = isGlobal ? 'cfg-global-model' : ('cfg-pmodel-' + playerId);
  const prefix = isGlobal ? 'g' : ('p' + playerId);
  const enabledId = isGlobal ? null : ('cfg-penabled-' + playerId);
  const isEnabled = isGlobal ? true : !!(currentConfig.players[playerId] || {}).model;

  const special = ['num_samples', 'time_limit_ms'];
  // Merge: current config values override defaults
  const defaults = modelDefaults[model] || {};
  const currentParams = isGlobal
    ? (currentConfig.global_params || {})[model] || {}
    : (currentConfig.players[playerId] || {}).params || {};
  const params = {...defaults, ...currentParams};
  const specialLabels = {num_samples:'采样次数', time_limit_ms:'时限(ms)'};

  let specialHtml = '';
  for (const [k, v] of Object.entries(params)) {
    if (!special.includes(k)) continue;
    specialHtml += `<span style="margin-right:12px;color:#daa520">${specialLabels[k]||k}:
      <input type="number" value="${v}" id="cfg-${prefix}param-${k}" style="width:60px;background:#222;color:#ddd;border:1px solid #555;border-radius:4px;padding:3px 6px;font-size:0.9em"></span>`;
  }

  const weightLabels = {
    efficiency_weight:'出牌效率', round_weight:'轮次奖励', bomb_lead_penalty:'首出炸弹罚',
    bomb_overuse_penalty:'炸弹压非炸弹罚', bomb_vs_bomb_bonus:'炸弹对炸弹奖', lead_bonus:'首家奖励',
    follow_bonus:'跟牌奖励', joker_lead_penalty:'王先出罚', high_rank_lead_penalty:'K+先出罚',
    card_usage_weight:'每张牌奖励', pass_threshold:'过牌阈值', sim_pass_prob:'模拟过牌率'
  };
  let weightHtml = '';
  for (const [k, v] of Object.entries(params)) {
    if (special.includes(k)) continue;
    const label = weightLabels[k] || k;
    weightHtml += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
      <span style="width:110px;text-align:right;font-size:0.85em">${label}</span>
      <input type="number" value="${v}" step="0.5" id="cfg-${prefix}param-${k}" style="width:56px;background:#222;color:#ccc;border:1px solid #444;border-radius:4px;padding:2px 5px;font-size:0.85em">
    </div>`;
  }

  const enabledCheckbox = !isGlobal ? `
    <label style="color:#aaa;font-size:0.85em;margin-right:10px;cursor:pointer">
      <input type="checkbox" id="${enabledId}" ${isEnabled?'checked':''} onchange="onPlayerEnabledChange(${playerId})"> 启用独立配置
    </label>` : '';

  container.innerHTML = `
    ${enabledCheckbox}
    <div style="margin-bottom:8px">
      <span style="color:#aaa;margin-right:8px">模型:</span>
      <select id="${selId}" onchange="onTabModelChange('${tabId}',${playerId})" style="background:#222;color:#ddd;border:1px solid #444;padding:4px 10px;border-radius:4px;font-size:0.9em">
        ${isGlobal ? '' : '<option value="">(全局)</option>'}
        ${modelOpts}
      </select>
      ${specialHtml}
    </div>
    <div style="color:#aaa;font-size:0.85em">${weightHtml}</div>`;
}

function onPlayerEnabledChange(playerId) {
  const cb = document.getElementById('cfg-penabled-' + playerId);
  const sel = document.getElementById('cfg-pmodel-' + playerId);
  if (!cb || !sel) return;
  if (!cb.checked) {
    sel.value = '';
    onTabModelChange('p' + playerId, playerId);
  }
}

function onTabModelChange(tabId, playerId) {
  const isGlobal = playerId === null;
  const selId = isGlobal ? 'cfg-global-model' : ('cfg-pmodel-' + playerId);
  const model = document.getElementById(selId).value;
  const playerNames = ['你', '右家', '对家', '左家'];
  const title = isGlobal ? '全局' : playerNames[playerId];
  buildConfigTab(tabId, title, model, playerId);
}

async function applyConfig() {
  const data = {
    global_model: document.getElementById('cfg-global-model').value,
    global_params: {},
    players: {},
  };

  const gModel = data.global_model;
  const gDefaults = modelDefaults[gModel] || {};
  data.global_params[gModel] = {};
  for (const k of Object.keys(gDefaults)) {
    const el = document.getElementById('cfg-gparam-' + k);
    if (el) data.global_params[gModel][k] = parseFloat(el.value) ?? gDefaults[k];
  }

  for (const p of [0,1,2,3]) {
    const enabledCb = document.getElementById('cfg-penabled-' + p);
    const enabled = enabledCb ? enabledCb.checked : false;
    if (!enabled) {
      data.players[p] = { model: null, params: null };
      continue;
    }
    const psel = document.getElementById('cfg-pmodel-' + p);
    const pmodel = psel ? psel.value : '';
    if (pmodel) {
      data.players[p] = { model: pmodel, params: {} };
      const pDefaults = modelDefaults[pmodel] || {};
      for (const k of Object.keys(pDefaults)) {
        const el = document.getElementById('cfg-p' + p + 'param-' + k);
        if (el) data.players[p].params[k] = parseFloat(el.value) ?? pDefaults[k];
      }
    } else {
      data.players[p] = { model: null, params: null };
    }
  }

  const r = await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const result = await r.json();
  // Show brief confirmation
  const msg = document.getElementById('message');
  msg.textContent = 'AI设置已保存';
  msg.style.color = '#27ae60';
  setTimeout(() => { msg.textContent = ''; msg.style.color = ''; }, 1500);
  // Refresh config display
  await fetchConfig();
  // Don't toggle — keep panel open so user sees the change
}

// Initial load
fetchState();
