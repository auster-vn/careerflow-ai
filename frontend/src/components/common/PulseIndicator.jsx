import React from 'react';

export default function PulseIndicator({ color = 'var(--accent-teal)', size = '10px' }) {
  return (
    <span 
      className="pulse-indicator" 
      style={{ 
        width: size, 
        height: size, 
        backgroundColor: color,
        '--pulse-color': color 
      }}
    ></span>
  );
}
