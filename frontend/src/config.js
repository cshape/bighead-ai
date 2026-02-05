/**
 * Application configuration loaded from environment variables.
 *
 * In development, these are set via Vite's proxy (vite.config.js).
 * In production, these are injected at build time from environment variables.
 */

// API URL for HTTP requests
export const API_URL = import.meta.env.VITE_API_URL || '';

// WebSocket URL
export const WS_URL = import.meta.env.VITE_WS_URL || '';

/**
 * Get the full API endpoint URL.
 * @param {string} path - The API path (e.g., '/api/games/create')
 * @returns {string} The full URL
 */
export function getApiUrl(path) {
  if (API_URL) {
    return `${API_URL}${path}`;
  }
  // In development with Vite proxy, just use relative paths
  return path;
}

/**
 * Get the WebSocket URL for a specific game.
 * @param {string} gameCode - The 6-digit game code
 * @returns {string} The full WebSocket URL
 */
export function getWebSocketUrl(gameCode) {
  if (WS_URL) {
    // Production: use the configured WebSocket URL
    const protocol = WS_URL.startsWith('wss') ? 'wss:' : 'ws:';
    const host = WS_URL.replace(/^wss?:\/\//, '');
    return `${protocol}//${host}/ws/${gameCode}`;
  }

  // Development: use current host with WebSocket protocol
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/${gameCode}`;
}

/**
 * Get the legacy WebSocket URL (no game code).
 * Used for backward compatibility with single-game mode.
 * @returns {string} The WebSocket URL
 */
export function getLegacyWebSocketUrl() {
  if (WS_URL) {
    const protocol = WS_URL.startsWith('wss') ? 'wss:' : 'ws:';
    const host = WS_URL.replace(/^wss?:\/\//, '');
    return `${protocol}//${host}/ws`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export default {
  API_URL,
  WS_URL,
  getApiUrl,
  getWebSocketUrl,
  getLegacyWebSocketUrl,
};
