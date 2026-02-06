import React, { createContext, useContext, useReducer, useEffect, useCallback, useState } from 'react';
import useWebSocket from '../hooks/useWebSocket';
import { getLegacyWebSocketUrl, getWebSocketUrl } from '../config';

const GameContext = createContext();

const initialState = {
  board: null,
  currentQuestion: null,
  dailyDouble: null,
  contestants: [],
  buzzerActive: false,
  adminMode: window.location.search.includes('admin=true'),
  finalJeopardy: null,
  lastBuzzer: null,
  registered: false,
  playerName: null,
  gameReady: false,
  players: {},
  chatMessages: [],
  boardGenerating: false,
  revealedCategories: new Set(),
  answerTimer: {
    active: false,
    player: null,
    seconds: 0,
  },
  controllingPlayer: null, // Player who has control to select the next clue
  // Multi-game state
  gameCode: null,
  gameId: null,
  isHost: false,
  gameStatus: null, // 'lobby', 'active', 'completed'
};

function gameReducer(state, action) {
  switch (action.type) {
    case 'INIT_BOARD':
      console.log('Initializing board with:', action.payload);
      return { 
        ...state, 
        board: {
          categories: action.payload
        },
        boardGenerating: false
      };
    case 'START_BOARD_GENERATION':
      console.log('Starting board generation with placeholder');
      
      // Create a placeholder board with question marks
      const startPlaceholderCategories = Array(5).fill(null).map((_, i) => ({
        name: "?????",
        questions: Array(5).fill(null).map((_, j) => ({
          value: 200 * (j + 1),
          clue: "?????",
          answer: "?????",
          daily_double: false,
          used: false,
          type: "text",
          isPlaceholder: true
        }))
      }));
      
      return {
        ...state,
        board: {
          categories: startPlaceholderCategories
        },
        boardGenerating: true,
        revealedCategories: new Set(),
        gameReady: true // Set gameReady to true so the board displays
      };
    case 'REVEAL_CATEGORY':
      console.log('Revealing category:', action.payload);
      
      if (!state.boardGenerating || !state.board) {
        return state;
      }
      
      // Add the revealed category index to the set
      const revealCategoryUpdatedSet = new Set(state.revealedCategories);
      revealCategoryUpdatedSet.add(action.payload.index);
      
      // Update the board with the real category
      return {
        ...state,
        board: {
          ...state.board,
          categories: state.board.categories.map((cat, idx) => 
            idx === action.payload.index ? action.payload.category : cat
          )
        },
        revealedCategories: revealCategoryUpdatedSet,
        // If all categories have been revealed, set boardGenerating to false
        boardGenerating: revealCategoryUpdatedSet.size < 5,
        gameReady: true // Ensure gameReady stays true
      };
    case 'SHOW_QUESTION':
      return {
        ...state,
        currentQuestion: action.payload,
        controllingPlayer: null, // Clear controlling player when question is displayed
        buzzerActive: false,  // Keep buzzer inactive when showing question
        answerTimer: { active: false, player: null, seconds: 0 }, // Reset answer timer
        board: {
          ...state.board,
          categories: state.board.categories.map(cat => ({
            ...cat,
            questions: cat.questions.map(q =>
              q.value === action.payload.value && cat.name === action.payload.category
                ? { ...q, used: true }
                : q
            )
          }))
        }
      };
    case 'DAILY_DOUBLE':
      // Just mark the question as used, but don't display it yet
      console.log('Setting dailyDouble state:', action.payload);
      return {
        ...state,
        dailyDouble: {
          ...action.payload,
          selectingPlayer: action.payload.selecting_player
        },
        board: {
          ...state.board,
          categories: state.board.categories.map(cat => ({
            ...cat,
            questions: cat.questions.map(q =>
              q.value === action.payload.value && cat.name === action.payload.category
                ? { ...q, used: true }
                : q
            )
          }))
        }
      };
    case 'DAILY_DOUBLE_BET':
      // Now we have a bet amount, so we can show the question
      console.log('Processing daily double bet:', action.payload);
      return {
        ...state,
        dailyDouble: null, // Clear the dailyDouble state since we're moving to currentQuestion
        currentQuestion: {
          ...action.payload.question,
          bet: action.payload.bet,
          contestant: action.payload.contestant,
          daily_double: true
        }
      };
    case 'DISMISS_QUESTION':
      console.log('Dismissing question and clearing dailyDouble state');
      return { 
        ...state, 
        currentQuestion: null,
        dailyDouble: null,
        lastBuzzer: null,  // Clear the last buzzer
        answerTimer: { active: false, player: null, seconds: 0 } // Reset answer timer
      };
    case 'UPDATE_SCORE':
      console.log('Update score action:', action.payload);
      // Handle the scores object sent from the backend
      if (action.payload.scores) {
        // Create a new players object by merging current player info with updated scores
        const updatedPlayers = { ...state.players };
        Object.entries(action.payload.scores).forEach(([playerName, score]) => {
          if (updatedPlayers[playerName]) {
            updatedPlayers[playerName] = {
              ...updatedPlayers[playerName],
              score: score
            };
          }
        });
        
        return {
          ...state,
          players: updatedPlayers
        };
      } else {
        // Handle the old format for backward compatibility
        return {
          ...state,
          players: {
            ...state.players,
            [action.payload.contestant]: {
              ...state.players[action.payload.contestant],
              score: action.payload.newScore
            }
          }
        };
      }
    case 'SET_BUZZER_STATUS':
      // We need to properly track buzzer activation through audio completion
      console.log('SET_BUZZER_STATUS called with:', action.payload);
      return { ...state, buzzerActive: action.payload };
    case 'SET_BUZZER':
      console.log('Setting buzzer to:', action.payload.contestant);
      return { 
        ...state, 
        lastBuzzer: action.payload.contestant,
        buzzerActive: false, // When someone buzzes in, the buzzer becomes inactive
        // When a player buzzes in, the answer timer state is activated by a separate message
      };
    case 'SET_ANSWER_TIMER':
      console.log('Setting answer timer:', action.payload);
      return {
        ...state,
        answerTimer: {
          active: true,
          player: action.payload.player,
          seconds: action.payload.seconds
        }
      };
    case 'CLEAR_ANSWER_TIMER':
      console.log('Clearing answer timer');
      return {
        ...state,
        answerTimer: {
          active: false,
          player: null,
          seconds: 0
        }
      };
    case 'REGISTER_PLAYER':
      return {
        ...state,
        registered: true,
        playerName: action.payload.name
      };
    case 'PLAYER_LIST':
      return {
        ...state,
        players: action.payload.players,
        gameReady: Object.keys(action.payload.players).length >= 3
      };
    case 'GAME_READY':
      return {
        ...state,
        gameReady: action.payload.ready
      };
    case 'ANSWER_QUESTION':
      console.log('Answer question action:', action.payload);
      const { contestant, correct, value, newScore: backendScore } = action.payload;
      
      // Use the score from the backend if provided, otherwise calculate it
      let newScore;
      if (backendScore !== undefined) {
        newScore = backendScore;
      } else {
        const currentScore = state.players[contestant]?.score || 0;
        newScore = correct ? currentScore + value : currentScore - value;
      }
      
      return {
        ...state,
        // Only clear the current question if answer was correct
        // For incorrect answers, keep the modal open for other players
        currentQuestion: correct ? null : state.currentQuestion,
        // Always clear the buzzer state to allow other players to buzz in
        lastBuzzer: null,
        // Re-enable the buzzer for incorrect answers to allow other players to buzz in
        buzzerActive: correct ? false : true,
        // Clear the answer timer
        answerTimer: { active: false, player: null, seconds: 0 },
        players: {
          ...state.players,
          [contestant]: {
            ...state.players[contestant],
            score: newScore
          }
        }
      };
    case 'CHAT_MESSAGE':
      return {
        ...state,
        chatMessages: [...state.chatMessages, action.payload]
      };
    case 'CHAT_HISTORY':
      return {
        ...state,
        chatMessages: action.payload
      };
    case 'PLAY_AUDIO':
      console.log('Setting buzzer inactive while audio plays');
      // Always ensure buzzer is disabled during audio playback
      return { ...state, buzzerActive: false };
    case 'com.sc2ctl.jeopardy.play_audio':
      console.log('Audio message received in reducer - deferring to WebSocket handler');
      // Audio playback is now fully handled by the WebSocket message handler
      // Just ensure buzzer is disabled during audio playback
      return { ...state, buzzerActive: false };
    case 'SET_CONTROLLING_PLAYER':
      return {
        ...state,
        controllingPlayer: action.payload.contestant,
      };
    case 'com.sc2ctl.jeopardy.question_selected':
      return {
        ...state,
        currentQuestion: null,
        dailyDouble: null,
        lastBuzzer: null,
        players: {
          ...state.players,
          [action.payload.contestant]: {
            ...state.players[action.payload.contestant],
            score: 0
          }
        }
      };
    case 'com.sc2ctl.jeopardy.game_ready':
      console.log('Game ready status:', action.payload);
      return {
        ...state,
        gameReady: action.payload.ready
      };
    case 'com.sc2ctl.jeopardy.start_board_generation':
      console.log('Starting board generation with placeholders');
      
      // Create a placeholder board with question marks
      const wsPlaceholderCategories = Array(5).fill(null).map((_, i) => ({
        name: "?????",
        questions: Array(5).fill(null).map((_, j) => ({
          value: 200 * (j + 1),
          clue: "?????",
          answer: "?????",
          daily_double: false,
          used: false,
          type: "text",
          isPlaceholder: true
        }))
      }));
      
      return {
        ...state,
        board: {
          categories: wsPlaceholderCategories
        },
        boardGenerating: true,
        revealedCategories: new Set(),
        gameReady: true // Set gameReady to true so the board displays
      };
    case 'com.sc2ctl.jeopardy.reveal_category':
      console.log('Revealing category:', action.payload);
      
      if (!state.board) {
        return state;
      }
      
      // Add the revealed category index to the set
      const wsRevealedCategories = new Set(state.revealedCategories);
      wsRevealedCategories.add(action.payload.index);
      
      // Update the board with the real category
      return {
        ...state,
        board: {
          ...state.board,
          categories: state.board.categories.map((cat, idx) => 
            idx === action.payload.index ? action.payload.category : cat
          )
        },
        revealedCategories: wsRevealedCategories,
        // If all categories have been revealed, set boardGenerating to false
        boardGenerating: wsRevealedCategories.size < 5,
        gameReady: true // Ensure gameReady stays true
      };
    case 'com.sc2ctl.jeopardy.error':
      console.error('Game error:', action.payload.message);
      return state;
    case 'com.sc2ctl.jeopardy.audio_complete':
      console.log('Audio playback complete:', action.payload.audio_id);
      // Do not try to set buzzer status here - the server will send a separate buzzer_status message
      // Just log that we received the audio completion
      console.log('Waiting for server to send buzzer status update after audio completion');
      return state;
    case 'com.sc2ctl.jeopardy.answer_timer_start':
      console.log('Answer timer started for player:', action.payload.player);
      return {
        ...state,
        answerTimer: {
          active: true,
          player: action.payload.player,
          seconds: action.payload.seconds,
        },
      };
    case 'SET_GAME_CODE':
      return {
        ...state,
        gameCode: action.payload.code,
        gameId: action.payload.gameId || state.gameId,
      };
    case 'SET_GAME_STATE':
      return {
        ...state,
        gameId: action.payload.game_id,
        gameCode: action.payload.game_code,
        gameStatus: action.payload.status,
        board: action.payload.board,
        currentQuestion: action.payload.current_question,
        buzzerActive: action.payload.buzzer_active,
        lastBuzzer: action.payload.last_buzzer,
        gameReady: action.payload.game_ready,
        isHost: action.payload.is_host,
      };
    case 'GAME_STARTED':
      return {
        ...state,
        gameStatus: 'active',
        gameReady: true,
      };
    default:
      return state;
  }
}

export function GameProvider({ children }) {
  const [state, dispatch] = useReducer(gameReducer, {
    ...initialState,
    registered: initialState.adminMode, // Auto-register if admin mode
  });

  // Track current game code for WebSocket URL
  const [currentGameCode, setCurrentGameCode] = useState(null);

  // Handle all WebSocket messages in a single callback function
  const handleWebSocketMessage = useCallback((message) => {
    console.log('Processing WebSocket message:', message);
    
    switch (message.topic) {
      case 'com.sc2ctl.jeopardy.board_init':
        dispatch({ type: 'INIT_BOARD', payload: message.payload.categories });
        break;
      case 'com.sc2ctl.jeopardy.question_display':
        console.log('Showing question:', message.payload);
        dispatch({ 
          type: 'SHOW_QUESTION', 
          payload: message.payload
        });
        // Don't set buzzer to active here - it should stay inactive until audio completes
        break;
      case 'com.sc2ctl.jeopardy.question_dismiss':
        dispatch({ type: 'DISMISS_QUESTION' });
        break;
      case 'com.sc2ctl.jeopardy.buzzer_status':
        // Always trust the server state for buzzer status
        console.log('Server buzzer status update:', message.payload.active);
        dispatch({ type: 'SET_BUZZER_STATUS', payload: message.payload.active });
        break;
      case 'com.sc2ctl.jeopardy.contestant_score':
        dispatch({ type: 'UPDATE_SCORE', payload: message.payload });
        break;
      case 'com.sc2ctl.jeopardy.buzzer':
        console.log('Buzzer pressed by:', message.payload.contestant);
        dispatch({ 
          type: 'SET_BUZZER', 
          payload: { contestant: message.payload.contestant }
        });
        dispatch({ type: 'SET_BUZZER_STATUS', payload: false });
        break;
      case 'com.sc2ctl.jeopardy.player_list':
        console.log('Updating player list:', message.payload);
        dispatch({
          type: 'PLAYER_LIST',
          payload: { players: message.payload.players }
        });
        break;
      case 'com.sc2ctl.jeopardy.register_player_response':
        if (message.payload.success) {
          dispatch({
            type: 'REGISTER_PLAYER',
            payload: { name: message.payload.name }
          });
        }
        break;
      case 'com.sc2ctl.jeopardy.board_selected':
        console.log('Board selected:', message.payload);
        dispatch({ 
          type: 'INIT_BOARD', 
          payload: message.payload.categories 
        });
        break;
      case 'com.sc2ctl.jeopardy.game_ready':
        console.log('Game ready status:', message.payload);
        dispatch({
          type: 'GAME_READY',
          payload: { ready: message.payload.ready }
        });
        break;
      case 'com.sc2ctl.jeopardy.error':
        console.error('Game error:', message.payload.message);
        break;
      case 'com.sc2ctl.jeopardy.answer':
        console.log('Question answered:', message.payload);
        dispatch({
          type: 'ANSWER_QUESTION',
          payload: message.payload
        });
        break;
      case 'com.sc2ctl.jeopardy.daily_double':
        console.log('Daily Double selected:', message.payload);
        dispatch({
          type: 'DAILY_DOUBLE',
          payload: message.payload
        });
        break;
      case 'com.sc2ctl.jeopardy.daily_double_bet_response':
        console.log('Received daily double bet response:', message.payload);
        dispatch({
          type: 'DAILY_DOUBLE_BET',
          payload: {
            question: message.payload.question,
            bet: message.payload.bet,
            contestant: message.payload.contestant
          }
        });
        break;
      case 'com.sc2ctl.jeopardy.chat_message':
        dispatch({
          type: 'CHAT_MESSAGE',
          payload: {
            user: message.payload.username,
            text: message.payload.message,
            timestamp: new Date(message.payload.timestamp) || new Date(),
            isAdmin: message.payload.is_admin
          }
        });
        break;
      case 'com.sc2ctl.jeopardy.chat_history':
        // Process chat history messages
        const formattedMessages = message.payload.messages.map(msg => ({
          user: msg.username,
          text: msg.message,
          timestamp: new Date(msg.timestamp) || new Date(),
          isAdmin: msg.is_admin
        }));
        
        dispatch({
          type: 'CHAT_HISTORY',
          payload: formattedMessages
        });
        break;
      case 'com.sc2ctl.jeopardy.play_audio':
        console.log('Playing audio message received:', message.payload);
        // Ensure buzzer is disabled during audio playback
        dispatch({ type: 'PLAY_AUDIO' });
        
        // Create and play an audio element with simplified handling
        try {
          // Support both formats (url and audio_url) to ensure compatibility
          const rawUrl = message.payload.audio_url || message.payload.url;
          if (!rawUrl) {
            console.error('No audio URL provided in payload:', message.payload);
            return;
          }
          
          // Ensure the URL is absolute by adding the backend URL if needed
          const audioUrl = rawUrl.startsWith('http') 
            ? rawUrl 
            : `${window.location.protocol}//${window.location.host}${rawUrl}`;
          
          console.log('Playing audio with full URL:', audioUrl);
          
          // Extract audio ID from the payload or the filename
          let audioId = message.payload.audio_id;
          if (!audioId) {
            const filenameMatch = rawUrl.match(/question_audio_(\d+)/);
            if (filenameMatch && filenameMatch[1]) {
              audioId = `audio_${filenameMatch[1]}`;
            } else {
              audioId = `audio_${Date.now()}`;
            }
          }
          console.log('Using audio ID:', audioId);
          
          const audio = new Audio(audioUrl);
          
          // Add debug event listeners
          audio.addEventListener('canplay', () => {
            console.log(`Audio ${audioId} can play`);
          });
          
          audio.addEventListener('playing', () => {
            console.log(`Audio ${audioId} playback started`);
            // Ensure buzzer stays disabled while audio is playing
            dispatch({ type: 'SET_BUZZER_STATUS', payload: false });
          });
          
          audio.addEventListener('error', (e) => {
            console.error(`Audio ${audioId} error:`, e.target.error);
          });
          
          // When audio completes, notify the backend via WebSocket using sendMessage
          audio.addEventListener('ended', () => {
            console.log(`Audio ${audioId} playback COMPLETED, notifying backend`);
            
            // Use the sendMessage function from our useWebSocket hook
            sendMessage('com.sc2ctl.jeopardy.audio_complete', { audio_id: audioId });
            console.log(`Audio completion for ${audioId} sent via sendMessage`);
          });
          
          // Play the audio
          console.log(`Starting audio playback for ${audioId}`);
          audio.play().catch(err => {
            console.error(`Error playing audio ${audioId}:`, err);
          });
        } catch (err) {
          console.error('Error setting up audio playback:', err);
        }
        break;
      case 'com.sc2ctl.jeopardy.select_question':
        console.log('Player has control:', message.payload.contestant);
        dispatch({
          type: 'SET_CONTROLLING_PLAYER',
          payload: { contestant: message.payload.contestant }
        });
        break;
      case 'com.sc2ctl.jeopardy.question_selected':
        dispatch({ type: 'QUESTION_SELECTED', payload: message.payload });
        break;
      case 'com.sc2ctl.jeopardy.start_board_generation':
        console.log('Starting board generation with placeholders');
        dispatch({ type: 'START_BOARD_GENERATION' });
        break;
      case 'com.sc2ctl.jeopardy.reveal_category':
        console.log('Revealing category:', message.payload);
        dispatch({
          type: 'REVEAL_CATEGORY',
          payload: message.payload
        });
        break;
      case 'com.sc2ctl.jeopardy.audio_complete':
        console.log('Audio playback complete:', message.payload.audio_id);
        // Do not try to set buzzer status here - the server will send a separate buzzer_status message
        // Just log that we received the audio completion
        console.log('Waiting for server to send buzzer status update after audio completion');
        break;
      case 'com.sc2ctl.jeopardy.answer_timer_start':
        console.log('Answer timer started for player:', message.payload.player);
        dispatch({
          type: 'SET_ANSWER_TIMER',
          payload: {
            player: message.payload.player,
            seconds: message.payload.seconds,
          },
        });
        break;
      case 'com.sc2ctl.jeopardy.game_state':
        console.log('Received game state:', message.payload);
        dispatch({
          type: 'SET_GAME_STATE',
          payload: message.payload,
        });
        // Also update players from the game state
        if (message.payload.players) {
          dispatch({
            type: 'PLAYER_LIST',
            payload: { players: message.payload.players },
          });
        }
        break;
      case 'com.sc2ctl.jeopardy.game_started':
        console.log('Game started');
        dispatch({ type: 'GAME_STARTED' });
        break;
      default:
        console.log('Unhandled message topic:', message.topic);
    }
  }, [dispatch]);
  
  // Get player name from session storage for HTTP-joined players
  const playerInfo = typeof window !== 'undefined'
    ? JSON.parse(sessionStorage.getItem('playerInfo') || '{}')
    : {};

  // Determine WebSocket URL based on game code, include player_name for linking
  const wsUrl = currentGameCode
    ? getWebSocketUrl(currentGameCode, playerInfo.playerName || null)
    : getLegacyWebSocketUrl();

  // Use the refactored WebSocket hook with our message handler
  const { sendMessage, ws, isConnected } = useWebSocket(wsUrl, handleWebSocketMessage);

  // Function to set the game code (called from game pages)
  const setGameCode = useCallback((code, gameId = null) => {
    setCurrentGameCode(code);
    dispatch({
      type: 'SET_GAME_CODE',
      payload: { code, gameId },
    });
  }, []);

  // Effect to handle admin mode initialization
  useEffect(() => {
    if (state.adminMode && !state.board) {
      console.log("Admin mode detected, auto-registering");
    }
  }, [state.adminMode]);

  // Initialize playerName from sessionStorage
  useEffect(() => {
    const playerInfo = JSON.parse(sessionStorage.getItem('playerInfo') || '{}');
    if (playerInfo.playerName && !state.playerName) {
      dispatch({
        type: 'REGISTER_PLAYER',
        payload: { name: playerInfo.playerName }
      });
    }
  }, []);

  // Function to send chat messages
  const sendChatMessage = (message) => {
    if (message.trim() === '') return;

    const isAdmin = state.adminMode;
    // Try state first, then sessionStorage as fallback
    let username = state.playerName;
    if (!username) {
      const playerInfo = JSON.parse(sessionStorage.getItem('playerInfo') || '{}');
      username = playerInfo.playerName || 'Anonymous';
    }

    // Send message to server
    sendMessage({
      topic: 'com.sc2ctl.jeopardy.chat_message',
      payload: {
        username: username,
        message: message,
        is_admin: isAdmin
      }
    });
    
    // Note: We don't need to dispatch to local state here
    // The message will come back through the websocket and be added through that handler
  };

  return (
    <GameContext.Provider
      value={{
        state,
        dispatch,
        sendMessage,
        sendChatMessage,
        setGameCode,
        isConnected,
      }}
    >
      {children}
    </GameContext.Provider>
  );
}

export function useGame() {
  const context = useContext(GameContext);
  if (context === undefined) {
    throw new Error('useGame must be used within a GameProvider');
  }
  return context;
} 