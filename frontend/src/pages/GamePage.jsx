import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useGame } from '../contexts/GameContext';
import GameBoard from '../components/GameBoard';
import QuestionModal from '../components/Modals/QuestionModal';
import ScoreBoard from '../components/ScoreBoard/ScoreBoard';
import ChatWindow from '../components/Chat/ChatWindow';
import '../styles/layout.css';

function GamePage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const { state, setGameCode } = useGame();
  const { board, gameReady, boardGenerating } = state;

  // Set the game code in context when the page loads
  useEffect(() => {
    if (code && setGameCode) {
      setGameCode(code);
    }
  }, [code, setGameCode]);

  // Get player info from session storage
  const playerInfo = JSON.parse(sessionStorage.getItem('playerInfo') || '{}');

  // If no player info and not in admin mode, redirect to lobby
  useEffect(() => {
    if (!playerInfo.playerName && !state.adminMode) {
      // Check if we need to register first
      navigate(`/game/${code}/lobby`);
    }
  }, [playerInfo.playerName, state.adminMode, code, navigate]);

  return (
    <div className="app">
      <div className="main-content">
        <div className="board-container">
          {board && (state.adminMode || gameReady || boardGenerating) ? (
            <GameBoard />
          ) : (
            <div className="waiting-screen">
              <h2>Waiting for Game to Start</h2>
              <p>The host will start the game shortly...</p>
              {Object.keys(state.players).length > 0 && (
                <div className="current-players">
                  <h3>Current Players:</h3>
                  <ul>
                    {Object.keys(state.players).map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          <QuestionModal />
        </div>

        <div className="score-container">
          <ScoreBoard />
          <ChatWindow />
        </div>
      </div>
    </div>
  );
}

export default GamePage;
