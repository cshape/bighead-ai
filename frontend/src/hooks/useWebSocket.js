import { useEffect, useRef, useCallback, useState } from 'react';
import { getWebSocketUrl, getLegacyWebSocketUrl } from '../config';

/**
 * WebSocket hook with support for game-specific connections.
 *
 * @param {string} urlOrGameCode - Either a full URL or a game code
 * @param {function} onMessage - Callback for incoming messages
 * @param {object} options - Additional options
 * @param {boolean} options.isGameCode - If true, treats first param as game code
 * @param {boolean} options.autoConnect - If true (default), connects automatically
 */
export default function useWebSocket(urlOrGameCode, onMessage, options = {}) {
  const { isGameCode = false, autoConnect = true } = options;

  const ws = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const [isConnected, setIsConnected] = useState(false);

  // Determine the URL to use
  const url = isGameCode
    ? getWebSocketUrl(urlOrGameCode)
    : urlOrGameCode || getLegacyWebSocketUrl();

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    console.log('Connecting to WebSocket:', url);
    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('WebSocket message received:', message);

      if (onMessage && typeof onMessage === 'function') {
        onMessage(message);
      }
    };

    ws.current.onopen = () => {
      console.log('WebSocket connection established');
      reconnectAttempts.current = 0;
      setIsConnected(true);
    };

    ws.current.onclose = (event) => {
      setIsConnected(false);

      // Don't reconnect if closed intentionally (code 4004 = game not found)
      if (event.code === 4004) {
        console.log('Game not found, not reconnecting');
        return;
      }

      if (reconnectAttempts.current < maxReconnectAttempts) {
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000);
        console.log(`WebSocket closed. Reconnecting in ${timeout}ms...`);
        reconnectAttempts.current += 1;
        setTimeout(connect, timeout);
      }
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }, [url, onMessage]);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect, autoConnect]);

  const sendMessage = useCallback(
    (message, payload) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        // If message is an object with a topic property, use it as is
        // Otherwise, construct a message object from the message (topic) and payload parameters
        const messageToSend =
          typeof message === 'object' && message.topic
            ? message
            : { topic: message, payload: payload };

        console.log('Sending WebSocket message:', messageToSend);
        ws.current.send(JSON.stringify(messageToSend));
      } else {
        console.warn('WebSocket not connected, attempting to reconnect...');
        connect();
      }
    },
    [connect]
  );

  const disconnect = useCallback(() => {
    if (ws.current) {
      ws.current.close();
      ws.current = null;
      setIsConnected(false);
    }
  }, []);

  return {
    sendMessage,
    connect,
    disconnect,
    isConnected,
    ws: ws.current,
  };
} 