import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getApiUrl } from '../config';
import ThemeSelector from '../components/ThemeSelector/ThemeSelector';
import VoiceSelector from '../components/VoiceSelector/VoiceSelector';
import './HomePage.css';

function HomePage() {
  const navigate = useNavigate();
  const [gameCode, setGameCode] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [preferences, setPreferences] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [joining, setJoining] = useState(false);
  const [creating, setCreating] = useState(false);
  const [voice, setVoice] = useState('Timothy');

  const handleCreateGame = async (e) => {
    e.preventDefault();
    setError('');

    if (!playerName.trim()) {
      setError('Please enter your name');
      return;
    }

    setLoading(true);

    try {
      // Step 1: Create the game with selected voice
      const createResponse = await fetch(getApiUrl('/api/games/create'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice }),
      });

      if (!createResponse.ok) {
        throw new Error('Failed to create game');
      }

      const createData = await createResponse.json();
      const code = createData.code;

      // Step 2: Join the game as host
      const joinResponse = await fetch(getApiUrl(`/api/games/join/${code}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_name: playerName.trim(),
          preferences: preferences.trim() || null,
        }),
      });

      if (!joinResponse.ok) {
        const errorData = await joinResponse.json();
        throw new Error(errorData.detail || 'Failed to join game');
      }

      const joinData = await joinResponse.json();

      // Store player info in sessionStorage (per-tab, no cross-tab conflicts)
      sessionStorage.setItem(
        'bighead_playerInfo',
        JSON.stringify({
          playerId: joinData.player_id,
          playerName: joinData.player_name,
          isHost: joinData.is_host,
          gameId: joinData.game_id,
          gameCode: joinData.code,
          preferences: preferences.trim(),
        })
      );

      // Navigate to lobby — host arrives fully registered
      navigate(`/game/${joinData.code}/lobby`);
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

      // Store player info in sessionStorage (per-tab, no cross-tab conflicts)
      sessionStorage.setItem(
        'bighead_playerInfo',
        JSON.stringify({
          playerId: data.player_id,
          playerName: data.player_name,
          isHost: data.is_host,
          gameId: data.game_id,
          gameCode: data.code,
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

  const handleBack = () => {
    setJoining(false);
    setCreating(false);
    setError('');
    setPlayerName('');
    setPreferences('');
    setGameCode('');
    setVoice('Timothy');
  };

  return (
    <div className="home-page">
      <div className="home-container">
        <h1 className="home-title">BIG HEAD</h1>

        {!joining && !creating ? (
          <>
            <div className="home-section">
              <button
                className="home-button create-button"
                onClick={() => setCreating(true)}
                disabled={loading}
              >
                CREATE GAME
              </button>
            </div>

            <div className="home-divider">
              <span>OR</span>
            </div>

            <div className="home-section">
              <button
                className="home-button join-button"
                onClick={() => setJoining(true)}
                disabled={loading}
              >
                JOIN GAME
              </button>
            </div>
          </>
        ) : creating ? (
          <form className="home-section join-form" onSubmit={handleCreateGame}>
            <div className="input-group">
              <label htmlFor="playerName">Your Name</label>
              <input
                id="playerName"
                type="text"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                placeholder="Enter your name"
                maxLength={100}
                className="home-input"
                disabled={loading}
                autoFocus
              />
            </div>

            <div className="input-group preferences-group">
              <label htmlFor="preferences">What kind of game do you want?</label>
              <textarea
                id="preferences"
                value={preferences}
                onChange={(e) => setPreferences(e.target.value)}
                placeholder={"Describe your ideal game — topics, themes, difficulty, anything goes!\n\ne.g., \"90s movies and music, but make it hard\" or \"Science for kids\" or \"A mix of sports, food, and weird history\""}
                className="home-input home-textarea"
                disabled={loading}
                rows={4}
              />
            </div>

            <VoiceSelector value={voice} onChange={setVoice} disabled={loading} />

            <button
              type="submit"
              className="home-button create-button"
              disabled={loading}
            >
              {loading ? 'Creating...' : 'CREATE'}
            </button>

            <button
              type="button"
              className="home-button back-button"
              onClick={handleBack}
              disabled={loading}
            >
              BACK
            </button>
          </form>
        ) : (
          <form className="home-section join-form" onSubmit={handleJoinGame}>
            <div className="input-group">
              <label htmlFor="gameCode">Game Code</label>
              <input
                id="gameCode"
                type="text"
                value={gameCode}
                onChange={(e) => setGameCode(e.target.value.toUpperCase())}
                placeholder="ABC123"
                maxLength={6}
                className="home-input"
                disabled={loading}
                autoFocus
              />
            </div>

            <div className="input-group">
              <label htmlFor="playerName">Your Name</label>
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

            <div className="input-group preferences-group">
              <label htmlFor="preferences">What kind of game do you want?</label>
              <textarea
                id="preferences"
                value={preferences}
                onChange={(e) => setPreferences(e.target.value)}
                placeholder={"Describe your ideal game — topics, themes, difficulty, anything goes!\n\ne.g., \"90s movies and music, but make it hard\" or \"Science for kids\""}
                className="home-input home-textarea"
                disabled={loading}
                rows={3}
              />
            </div>

            <button
              type="submit"
              className="home-button join-button"
              disabled={loading}
            >
              {loading ? 'Joining...' : 'JOIN'}
            </button>

            <button
              type="button"
              className="home-button back-button"
              onClick={handleBack}
              disabled={loading}
            >
              BACK
            </button>
          </form>
        )}

        {error && <div className="error-message">{error}</div>}
        <ThemeSelector />
      </div>
    </div>
  );
}

export default HomePage;
