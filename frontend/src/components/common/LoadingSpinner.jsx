import React from 'react';

export default function LoadingSpinner({ message = 'Loading...', isOverlay = false }) {
  if (isOverlay) {
    return (
      <div className="modal-overlay">
        <div className="glass-card loading-card-wrapper">
          <div className="spinner"></div>
          <p className="loading-message-text">{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="inline-spinner-wrapper">
      <div className="spinner"></div>
      <p className="loading-message-text">{message}</p>
    </div>
  );
}
