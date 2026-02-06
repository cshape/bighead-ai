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

  // Keep onMessage in a ref so connect() doesn't depend on it.
  // This prevents connect from being recreated when onMessage changes,
  // which would cause the useEffect cleanup to close and reopen the WS.
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  // Flag to distinguish intentional cleanup closes from unexpected disconnects.
  // When the useEffect cleanup fires (e.g. URL changed), we set this to true
  // so the onclose handler doesn't try to reconnect with the stale URL.
  const intentionalClose = useRef(false);

  // Queue messages sent while the socket is not open. Flushed on next open.
  const messageQueue = useRef([]);

  // Determine the URL to use
  const url = isGameCode
    ? getWebSocketUrl(urlOrGameCode)
    : urlOrGameCode || getLegacyWebSocketUrl();

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    // Reset the intentional-close flag when we deliberately connect
    intentionalClose.current = false;

    console.log('Connecting to WebSocket:', url);
    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('WebSocket message received:', message);

      if (onMessageRef.current && typeof onMessageRef.current === 'function') {
        onMessageRef.current(message);
      }
    };

    ws.current.onopen = () => {
      console.log('WebSocket connection established');
      reconnectAttempts.current = 0;
      setIsConnected(true);

      // Flush any queued messages
      while (messageQueue.current.length > 0) {
        const queued = messageQueue.current.shift();
        console.log('Flushing queued WebSocket message:', queued);
        ws.current.send(JSON.stringify(queued));
      }
    };

    ws.current.onclose = (event) => {
      setIsConnected(false);

      // Don't reconnect if closed intentionally by our cleanup
      if (intentionalClose.current) {
        console.log('WebSocket closed intentionally, not reconnecting');
        return;
      }

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
  }, [url]);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    return () => {
      if (ws.current) {
        intentionalClose.current = true;
        ws.current.close();
      }
    };
  }, [connect, autoConnect]);

  const sendMessage = useCallback(
    (message, payload) => {
      // Build the message object
      const messageToSend =
        typeof message === 'object' && message.topic
          ? message
          : { topic: message, payload: payload };

      if (ws.current?.readyState === WebSocket.OPEN) {
        console.log('Sending WebSocket message:', messageToSend);
        ws.current.send(JSON.stringify(messageToSend));
      } else {
        console.warn('WebSocket not connected, queueing message and reconnecting...');
        messageQueue.current.push(messageToSend);
        connect();
      }
    },
    [connect]
  );

  const disconnect = useCallback(() => {
    if (ws.current) {
      intentionalClose.current = true;
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
