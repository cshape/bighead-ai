import React from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { useGame } from './contexts/GameContext';
import GameBoard from './components/GameBoard';
import QuestionModal from './components/Modals/QuestionModal';
import PlayerRegistrationModal from './components/Modals/PlayerRegistrationModal';
import ScoreBoard from './components/ScoreBoard/ScoreBoard';
import ChatWindow from './components/Chat/ChatWindow';
import HomePage from './pages/HomePage';
import LobbyPage from './pages/LobbyPage';
import GamePage from './pages/GamePage';
import './styles/layout.css';

// Legacy game component for backward compatibility
function LegacyGame() {
  const { state } = useGame();
  const { registered, adminMode, board, gameReady } = state;

  // Admin mode should bypass player registration
  if (!registered && !adminMode) {
    return <PlayerRegistrationModal />;
  }

  return (
    <div className="app">
      <div className="main-content">
        <div className="board-container">
          {board && (adminMode || gameReady || state.boardGenerating) ? (
            <GameBoard />
          ) : (
            <div className="waiting-screen">
              <h2>Waiting for Players</h2>
              <p>Please wait while players join...</p>
              {Object.keys(state.players).length > 0 && (
                <div className="current-players">
                  <h3>Current Players:</h3>
                  <ul>
                    {Object.keys(state.players).map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                  <p>Need {3 - Object.keys(state.players).length} more player(s) to start</p>
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

function App() {
  const location = useLocation();

  // Check if this is legacy admin mode
  const isLegacyAdmin = location.search.includes('admin=true');

  // For legacy routes (admin, board, play), use the legacy game component
  if (
    isLegacyAdmin ||
    location.pathname === '/admin' ||
    location.pathname === '/board' ||
    location.pathname.startsWith('/play/')
  ) {
    return <LegacyGame />;
  }

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/game/:code/lobby" element={<LobbyPage />} />
      <Route path="/game/:code" element={<GamePage />} />
      {/* Legacy routes - redirect to legacy component handled above */}
      <Route path="/admin" element={<LegacyGame />} />
      <Route path="/board" element={<LegacyGame />} />
      <Route path="/play/:username" element={<LegacyGame />} />
      {/* Fallback - show home page */}
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}

export default App; 