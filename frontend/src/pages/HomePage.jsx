import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getApiUrl } from '../config';
import './HomePage.css';

function HomePage() {
  const navigate = useNavigate();
  const [gameCode, setGameCode] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [preferences, setPreferences] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreateGame = async () => {
    setLoading(true);
    setError('');

    try {
      const response = await fetch(getApiUrl('/api/games/create'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to create game');
      }

      const data = await response.json();
      // Navigate to lobby with the game code
      navigate(`/game/${data.code}/lobby`, { state: { isHost: true } });
    } catch (err) {
      setError(err.message || 'Failed to create game');
    } finally {
      setLoading(false);
    }
  };

  const handleJoinGame = async (e) => {
    e.preventDefault();
    setError('');

    if (!gameCode.trim()) {
      setError('Please enter a game code');
      return;
    }

    if (!playerName.trim()) {
      setError('Please enter your name');
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(getApiUrl(`/api/games/join/${gameCode.toUpperCase()}`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          player_name: playerName.trim(),
          preferences: preferences.trim() || null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to join game');
      }

      const data = await response.json();

      // Store player info in session storage for the lobby/game pages
      sessionStorage.setItem(
        'playerInfo',
        JSON.stringify({
          playerId: data.player_id,
          playerName: data.player_name,
          isHost: data.is_host,
          gameId: data.game_id,
          preferences: preferences.trim(),
        })
      );

      // Navigate to lobby
      navigate(`/game/${data.code}/lobby`);
    } catch (err) {
      setError(err.message || 'Failed to join game');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="home-page">
      <div className="home-container">
        <h1 className="home-title">JEOPARDY AI</h1>

        <div className="home-section">
          <button
            className="home-button create-button"
            onClick={handleCreateGame}
            disabled={loading}
          >
            {loading ? 'Creating...' : 'CREATE GAME'}
          </button>
        </div>

        <div className="home-divider">
          <span>OR</span>
        </div>

        <form className="home-section join-form" onSubmit={handleJoinGame}>
          <div className="input-group">
            <label htmlFor="gameCode">Enter Game Code:</label>
            <input
              id="gameCode"
              type="text"
              value={gameCode}
              onChange={(e) => setGameCode(e.target.value.toUpperCase())}
              placeholder="ABC123"
              maxLength={6}
              className="home-input"
              disabled={loading}
            />
          </div>

          <div className="input-group">
            <label htmlFor="playerName">Your Name:</label>
            <input
              id="playerName"
              type="text"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              placeholder="Enter your name"
              maxLength={100}
              className="home-input"
              disabled={loading}
            />
          </div>

          <div className="input-group">
            <label htmlFor="preferences">Category Preferences (optional):</label>
            <input
              id="preferences"
              type="text"
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              placeholder="e.g., Science, History, 90s Movies"
              className="home-input"
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="home-button join-button"
            disabled={loading}
          >
            {loading ? 'Joining...' : 'JOIN GAME'}
          </button>
        </form>

        {error && <div className="error-message">{error}</div>}
      </div>
    </div>
  );
}

export default HomePage;
