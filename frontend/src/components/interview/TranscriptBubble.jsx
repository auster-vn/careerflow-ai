import React from 'react';

export default function TranscriptBubble({ log }) {
  const isAI = log.speaker === 'AI';

  const renderFeedbackList = (feedbackText) => {
    if (!feedbackText) return null;
    
    // Split and filter empty lines
    const lines = feedbackText.split('\n').map(l => l.trim()).filter(Boolean);
    
    return (
      <ul className="evaluation-feedback-list">
        {lines.map((line, i) => {
          const cleanLine = line.replace(/^[-*•]\s*/, '');
          return (
            <li key={i} className="evaluation-feedback-item">
              {cleanLine}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <div className={`chat-bubble-container ${isAI ? 'ai' : 'user'}`}>
      <div className={`chat-bubble ${isAI ? 'ai' : 'user'}`}>
        <p className="bubble-message-text">{log.message}</p>
        <span className="bubble-time-stamp">
          {new Date(log.created_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      {/* Renders Grading card for user responses */}
      {!isAI && log.score !== undefined && (
        <div className="glass-card evaluation-grade-card">
          <div className="evaluation-card-header">
            <span className="evaluation-score-badge">Score: {log.score}/10</span>
            <span className="evaluation-author-label">AI Evaluation</span>
          </div>
          
          {renderFeedbackList(log.feedback)}
          
          {log.model_answer && (
            <div className="evaluation-model-guide-box">
              <h5 className="model-guide-header">Model Answer Guide:</h5>
              <p className="model-guide-text">"{log.model_answer}"</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
