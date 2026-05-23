/* ================================================================
   Guandan Web UI — Frontend Logic
   ================================================================ */

let gameState = null;
let selectedCards = new Set();       // card IDs selected in main hand
let activeStrip = null;              // index of selected combo strip (or null)
let debugMode = true;                // default ON
let flatLayout = false;              // false = vertical columns, true = horizontal
let comboStrips = [];                // [{cardIds: [id,...]}, ...]

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
}

async function playCards() {
  if (!myTurn) return;
  let cardIds;

  if (activeStrip !== null && activeStrip < comboStrips.length) {
    // Play the selected combo strip
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
  // Remove played cards from strips
  if (cardIds) {
    const playedSet = new Set(cardIds);
    comboStrips = comboStrips.filter(s => {
      s.cardIds = s.cardIds.filter(id => !playedSet.has(id));
      return s.cardIds.length > 0;
    });
  }
  render();
  if (debugMode) fetchDebug();
}

async function passTurn() {
  if (!myTurn) return;
  const r = await fetch('/api/pass', {method: 'POST'});
  gameState = await r.json();
  selectedCards.clear();
  activeStrip = null;
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
  }

  renderTrickHistory(gameState.trick_history || []);
  renderHand(gameState.my_hand);
  renderComboStrips();

  document.getElementById('btn-play').disabled = !myTurn || (selectedCards.size === 0 && activeStrip === null);
  document.getElementById('btn-pass').disabled = !myTurn || !gameState.can_pass;
  document.getElementById('btn-hint').disabled = !myTurn;
  document.getElementById('btn-organize').disabled = selectedCards.size === 0;
  document.getElementById('btn-new-round').style.display =
    (gameState.round_over && !gameState.game_over) ? 'inline-block' : 'none';

  const msgEl = document.getElementById('message');
  msgEl.textContent = gameState.message || '';
  msgEl.className = gameState.error ? 'error' : '';

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

// Initial load
fetchState();
