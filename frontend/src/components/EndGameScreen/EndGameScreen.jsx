import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useGame } from '../../contexts/GameContext';
import { getApiUrl } from '../../config';
import './EndGameScreen.css';

function EndGameScreen() {
  const { state } = useGame();
  const { finalResults } = state;
  const { code } = useParams();
  const navigate = useNavigate();
  const [restarting, setRestarting] = useState(false);
  const [shareText, setShareText] = useState('Share Results');

  if (!finalResults) return null;

  const { scores, winner } = finalResults;

  // Sort players by score descending
  const sortedPlayers = Object.entries(scores).sort(([, a], [, b]) => b - a);

  const playerInfo = JSON.parse(sessionStorage.getItem('bighead_playerInfo') || '{}');
  const gameId = playerInfo.gameId || state.gameId;

  const handlePlayAgain = async () => {
    if (!gameId) {
      navigate('/');
      return;
    }

    setRestarting(true);
    try {
      const response = await fetch(getApiUrl(`/api/games/${gameId}/restart`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to restart');
      }
      // Game will restart and WebSocket will receive game_restart event
    } catch {
      // Fallback: navigate home to create a new game
      navigate('/');
    } finally {
      setRestarting(false);
    }
  };

  const handleShare = () => {
    const lines = ['BIG HEAD - Final Scores'];
    sortedPlayers.forEach(([name, score], index) => {
      const medal = index === 0 ? ' (Winner)' : '';
      lines.push(`${index + 1}. ${name}: $${score.toLocaleString()}${medal}`);
    });
    const text = lines.join('\n');

    navigator.clipboard.writeText(text).then(() => {
      setShareText('Copied!');
      setTimeout(() => setShareText('Share Results'), 2000);
    });
  };

  const handleHome = () => {
    navigate('/');
  };

  return (
    <div className="end-game-page">
      <div className="end-game-container">
        <h1 className="end-game-title">Game Over!</h1>
        <h2 className="end-game-winner">
          Congratulations, {winner}!
        </h2>

        <div className="end-game-scoreboard">
          <h3>Final Scores</h3>
          <ol className="end-game-scores">
            {sortedPlayers.map(([name, score], index) => (
              <li
                key={name}
                className={`end-game-score-row ${name === winner ? 'winner' : ''}`}
              >
                <span className="end-game-rank">{index + 1}</span>
                <span className="end-game-name">{name}</span>
                <span className="end-game-score">${score.toLocaleString()}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="end-game-actions">
          <button
            className="end-game-play-again"
            onClick={handlePlayAgain}
            disabled={restarting}
          >
            {restarting ? 'Restarting...' : 'Play Again'}
          </button>

          <button className="end-game-share" onClick={handleShare}>
            {shareText}
          </button>

          <button className="end-game-home" onClick={handleHome}>
            Back to Home
          </button>
        </div>
      </div>
    </div>
  );
}

export default EndGameScreen;
