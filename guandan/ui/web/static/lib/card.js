/* ================================================================
   Guandan Web UI — Card Rendering (single source of truth)
   Loaded as regular <script> before game.js and arena.js
   ================================================================ */

window.suitClass = function(c) {
  if (c.is_joker) {
    return c.rank_name === 'SJ' ? 'joker-black' : 'joker-red';
  }
  return 'suit-' + (c.suit_name || SUIT_NAMES[c.suit] || '');
};

window.cardHTML = function(c, opts = {}) {
  const cls = (c.is_wild ? ' wild' : '') + ' ' + suitClass(c) + (opts.extraClass ? ' ' + opts.extraClass : '');
  const attrs = opts.attrs || '';
  return '<div class="card' + cls + '"' + (attrs ? ' ' + attrs : '') + '>' +
    '<span class="card-rank">' + c.rank_name + '</span>' +
    '<span class="card-suit-big">' + (SUIT_CHARS[c.suit] || '') + '</span>' +
    '</div>';
};

window.createCardElement = function(c, onClick, selected) {
  selected = selected || false;
  var sel = selected ? ' selected' : '';
  var wild = c.is_wild ? ' wild' : '';
  var sc = suitClass(c);
  var div = document.createElement('div');
  div.className = 'card' + sel + wild + ' ' + sc;
  div.setAttribute('data-card-id', c.id);
  div.onclick = function(e) {
    e.stopPropagation();
    onClick(c.id);
  };
  div.innerHTML =
    '<span class="card-rank">' + c.rank_name + '</span>' +
    '<span class="card-suit-big">' + (SUIT_CHARS[c.suit] || '') + '</span>';
  return div;
};

window.sortCards = function(cards) {
  return [...cards].sort(function(a, b) {
    return a.rank !== b.rank ? b.rank - a.rank : (a.suit || 0) - (b.suit || 0);
  });
};
