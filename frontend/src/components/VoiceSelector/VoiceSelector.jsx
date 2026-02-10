import React, { useState, useEffect } from 'react';
import { getApiUrl } from '../../config';
import './VoiceSelector.css';

const FALLBACK_VOICES = [
  { id: 'Timothy', name: 'Timothy', description: 'Default male host voice' },
  { id: 'Dennis', name: 'Dennis', description: 'Smooth, calm and friendly male voice' },
  { id: 'Alex', name: 'Alex', description: 'Energetic and expressive male voice' },
  { id: 'Ashley', name: 'Ashley', description: 'Warm, natural female voice' },
];

function VoiceSelector({ value, onChange, disabled }) {
  const [voices, setVoices] = useState(FALLBACK_VOICES);

  useEffect(() => {
    fetch(getApiUrl('/api/games/voices'))
      .then((res) => res.json())
      .then((data) => {
        if (data.voices && data.voices.length > 0) {
          setVoices(data.voices);
        }
      })
      .catch(() => {
        // Keep fallback voices
      });
  }, []);

  return (
    <div className="voice-selector">
      <label className="voice-label">AI Host Voice</label>
      <div className="voice-options">
        {voices.map((v) => (
          <button
            key={v.id}
            type="button"
            className={`voice-option ${value === v.id ? 'active' : ''}`}
            onClick={() => onChange(v.id)}
            disabled={disabled}
            title={v.description}
          >
            <span className="voice-name">{v.name}</span>
            {v.description && (
              <span className="voice-desc">{v.description}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export default VoiceSelector;
