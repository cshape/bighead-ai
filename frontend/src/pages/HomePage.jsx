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
  const [voice, setVoice] = useState('Clive');

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
    setVoice('Clive');
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
                placeholder="Enter whatever"
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
                placeholder="Enter whatever"
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

      <div className="home-footer">
        <a href="https://github.com/cshape/bighead-ai" target="_blank" rel="noopener noreferrer" className="floating-btn github-btn" title="View on GitHub">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
          </svg>
          <span>GitHub</span>
        </a>
        <a href="https://render.com/deploy?repo=https://github.com/cshape/bighead-ai" target="_blank" rel="noopener noreferrer" className="floating-btn deploy-btn" title="Deploy on Render">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span>Deploy on Render</span>
        </a>
      </div>
    </div>
  );
}

export default HomePage;
