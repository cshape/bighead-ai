import React from 'react';
import { useGame } from '../../contexts/GameContext';

export default function QuestionCell({ question, categoryName, isAdmin, isPlaceholder, canSelect }) {
  const { sendMessage } = useGame();

  const handleClick = () => {
    // Allow admin OR controlling player to select clues
    if ((!isAdmin && !canSelect) || question.used || isPlaceholder) return;

    // If it's a daily double, use a different message
    if (question.double_big_head) {
      sendMessage('com.sc2ctl.bighead.double_big_head', {
        category: categoryName,
        value: question.value
      });
    } else {
      sendMessage('com.sc2ctl.bighead.question_display', {
        category: categoryName,
        value: question.value
      });
    }
  };

  return (
    <div
      className={`question ${question.used ? 'used' : ''} ${isPlaceholder ? 'placeholder' : ''}`}
      onClick={handleClick}
    >
      ${question.value}
    </div>
  );
} 