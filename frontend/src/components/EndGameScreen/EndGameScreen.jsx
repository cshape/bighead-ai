import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame } from '../../contexts/GameContext';
import './EndGameScreen.css';

function EndGameScreen() {
  const { state } = useGame();
  const { finalResults } = state;
  const navigate = useNavigate();

  if (!finalResults) return null;

  const { scores, winner } = finalResults;

  // Sort players by score descending
  const sortedPlayers = Object.entries(scores).sort(([, a], [, b]) => b - a);

  const handlePlayAgain = () => {
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

        <button
          className="end-game-play-again"
          onClick={handlePlayAgain}
        >
          Play Again
        </button>
      </div>
    </div>
  );
}

export default EndGameScreen;
