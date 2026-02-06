import React from 'react';
import QuestionCell from './QuestionCell';

export default function CategoryColumn({ category, isAdmin, isPlaceholder, isRevealing, canSelect }) {
  return (
    <div className={`category ${isPlaceholder ? 'placeholder' : ''} ${isRevealing ? 'revealing' : ''}`}>
      <div className="category-title">{category.name}</div>
      {category.questions.map((question, index) => (
        <QuestionCell
          key={index}
          question={{
            ...question,
            used: question.used || false // ensure used property exists
          }}
          categoryName={category.name}
          isAdmin={isAdmin}
          isPlaceholder={isPlaceholder || question.isPlaceholder}
          canSelect={canSelect}
        />
      ))}
    </div>
  );
} 