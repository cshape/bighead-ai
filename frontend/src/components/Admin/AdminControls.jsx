import React from 'react';
import { useGame } from '../../contexts/GameContext';
import BoardSelector from './BoardSelector';
import './AdminControls.css';

export default function AdminControls() {
  const { state, sendMessage } = useGame();
  const { board } = state;

  if (!board) {
    return <BoardSelector />;
  }

  const handleStartAIGame = () => {
    sendMessage('com.sc2ctl.bighead.start_ai_game', {
      num_players: 3,
      headless: false
    });
  };

  return (
    <div className="admin-controls">
      <div className="admin-status">
        <button 
          onClick={handleStartAIGame}
          className="start-ai-game-btn"
        >
          Start AI Game
        </button>
      </div>
    </div>
  );
}