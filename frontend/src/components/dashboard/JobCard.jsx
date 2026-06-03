import React from 'react';

export default function JobCard({ 
  job, 
  prediction, 
  onDelete, 
  onOptimize, 
  onInterview, 
  onToggleForecast,
  onDragStart 
}) {
  return (
    <div 
      draggable 
      onDragStart={(e) => onDragStart(e, job.id)}
      className="glass-card kanban-job-card"
    >
      <div className="job-card-header">
        <h4 className="job-card-title" title={job.job_title}>
          {job.job_title}
        </h4>
        <button 
          onClick={() => onDelete(job.id, job.company_name)} 
          className="job-card-delete-btn"
          title="Delete Position"
        >
          &times;
        </button>
      </div>
      
      <p className="job-card-company">{job.company_name}</p>
      
      <div className="job-card-tags-row">
        {job.salary_range && (
          <span className="job-card-salary-tag">
            💰 {job.salary_range}
          </span>
        )}

        {/* Interactive Apply Link */}
        {job.job_url && (
          <a 
            href={job.job_url} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="job-card-apply-link"
            title="Apply directly to this position"
            draggable={false}
            onDragStart={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            🔗 Apply Now
          </a>
        )}
      </div>

      {/* XGBoost Real-Time Forecast Panel */}
      {prediction && (
        <div className="xgb-forecast-box">
          <h5 className="xgb-forecast-title">🧠 XGBoost Forecast Engine</h5>
          
          <div className="xgb-metric-row">
            <span className="xgb-metric-label">Forecasted Salary</span>
            <span className="xgb-metric-value">
              ${(prediction.salary / 1000).toFixed(0)}K
            </span>
          </div>

          <div className="xgb-metric-row">
            <span className="xgb-metric-label">ATS Resume Match</span>
            <div className="xgb-bar-container">
              <div className="xgb-progress-bar-bg">
                <div 
                  className={`xgb-progress-bar-fill ${
                    prediction.match >= 75 ? 'emerald' : prediction.match >= 50 ? 'amber' : 'rose'
                  }`}
                  style={{ width: `${prediction.match || 0}%` }}
                ></div>
              </div>
              <span className="xgb-percent-text">
                {prediction.match ? prediction.match.toFixed(0) : '0'}%
              </span>
            </div>
          </div>

          <div className="xgb-metric-row">
            <span className="xgb-metric-label">Hire Probability</span>
            <div className="xgb-bar-container">
              <div className="xgb-progress-bar-bg">
                <div 
                  className={`xgb-progress-bar-fill ${
                    prediction.success >= 75 ? 'emerald' : prediction.success >= 50 ? 'amber' : 'rose'
                  }`}
                  style={{ width: `${prediction.success || 0}%` }}
                ></div>
              </div>
              <span className="xgb-percent-text">
                {prediction.success ? prediction.success.toFixed(0) : '0'}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Action buttons footer */}
      <div className="job-card-actions-footer">
        <button 
          onClick={() => onOptimize(job)} 
          className="job-card-action-btn optimize-btn"
          title="Optimize Resume ATS Match"
        >
          🔍 Match
        </button>
        
        <button 
          onClick={() => onToggleForecast(job.id)} 
          className="job-card-action-btn forecast-btn"
          title="Run XGBoost AI Predictions"
        >
          🔮 Forecast
        </button>

        <button 
          onClick={() => onInterview(job)} 
          className="job-card-action-btn interview-btn"
          title="Practice Mock Interview"
        >
          🗣️ Practice
        </button>
      </div>
    </div>
  );
}
