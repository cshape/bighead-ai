import React, { useState, useEffect, useRef } from 'react';
import { useGame } from '../../contexts/GameContext';
import './Modal.css';

export default function QuestionModal() {
  const { state, sendMessage } = useGame();
  const { currentQuestion, buzzerActive, lastBuzzer, playerName, answerTimer, players } = state;
  const [showDailyDoubleQuestion, setShowDailyDoubleQuestion] = useState(false);
  const [timerProgress, setTimerProgress] = useState(0);
  const [answerTimerProgress, setAnswerTimerProgress] = useState(0);
  const [betAmount, setBetAmount] = useState(5);
  
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
      if (e.code === 'Space' && showActiveBuzzer) {
        handleBuzz();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [showActiveBuzzer]);

  // If currentQuestion changes and it's a daily double, update state
  useEffect(() => {
    if (currentQuestion?.daily_double && currentQuestion.bet) {
      setShowDailyDoubleQuestion(true);
    }
  }, [currentQuestion]);

  // Log state for debugging
  useEffect(() => {
    console.log("Modal state:", { 
      currentQuestion, 
      dailyDouble: state.dailyDouble, 
      showDailyDoubleQuestion,
      buzzerActive,
      showActiveBuzzer,
      hasBeenActivated: hasBeenActivatedRef.current,
      answerTimer: state.answerTimer
    });
  }, [currentQuestion, state.dailyDouble, showDailyDoubleQuestion, buzzerActive, showActiveBuzzer, state.answerTimer]);

  // Don't render anything if there's no current question or daily double
  if (!currentQuestion && !state.dailyDouble) {
    console.log("Not showing modal - no currentQuestion or dailyDouble");
    return null;
  }

  // Handle buzzer press
  const handleBuzz = () => {
    if (showActiveBuzzer) {
      sendMessage('com.sc2ctl.jeopardy.buzzer', {
        contestant: playerName
      });
    }
  };

  // Handle bet submission
  const handleBetSubmit = () => {
    if (state.dailyDouble && playerName === state.dailyDouble.selectingPlayer) {
      sendMessage('com.sc2ctl.jeopardy.daily_double_bet', {
        contestant: playerName,
        bet: betAmount
      });
    }
  };

  // Calculate max bet for the selecting player
  const getMaxBet = () => {
    if (!state.dailyDouble?.selectingPlayer || !players) return 1000;
    const playerScore = players[state.dailyDouble.selectingPlayer]?.score || 0;
    return Math.max(1000, playerScore);
  };

  // If we have a daily double but not yet the question
  if (state.dailyDouble) {
    const selectingPlayer = state.dailyDouble.selectingPlayer;
    const isSelectingPlayer = playerName === selectingPlayer;
    const maxBet = getMaxBet();

    console.log("Showing daily double selection screen", { selectingPlayer, isSelectingPlayer, playerName });
    return (
      <div className="modal-overlay">
        <div className="modal-content daily-double">
          <h2>Daily Double!</h2>
          <p>{state.dailyDouble.category} - ${state.dailyDouble.value}</p>

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
  if (currentQuestion?.daily_double && !showDailyDoubleQuestion) {
    console.log("Showing daily double bet info before revealing question");
    return (
      <div className="modal-overlay">
        <div className="modal-content daily-double">
          <h2>Daily Double!</h2>
          <p>{currentQuestion.category} - ${currentQuestion.value}</p>
          <p>Player: {currentQuestion.contestant}</p>
          <p>Bet: ${currentQuestion.bet}</p>
          
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
        {currentQuestion.daily_double && <h3 className="daily-double-banner">Daily Double!</h3>}
        <p className="question-text">{currentQuestion.text}</p>
        
        {!currentQuestion.daily_double && !lastBuzzer && (
          <div 
            className={`player-buzzer ${showActiveBuzzer ? 'active' : ''}`}
            onClick={handleBuzz}
          >
            {showActiveBuzzer ? 'BUZZ IN! (Space)' : 'Wait...'}
          </div>
        )}
        
        {lastBuzzer && (
          <div className="timer-container answer-timer">
            <div
              className="timer-bar answer"
              style={{ width: `${100 - answerTimerProgress}%` }}
            ></div>
          </div>
        )}
        
        {/* Buzzer timer - only show when buzzer is active */}
        {showActiveBuzzer && (
          <div className="timer-container">
            <div 
              className="timer-bar" 
              style={{ width: `${100 - timerProgress}%` }}
            ></div>
          </div>
        )}
        
      </div>
    </div>
  );
} 