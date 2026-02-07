import React from 'react';
import { useGame } from '../../contexts/GameContext';
import CategoryColumn from './CategoryColumn';
import './GameBoard.css';

export default function GameBoard() {
  const { state } = useGame();

  if (!state.board) {
    return <div className="loading">Loading game board...</div>;
  }

  // Add safety check for categories
  if (!Array.isArray(state.board?.categories)) {
    console.log('Current board state:', state.board);
    return <div className="loading">Waiting for categories...</div>;
  }

  // Check if current player has control to select clues
  // Get playerName from state OR localStorage as fallback for race condition
  let playerName = state.playerName;
  if (!playerName) {
    const playerInfo = JSON.parse(sessionStorage.getItem('jeopardy_playerInfo') || '{}');
    playerName = playerInfo.playerName;
  }

  const canSelect = state.controllingPlayer &&
                    playerName &&
                    state.controllingPlayer === playerName;

  return (
    <div className={`jeopardy-board ${state.boardGenerating ? 'generating' : ''}`}>
      {state.board.categories.map((category, index) => (
        <CategoryColumn
          key={index}
          category={category}
          isAdmin={state.adminMode}
          isPlaceholder={state.boardGenerating && !state.revealedCategories.has(index)}
          isRevealing={state.boardGenerating && state.revealedCategories.has(index)}
          canSelect={canSelect}
        />
      ))}
    </div>
  );
} 