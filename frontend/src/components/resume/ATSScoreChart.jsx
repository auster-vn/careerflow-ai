import React from 'react';

export default function ATSScoreChart({ score }) {
  const roundedScore = Math.round(score);
  
  const getScoreColor = (val) => {
    if (val >= 80) return 'var(--accent-emerald)';
    if (val >= 50) return 'var(--accent-amber)';
    return 'var(--accent-rose)';
  };

  // 2 * Math.PI * r = 2 * 3.1416 * 50 = 314.16
  const strokeDashoffset = 314.16 - (314.16 * roundedScore) / 100;

  return (
    <div className="radial-score-container">
      <svg width="130" height="130" viewBox="0 0 120 120" className="radial-score-svg">
        <circle 
          cx="60" 
          cy="60" 
          r="50" 
          fill="transparent" 
          stroke="rgba(255,255,255,0.02)" 
          strokeWidth="10" 
        />
        <circle 
          cx="60" 
          cy="60" 
          r="50" 
          fill="transparent" 
          stroke={getScoreColor(roundedScore)} 
          strokeWidth="10" 
          strokeDasharray="314.16"
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          transform="rotate(-90 60 60)"
          className="radial-score-bar"
        />
      </svg>
      <div className="radial-score-text-overlay">
        <h2 className="radial-score-number">{roundedScore}%</h2>
        <span className="radial-score-label">Compatibility</span>
      </div>
    </div>
  );
}
