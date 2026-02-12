import React, { useState } from 'react';
import { useGame } from '../../contexts/GameContext';
import './Modal.css';

export default function PlayerRegistrationModal() {
  const [name, setName] = useState('');
  const [preferences, setPreferences] = useState('');
  const { sendMessage } = useGame();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    
    sendMessage('com.sc2ctl.bighead.register_player', {
      name: name.trim(),
      preferences: preferences.trim()
    });
  };

  return (
    <div className="modal">
      <div className="modal-content">
        <h2>Enter Your Name</h2>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            className="player-name-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
          />
          <input
            type="text"
            className="player-preferences-input"
            value={preferences}
            onChange={(e) => setPreferences(e.target.value)}
            placeholder="What kinds of categories do you want?"
          />
          <button type="submit" className="join-game-button">Join Game</button>
        </form>
      </div>
    </div>
  );
} 