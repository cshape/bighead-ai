import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { getApiUrl, getWebSocketUrl } from '../config';
import { useGame } from '../contexts/GameContext';
import './LobbyPage.css';

function LobbyPage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { setGameCode } = useGame();

  // Set game code in GameContext so it connects to the correct WebSocket endpoint
  useEffect(() => {
    if (code) {
      setGameCode(code, null);
    }
  }, [code, setGameCode]);

  const [gameState, setGameState] = useState(null);
  const [players, setPlayers] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [ws, setWs] = useState(null);
  const [playerName, setPlayerName] = useState('');
  const [playerPreferences, setPlayerPreferences] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);

  // Get player info from session storage or location state
  const playerInfo = JSON.parse(sessionStorage.getItem('playerInfo') || '{}');
  const isHost = location.state?.isHost || playerInfo.isHost || false;

  // Fetch initial game state
  useEffect(() => {
    const fetchGameState = async () => {
      try {
        const response = await fetch(getApiUrl(`/api/games/code/${code}`));
        if (!response.ok) {
          throw new Error('Game not found');
        }
        const data = await response.json();
        setGameState(data);
        setPlayers(data.players || []);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    };

    fetchGameState();
  }, [code]);

  // Set up WebSocket connection
  useEffect(() => {
    if (!code) return;

    // Include player_name for HTTP-joined players so backend can link the websocket
    const wsUrl = getWebSocketUrl(code, playerInfo.playerName || null);
    console.log('Connecting to WebSocket:', wsUrl);
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      console.log('WebSocket connected to lobby');
      setError(''); // Clear any connection errors
    };

    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('Lobby received:', message);

      switch (message.topic) {
        case 'com.sc2ctl.jeopardy.game_state':
          setGameState(message.payload);
          setPlayers(
            Object.entries(message.payload.players || {}).map(([name, data]) => ({
              name,
              score: data.score,
            }))
          );
          break;

        case 'com.sc2ctl.jeopardy.player_list':
          setPlayers(
            Object.entries(message.payload.players || {}).map(([name, data]) => ({
              name,
              score: data.score,
              preferences: data.preferences || '',
            }))
          );
          break;

        case 'com.sc2ctl.jeopardy.game_ready':
          setGameState((prev) => ({ ...prev, can_start: message.payload.ready }));
          break;

        case 'com.sc2ctl.jeopardy.start_board_generation':
          // Board generation started, navigate to game page
          navigate(`/game/${code}`);
          break;

        case 'com.sc2ctl.jeopardy.game_started':
          // Game has started, navigate to game page
          navigate(`/game/${code}`);
          break;

        case 'com.sc2ctl.jeopardy.register_player_response':
          if (message.payload.success) {
            setIsRegistering(false);
            // Store player info including player_id from backend
            sessionStorage.setItem(
              'playerInfo',
              JSON.stringify({
                ...playerInfo,
                playerName: message.payload.name,
                playerId: message.payload.player_id,
                isHost: message.payload.is_host,
                gameId: gameState?.game_id,
              })
            );
          }
          break;

        default:
          console.log('Unhandled lobby message:', message.topic);
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('Connection error');
    };

    websocket.onclose = () => {
      console.log('WebSocket closed');
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [code, navigate]);

  const handleRegisterPlayer = useCallback(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !playerName.trim()) {
      return;
    }

    setIsRegistering(true);
    ws.send(
      JSON.stringify({
        topic: 'com.sc2ctl.jeopardy.register_player',
        payload: {
          name: playerName.trim(),
          preferences: playerPreferences.trim(),
        },
      })
    );
  }, [ws, playerName, playerPreferences]);

  const handleStartGame = async () => {
    // Read fresh from sessionStorage to avoid stale closure
    const currentPlayerInfo = JSON.parse(sessionStorage.getItem('playerInfo') || '{}');
    if (!currentPlayerInfo.playerId) {
      setError('Player information not found. Please rejoin the game.');
      return;
    }

    setStarting(true);
    setError('');

    try {
      const response = await fetch(getApiUrl(`/api/games/${gameState.game_id}/start`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          player_id: currentPlayerInfo.playerId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start game');
      }

      // Navigation will happen via WebSocket message
    } catch (err) {
      setError(err.message);
      setStarting(false);
    }
  };

  const copyGameCode = () => {
    navigator.clipboard.writeText(code);
  };

  if (loading) {
    return (
      <div className="lobby-page">
        <div className="lobby-container">
          <div className="loading">Loading game...</div>
        </div>
      </div>
    );
  }

  if (error && !gameState) {
    return (
      <div className="lobby-page">
        <div className="lobby-container">
          <div className="error-message">{error}</div>
          <button className="lobby-button" onClick={() => navigate('/')}>
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  const canStart = players.length >= 3;
  const needsRegistration = isHost && !playerInfo.playerName;

  return (
    <div className="lobby-page">
      <div className="lobby-container">
        <h1 className="lobby-title">GAME LOBBY</h1>

        <div className="game-code-section">
          <span className="game-code-label">Game Code:</span>
          <div className="game-code-display">
            <span className="game-code">{code}</span>
            <button className="copy-button" onClick={copyGameCode} title="Copy code">
              Copy
            </button>
          </div>
          <p className="game-code-hint">Share this code with other players to join</p>
        </div>

        {needsRegistration && (
          <div className="register-section">
            <h3>Enter Your Name to Join</h3>
            <div className="register-form">
              <input
                type="text"
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                placeholder="Your name"
                maxLength={100}
                className="register-input"
                disabled={isRegistering}
              />
              <input
                type="text"
                value={playerPreferences}
                onChange={(e) => setPlayerPreferences(e.target.value)}
                placeholder="Category preferences (optional)"
                className="register-input"
                disabled={isRegistering}
              />
              <button
                className="register-button"
                onClick={handleRegisterPlayer}
                disabled={isRegistering || !playerName.trim()}
              >
                {isRegistering ? 'Joining...' : 'Join'}
              </button>
            </div>
          </div>
        )}

        <div className="players-section">
          <h2 className="players-title">
            Players ({players.length}/3 minimum)
          </h2>
          <ul className="players-list">
            {players.map((player, index) => (
              <li key={player.name || index} className="player-item">
                <div className="player-info">
                  <span className="player-name">{player.name}</span>
                  {index === 0 && <span className="host-badge">Host</span>}
                </div>
                {player.preferences && (
                  <span className="player-preferences">{player.preferences}</span>
                )}
              </li>
            ))}
            {players.length === 0 && (
              <li className="player-item empty">Waiting for players...</li>
            )}
          </ul>
        </div>

        {isHost && (
          <div className="host-controls">
            <button
              className="start-button"
              onClick={handleStartGame}
              disabled={!canStart || starting}
            >
              {starting
                ? 'Starting...'
                : canStart
                ? 'START GAME'
                : `Need ${3 - players.length} more player(s)`}
            </button>
          </div>
        )}

        {!isHost && (
          <div className="waiting-message">
            Waiting for host to start the game...
          </div>
        )}

        {error && !(error === 'Connection error' && players.length > 0) && (
          <div className="error-message">{error}</div>
        )}
      </div>
    </div>
  );
}

export default LobbyPage;
