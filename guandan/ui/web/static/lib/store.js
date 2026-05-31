/* ================================================================
   Guandan Web UI — Alpine.js Reactive Store
   Single source of truth for UI state.
   Creates a plain object first (so game.js can write before Alpine
   initializes), then wraps it reactively on alpine:init.
   ================================================================ */

// Plain state object — accessible immediately (before Alpine init)
window._gameState = {
  configOpen: false,
  suggestOpen: false,
  aiDebugOpen: false,
  debugMode: true,
  showWinRate: true,
  configTab: 'global',
  state: null,

  get started() { return this.state?.game_started; },
  get roundOver() { return this.state?.round_over; },
  get isMyTurn() { return this.state?.my_turn; },

  // Actions delegate to window functions set by game.js
  toggleWinRate() { if (window.toggleWinRate) window.toggleWinRate(); },
  toggleDebug()   { if (window.toggleDebug) window.toggleDebug(); },
  toggleAIDebug() { if (window.toggleAIDebug) window.toggleAIDebug(); },
  toggleConfig()  { if (window.toggleConfig) window.toggleConfig(); },
  applyConfig()   { if (window.applyConfig) window.applyConfig(); },
  switchConfigTab(t) { if (window.switchConfigTab) window.switchConfigTab(t); },
  startGame()     { if (window.startGame) window.startGame(); },
  playCards()     { if (window.playCards) window.playCards(); },
  passTurn()      { if (window.passTurn) window.passTurn(); },
  showHint()      { if (window.showHint) window.showHint(); },
  organizeCombo() { if (window.organizeCombo) window.organizeCombo(); },
  toggleLayout()  { if (window.toggleLayout) window.toggleLayout(); },
  newRound()      { if (window.newRound) window.newRound(); },
  newGame()       { if (window.newGame) window.newGame(); },
  aiSuggest()     { if (window.aiSuggest) window.aiSuggest(); },
  aiEvaluate()    { if (window.aiEvaluate) window.aiEvaluate(); },
  toggleAutoPlay(){ if (window.toggleAutoPlay) window.toggleAutoPlay(); },
  clearAILog()    { if (window.clearAILog) window.clearAILog(); },
  closeSuggest()  { this.suggestOpen = false; },
};

// When Alpine initializes, wrap the existing object reactively,
// then replace window._gameState with the reactive proxy so that
// direct writes (window._gameState.xxx = y) trigger x-show updates.
document.addEventListener('alpine:init', () => {
  Alpine.store('game', window._gameState);
  window._gameState = Alpine.store('game');
});
