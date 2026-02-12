import React, { useState, useEffect, useRef } from 'react';
import { getApiUrl } from '../../config';
import './VoiceSelector.css';

const FALLBACK_VOICES = [
  { id: 'Clive', name: 'Clive' },
  { id: 'Dennis', name: 'Dennis' },
  { id: 'Wendy', name: 'Wendy' },
  { id: 'Ashley', name: 'Ashley' },
];

function VoiceSelector({ value, onChange, disabled }) {
  const [voices, setVoices] = useState(FALLBACK_VOICES);
  const [previewLoading, setPreviewLoading] = useState(null);
  const audioRef = useRef(null);

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

  const handleVoiceClick = async (voiceId) => {
    onChange(voiceId);

    // Play TTS preview
    setPreviewLoading(voiceId);
    try {
      const res = await fetch(getApiUrl(`/api/games/voices/preview/${voiceId}`));
      if (!res.ok) throw new Error('Preview failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => URL.revokeObjectURL(url);
      audio.play();
    } catch {
      // Silently fail - voice is still selected
    } finally {
      setPreviewLoading(null);
    }
  };

  return (
    <div className="voice-selector">
      <label className="voice-label">AI Host Voice</label>
      <div className="voice-options">
        {voices.map((v) => (
          <button
            key={v.id}
            type="button"
            className={`voice-option ${value === v.id ? 'active' : ''}`}
            onClick={() => handleVoiceClick(v.id)}
            disabled={disabled || previewLoading === v.id}
          >
            <span className="voice-name">{v.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default VoiceSelector;
