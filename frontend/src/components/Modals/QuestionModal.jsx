import React, { useState, useEffect, useRef } from 'react';
import { useGame } from '../../contexts/GameContext';
import './Modal.css';

export default function QuestionModal() {
  const { state, sendMessage, submitAnswer } = useGame();
  const { currentQuestion, buzzerActive, lastBuzzer, answerTimer, answerSubmitted, players, incorrectPlayers } = state;

  // Get playerName from state OR localStorage as fallback (registration
  // happens on LobbyPage's WebSocket, so state.playerName may still be null)
  let playerName = state.playerName;
  if (!playerName) {
    const info = JSON.parse(sessionStorage.getItem('bighead_playerInfo') || '{}');
    playerName = info.playerName;
  }
  const [showDoubleBigHeadQuestion, setShowDoubleBigHeadQuestion] = useState(false);
  const [timerProgress, setTimerProgress] = useState(0);
  const [answerTimerProgress, setAnswerTimerProgress] = useState(0);
  const [betAmount, setBetAmount] = useState(5);
  const [answerText, setAnswerText] = useState('');
  const answerInputRef = useRef(null);

  // Reference to track if this is the first time we're seeing this question
  const questionRef = useRef(null);
  // Track if we've received at least one true buzzerActive state for this question
  const hasBeenActivatedRef = useRef(false);
  // Local state to control buzzer UI
  const [showActiveBuzzer, setShowActiveBuzzer] = useState(false);
  // Timer animation reference
  const timerIntervalRef = useRef(null);
  // Answer timer animation reference
  const answerTimerIntervalRef = useRef(null);
  
  // Reset question tracking when question changes
  useEffect(() => {
    // If we have a new question (different from the one we're tracking)
    if (currentQuestion && currentQuestion !== questionRef.current) {
      console.log("New question detected, resetting buzzer states");
      questionRef.current = currentQuestion;
      hasBeenActivatedRef.current = false;
      setShowActiveBuzzer(false);
      setTimerProgress(0);
      setAnswerTimerProgress(0);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
      if (answerTimerIntervalRef.current) {
        clearInterval(answerTimerIntervalRef.current);
        answerTimerIntervalRef.current = null;
      }
    }
  }, [currentQuestion]);
  
  // Handle buzzer active state changes from the backend
  useEffect(() => {
    if (buzzerActive) {
      // Only set the buzzer to active if we've already seen this question for a while
      // This prevents the initial flash of green
      if (hasBeenActivatedRef.current) {
        console.log("Showing active buzzer - activation already confirmed");
        setShowActiveBuzzer(true);
      } else {
        // Mark that we've seen a true activation, but don't show it yet
        // until we've had this question for a bit
        console.log("First activation signal received, waiting to confirm");
        hasBeenActivatedRef.current = true;
        
        // Wait a short time to make sure this isn't just a transient state
        const timer = setTimeout(() => {
          // Only proceed if we're still on the same question and buzzer is still active
          if (currentQuestion === questionRef.current && buzzerActive) {
            console.log("Activation confirmed after delay, showing active buzzer");
            setShowActiveBuzzer(true);
          }
        }, 500); // 500ms delay to ensure it's not a false activation
        
        return () => clearTimeout(timer);
      }
    } else {
      // Always immediately disable the buzzer when backend says to
      console.log("Backend disabled buzzer, hiding active buzzer");
      setShowActiveBuzzer(false);
      setTimerProgress(0);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
  }, [buzzerActive, currentQuestion]);

  // Timer effect for buzzer countdown
  useEffect(() => {
    if (showActiveBuzzer) {
      // Reset timer progress
      setTimerProgress(0);
      
      // Clear any existing interval
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
      
      // Start a new timer
      const startTime = Date.now();
      const duration = 5000; // 5 seconds in ms
      
      timerIntervalRef.current = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min((elapsed / duration) * 100, 100);
        setTimerProgress(progress);
        
        if (progress >= 100) {
          clearInterval(timerIntervalRef.current);
          timerIntervalRef.current = null;
        }
      }, 50); // Update every 50ms for smooth animation
    } else {
      // Reset the timer when buzzer is deactivated
      setTimerProgress(0);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }
    
    // Clean up on unmount
    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    };
  }, [showActiveBuzzer]);

  // Answer timer effect
  useEffect(() => {
    if (answerTimer.active) {
      // Reset answer timer progress
      setAnswerTimerProgress(0);
      
      // Clear any existing interval
      if (answerTimerIntervalRef.current) {
        clearInterval(answerTimerIntervalRef.current);
      }
      
      // Start a new timer
      const startTime = Date.now();
      const duration = answerTimer.seconds * 1000; // Convert seconds to ms
      
      answerTimerIntervalRef.current = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min((elapsed / duration) * 100, 100);
        setAnswerTimerProgress(progress);
        
        if (progress >= 100) {
          clearInterval(answerTimerIntervalRef.current);
          answerTimerIntervalRef.current = null;
        }
      }, 50); // Update every 50ms for smooth animation
    } else {
      // Reset the timer when answer timer is deactivated
      setAnswerTimerProgress(0);
      if (answerTimerIntervalRef.current) {
        clearInterval(answerTimerIntervalRef.current);
        answerTimerIntervalRef.current = null;
      }
    }
    
    // Clean up on unmount
    return () => {
      if (answerTimerIntervalRef.current) {
        clearInterval(answerTimerIntervalRef.current);
        answerTimerIntervalRef.current = null;
      }
    };
  }, [answerTimer]);

  // Add keyboard event listener for spacebar
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space' && showActiveBuzzer && !incorrectPlayers.includes(playerName)) {
        handleBuzz();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [showActiveBuzzer, incorrectPlayers, playerName]);

  // If currentQuestion changes and it's a daily double, update state
  useEffect(() => {
    if (currentQuestion?.double_big_head && currentQuestion.bet) {
      setShowDoubleBigHeadQuestion(true);
    }
  }, [currentQuestion]);

  // Auto-focus answer input when this player buzzes in
  useEffect(() => {
    if (lastBuzzer && lastBuzzer === playerName && !answerSubmitted) {
      setAnswerText('');
      // Small delay to let the DOM render the input
      setTimeout(() => {
        answerInputRef.current?.focus();
      }, 50);
    }
  }, [lastBuzzer, playerName, answerSubmitted]);

  // Log state for debugging
  useEffect(() => {
    console.log("Modal state:", { 
      currentQuestion, 
      doubleBigHead: state.doubleBigHead, 
      showDoubleBigHeadQuestion,
      buzzerActive,
      showActiveBuzzer,
      hasBeenActivated: hasBeenActivatedRef.current,
      answerTimer: state.answerTimer
    });
  }, [currentQuestion, state.doubleBigHead, showDoubleBigHeadQuestion, buzzerActive, showActiveBuzzer, state.answerTimer]);

  // Don't render anything if there's no current question or daily double
  if (!currentQuestion && !state.doubleBigHead) {
    console.log("Not showing modal - no currentQuestion or doubleBigHead");
    return null;
  }

  // Handle buzzer press
  const handleBuzz = () => {
    if (showActiveBuzzer) {
      sendMessage('com.sc2ctl.bighead.buzzer', {
        contestant: playerName
      });
    }
  };

  // Handle bet submission
  const handleBetSubmit = () => {
    if (state.doubleBigHead && playerName === state.doubleBigHead.selectingPlayer) {
      sendMessage('com.sc2ctl.bighead.double_big_head_bet', {
        contestant: playerName,
        bet: betAmount
      });
    }
  };

  // Handle answer submission from modal input
  const handleAnswerSubmit = () => {
    if (answerText.trim() === '') return;
    submitAnswer(answerText.trim());
  };

  // Calculate max bet for the selecting player
  const getMaxBet = () => {
    if (!state.doubleBigHead?.selectingPlayer || !players) return 1000;
    const playerScore = players[state.doubleBigHead.selectingPlayer]?.score || 0;
    return Math.max(1000, playerScore);
  };

  // If we have a daily double but not yet the question
  if (state.doubleBigHead) {
    const selectingPlayer = state.doubleBigHead.selectingPlayer;
    const isSelectingPlayer = playerName === selectingPlayer;
    const maxBet = getMaxBet();

    console.log("Showing daily double selection screen", { selectingPlayer, isSelectingPlayer, playerName });
    return (
      <div className="modal-overlay">
        <div className="modal-content double-big-head">
          <h2>Double Big Head!</h2>
          <p className="double-big-head-info">{state.doubleBigHead.category} - ${state.doubleBigHead.value}</p>

          {isSelectingPlayer ? (
            <div className="bet-input-container">
              <p>Enter your wager:</p>
              <div className="bet-controls">
                <input
                  type="number"
                  min="5"
                  max={maxBet}
                  value={betAmount}
                  onChange={(e) => setBetAmount(Math.max(5, Math.min(maxBet, parseInt(e.target.value) || 5)))}
                  className="bet-input"
                />
                <span className="bet-range">(${5} - ${maxBet})</span>
              </div>
              <button onClick={handleBetSubmit} className="bet-submit-btn">
                Place Wager
              </button>
            </div>
          ) : (
            <p className="waiting-message">
              {selectingPlayer ? `${selectingPlayer} is placing their wager...` : 'Waiting for wager...'}
            </p>
          )}
        </div>
      </div>
    );
  }

  // If current question is a daily double but we haven't shown it yet
  if (currentQuestion?.double_big_head && !showDoubleBigHeadQuestion) {
    console.log("Showing daily double bet info before revealing question");
    return (
      <div className="modal-overlay">
        <div className="modal-content double-big-head">
          <h2>Double Big Head!</h2>
          <p className="double-big-head-info">{currentQuestion.category} - ${currentQuestion.value}</p>
          <p className="double-big-head-info">Player: {currentQuestion.contestant}</p>
          <p className="double-big-head-info">Bet: ${currentQuestion.bet}</p>
          
          {playerName === currentQuestion.contestant ? (
            <p>Wait for the host to reveal the question...</p>
          ) : (
            <p>{currentQuestion.contestant} has placed a bet of ${currentQuestion.bet}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>{currentQuestion.category} - ${currentQuestion.value}</h2>
        {currentQuestion.double_big_head && <h3 className="double-big-head-banner">Double Big Head!</h3>}
        <p className="question-text">{currentQuestion.text}</p>
        
        {!currentQuestion.double_big_head && !lastBuzzer && !incorrectPlayers.includes(playerName) && (
          <div
            className={`player-buzzer ${showActiveBuzzer ? 'active' : ''}`}
            onClick={handleBuzz}
          >
            {showActiveBuzzer ? 'BUZZ IN! (Space)' : 'Wait...'}
          </div>
        )}

        {!currentQuestion.double_big_head && !lastBuzzer && incorrectPlayers.includes(playerName) && (
          <p className="waiting-message">You already answered this one. Waiting for other players...</p>
        )}
        
        {lastBuzzer && lastBuzzer === playerName && !answerSubmitted && (
          <div className="answer-input-container">
            <input
              ref={answerInputRef}
              type="text"
              className="answer-input"
              placeholder="Type your answer..."
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Enter') handleAnswerSubmit();
              }}
            />
            <button className="answer-submit-btn" onClick={handleAnswerSubmit}>
              Submit
            </button>
          </div>
        )}

        {lastBuzzer && lastBuzzer === playerName && answerSubmitted && (
          <p className="answer-submitted-text">Answer submitted...</p>
        )}
        
        {/* Unified bottom timer bar for buzzer countdown and answer countdown */}
        {(showActiveBuzzer || (answerTimer.active && lastBuzzer)) && (
          <div className="timer-container">
            <div
              className="timer-bar"
              style={{ width: `${100 - (answerTimer.active && lastBuzzer ? answerTimerProgress : timerProgress)}%` }}
            ></div>
          </div>
        )}
        
      </div>
    </div>
  );
} 