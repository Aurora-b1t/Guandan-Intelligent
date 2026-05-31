/* ================================================================
   Guandan Web UI — Shared Constants
   Loaded as regular <script> before game.js and arena.js
   ================================================================ */

window.SUIT_CHARS  = {0: '♣', 1: '♦', 2: '♥', 3: '♠', 4: ''};
window.SUIT_NAMES  = {0: 'C', 1: 'D', 2: 'H', 3: 'S', 4: ''};
window.PLAYER_NAMES = ['你', 'AI-右家', 'AI-对家', 'AI-左家'];
window.PLAYER_NAMES_ARENA = {0: '你', 1: '右家', 2: '对家', 3: '左家'};

window.COMBO_TYPE_CN = {
  1: '单张', 2: '对子', 3: '三条', 4: '三带二',
  5: '顺子', 6: '连对', 7: '钢板', 8: '炸弹',
  9: '同花顺', 10: '天王炸',
};

window.CAT_CN = {
  deduction: '确定推演',
  sampling: '不确定采样',
  endgame: '残局求解',
  opening: '开局评估',
};
