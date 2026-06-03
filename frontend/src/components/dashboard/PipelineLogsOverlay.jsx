import React from 'react';

export default function PipelineLogsOverlay({ steps, currentStep, isVisible }) {
  if (!isVisible) return null;

  return (
    <div className="modal-overlay">
      <div className="glass-card pipeline-logs-card">
        <div className="pipeline-logs-header">
          <div className="spinner-small"></div>
          <h3 className="pipeline-logs-title">
            🔍 Lakehouse ETL Pipeline Active
          </h3>
        </div>
        
        <div className="pipeline-logs-container">
          {steps.map((step, idx) => {
            const isCompleted = idx < currentStep;
            const isActive = idx === currentStep;
            return (
              <div 
                key={idx} 
                className={`pipeline-log-line ${isCompleted ? 'completed' : isActive ? 'active' : 'pending'}`}
              >
                <span className="pipeline-log-icon-status">
                  {isCompleted ? "✓" : isActive ? "⚡" : "○"}
                </span>
                <span className="pipeline-log-text">{step}</span>
              </div>
            );
          })}
        </div>
        
        <p className="pipeline-logs-footer-notice">
          S3 Medallion storage partitions are automatically synced upon completion.
        </p>
      </div>
    </div>
  );
}
