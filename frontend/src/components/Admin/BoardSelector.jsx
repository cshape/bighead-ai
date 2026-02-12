import React, { useState, useEffect } from 'react';
import { useGame } from '../../contexts/GameContext';
import './BoardSelector.css';

export default function BoardSelector() {
  const [boards, setBoards] = useState([]);
  const [error, setError] = useState(null);
  const { sendMessage } = useGame();

  useEffect(() => {
    fetch('/api/boards')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch boards');
        return res.json();
      })
      .then(data => {
        if (Array.isArray(data.boards)) {
          // Transform the board names into objects with id and name
          const boardList = data.boards.map(boardName => ({
            id: boardName,
            name: boardName
          }));
          setBoards(boardList);
        } else {
          throw new Error('Invalid board data format');
        }
      })
      .catch(err => {
        console.error('Error loading boards:', err);
        setError(err.message);
      });
  }, []);

  const handleBoardSelect = (boardId) => {
    sendMessage('com.sc2ctl.bighead.select_board', { boardId });
  };

  if (error) {
    return (
      <div className="board-selector error">
        <h2>Error Loading Boards</h2>
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="board-selector">
      <h2>Select a Game Board</h2>
      {boards.length === 0 ? (
        <div>Loading boards...</div>
      ) : (
        <div className="board-list">
          {boards.map(board => (
            <button 
              key={board.id}
              onClick={() => handleBoardSelect(board.id)}
              className="board-option"
            >
              {board.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
} 