import React from 'react';

export default function Sidebar({ activeTab, setActiveTab, activeResume }) {
  return (
    <aside className="sidebar-frost-panel">
      <div className="sidebar-brand">
        <span className="sidebar-logo-icon">💼</span>
        <h2 className="sidebar-brand-name">CareerFlow AI</h2>
      </div>

      <nav className="sidebar-nav-group">
        <button 
          onClick={() => setActiveTab('dashboard')} 
          className={`sidebar-nav-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
        >
          <span className="sidebar-nav-icon">📊</span> Kanban CRM Board
        </button>
        
        <button 
          onClick={() => setActiveTab('optimizer')} 
          className={`sidebar-nav-btn ${activeTab === 'optimizer' ? 'active' : ''}`}
        >
          <span className="sidebar-nav-icon">🔍</span> Resume ATS Matcher
        </button>
        
        <button 
          onClick={() => setActiveTab('practice')} 
          className={`sidebar-nav-btn ${activeTab === 'practice' ? 'active' : ''}`}
        >
          <span className="sidebar-nav-icon">🗣️</span> AI Interview Practice
        </button>

        <button 
          onClick={() => setActiveTab('analytics')} 
          className={`sidebar-nav-btn ${activeTab === 'analytics' ? 'active' : ''}`}
        >
          <span className="sidebar-nav-icon">📈</span> Lakehouse Analytics
        </button>
      </nav>

      {/* Active Resume Status Badge */}
      <div className="sidebar-resume-status-box">
        <h4 className="sidebar-status-header">Active Profile</h4>
        {activeResume ? (
          <div className="sidebar-active-profile-info">
            <div className="sidebar-profile-title-row">
              <span className="pulse-indicator"></span>
              <span className="sidebar-file-name" title={activeResume.file_name}>
                {activeResume.file_name}
              </span>
            </div>
            <p className="sidebar-created-date">
              Uploaded: {new Date(activeResume.created_date).toLocaleDateString()}
            </p>
          </div>
        ) : (
          <div className="sidebar-no-profile" onClick={() => setActiveTab('optimizer')}>
            <span className="warning-icon">⚠️</span>
            <p className="no-profile-text">No Resume Uploaded</p>
            <span className="upload-prompt">Click to upload PDF</span>
          </div>
        )}
      </div>
    </aside>
  );
}
