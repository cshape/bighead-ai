import React, { useState, useEffect } from 'react';
import './ThemeSelector.css';

const THEMES = [
  { id: 'ancient-map', label: 'Ancient Map' },
  { id: 'classic', label: 'Classic Blue' },
  { id: 'midnight', label: 'Midnight' },
];

function ThemeSelector() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('bighead-theme') || 'ancient-map';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('bighead-theme', theme);
  }, [theme]);

  // Apply saved theme on mount
  useEffect(() => {
    const saved = localStorage.getItem('bighead-theme');
    if (saved) {
      document.documentElement.setAttribute('data-theme', saved);
    }
  }, []);

  return (
    <div className="theme-selector">
      {THEMES.map((t) => (
        <button
          key={t.id}
          className={`theme-btn ${theme === t.id ? 'active' : ''}`}
          onClick={() => setTheme(t.id)}
          title={t.label}
        >
          <span className={`theme-swatch theme-swatch--${t.id}`} />
          <span className="theme-label">{t.label}</span>
        </button>
      ))}
    </div>
  );
}

export default ThemeSelector;
