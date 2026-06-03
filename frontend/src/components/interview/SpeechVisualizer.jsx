import React from 'react';

export default function SpeechVisualizer({ isSpeaking, isListening }) {
  const getStatusText = () => {
    if (isSpeaking) return "Speaking";
    if (isListening) return "Listening";
    return "Idle";
  };

  const getStatusClass = () => {
    if (isSpeaking) return "speaking";
    if (isListening) return "listening";
    return "idle";
  };

  return (
    <div className={`avatar-status-visualizer ${getStatusClass()}`}>
      <div className="pulsing-avatar-wrapper">
        <div className="pulse-layer outer-pulse"></div>
        <div className="pulse-layer inner-pulse"></div>
        <div className="avatar-core-circle">
          <span className="avatar-state-label">{getStatusText()}</span>
        </div>
      </div>
      
      {/* Animated CSS Audio wave bars */}
      <div className="audio-wave-bars-container">
        {[20, 45, 15, 38, 10, 25, 42, 18].map((baseHeight, idx) => {
          let height = '6px';
          if (isSpeaking) {
            height = `${baseHeight}px`;
          } else if (isListening) {
            height = `${baseHeight * 0.75}px`;
          }
          return (
            <span 
              key={idx}
              className={`audio-wave-bar ${isSpeaking ? 'speaking' : isListening ? 'listening' : 'idle'}`}
              style={{ 
                height,
                animationDelay: `${idx * 0.15}s`
              }}
            ></span>
          );
        })}
      </div>
    </div>
  );
}
