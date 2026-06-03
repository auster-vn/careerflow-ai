import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import JobCard from '../components/dashboard/JobCard';
import AddJobModal from '../components/dashboard/AddJobModal';
import PipelineLogsOverlay from '../components/dashboard/PipelineLogsOverlay';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function Dashboard({ onOptimize, onInterview }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  
  // Real-time XGBoost forecasts cache state
  const [predictions, setPredictions] = useState({});

  // Crawling and scraping states
  const [searchKeyword, setSearchKeyword] = useState('');
  const [scraping, setScraping] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  // Big Data pipeline stages
  const pipelineSteps = [
    'Connecting to VietnamWorks and TopCV endpoints...',
    'Running TopCV scraper with curl_cffi TLS bypass...',
    'Running VietnamWorks scraper payload parser...',
    'Streaming raw parquets to MinIO S3 Bronze bucket...',
    'Executing Polars Silver ETL pipeline (standardization)...',
    'Synchronizing clean parquets to local DuckDB Warehouse...',
    'Rebuilding Gold transformations in DBT...'
  ];

  // Load CRM jobs from backend DuckDB
  const fetchJobs = async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
    } catch (e) {
      console.error("Failed to load jobs:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  // Fetch real-time XGBoost predictions
  const handleFetchPredictions = async (appId) => {
    // Toggle collapse if already fetched
    if (predictions[appId]) {
      const updated = { ...predictions };
      delete updated[appId];
      setPredictions(updated);
      return;
    }

    try {
      const dataSal = await api.predictSalary(appId);
      const dataSuc = await api.predictSuccess(appId);

      setPredictions(prev => ({
        ...prev,
        [appId]: {
          salary: dataSal.predicted_median_salary,
          success: dataSuc.success_probability * 100,
          match: dataSuc.match_score
        }
      }));
    } catch (err) {
      console.error("Failed to fetch XGBoost metrics:", err);
      alert("Failed to compile ML forecasts. Please ensure you have uploaded a resume first!");
    }
  };

  // HTML5 Drag and Drop handlers
  const handleDragStart = (e, id) => {
    e.dataTransfer.setData('text/plain', id);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = async (e, targetStatus) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain');
    if (!id) return;

    // Optimistically update state
    const originalJobs = [...jobs];
    setJobs(jobs.map(j => j.id === id ? { ...j, status: targetStatus } : j));

    try {
      await api.updateJobStatus(id, targetStatus);
      fetchJobs(); // Refresh to catch updated dates
    } catch (err) {
      setJobs(originalJobs); // Rollback
      console.error("Failed to update status:", err);
    }
  };

  // Form submission handler
  const handleCreateJob = async (jobData) => {
    try {
      await api.createJob(jobData);
      setShowAddModal(false);
      fetchJobs(); // Reload board
    } catch (err) {
      console.error("Job creation failed:", err);
    }
  };

  // Delete card handler
  const handleDeleteJob = async (id, company) => {
    if (!window.confirm(`Are you sure you want to delete the job application for ${company}?`)) {
      return;
    }
    try {
      await api.deleteJob(id);
      fetchJobs();
    } catch (err) {
      console.error("Failed to delete job card:", err);
    }
  };

  // Handle cào tìm kiếm việc làm từ TopCV / VietnamWorks
  const handleScrapeJobs = async (e) => {
    if (e) e.preventDefault();
    const query = searchKeyword.trim();
    if (!query) return;

    setScraping(true);
    setCurrentStep(0);
    
    // Set periodic status updates to show pipeline progression logs
    let stepIdx = 0;
    const interval = setInterval(() => {
      if (stepIdx < pipelineSteps.length - 1) {
        stepIdx++;
        setCurrentStep(stepIdx);
      }
    }, 1200);

    try {
      const data = await api.scrapeJobs(query);
      clearInterval(interval);
      alert(`🎉 Successfully crawled & synced ${data.jobs?.length || 0} jobs into your Wishlist column!`);
      setSearchKeyword('');
      fetchJobs(); // Reload jobs from DuckDB
    } catch (err) {
      clearInterval(interval);
      console.error("Scraper failed:", err);
      alert(err.message || "Failed to connect to job scraper service.");
    } finally {
      setScraping(false);
      setCurrentStep(0);
    }
  };

  // Handle xóa toàn bộ công việc trong DuckDB
  const handleClearAll = async () => {
    if (!window.confirm("🧹 Are you sure you want to clear all job applications and mock transcripts? This action is permanent!")) {
      return;
    }
    
    try {
      await api.clearAll();
      alert("Successfully cleared all records!");
      fetchJobs(); // Reload board (will show empty columns)
    } catch (err) {
      console.error("Clear all failed:", err);
      alert("Failed to contact server to clear records.");
    }
  };

  // Columns specification
  const columns = [
    { title: 'Wishlist', status: 'WISHLIST', color: 'var(--text-secondary)' },
    { title: 'Applied', status: 'APPLIED', color: '#3b82f6' },
    { title: 'Interviewing', status: 'INTERVIEWING', color: 'var(--accent-teal)' },
    { title: 'Offered / Offer', status: 'OFFERED', color: 'var(--accent-emerald)' }
  ];

  // Pipeline Metric Totals
  const countByStatus = (stat) => jobs.filter(j => j.status === stat).length;

  return (
    <div className="page-container">
      {/* Upper Statistics Header */}
      <header className="page-header">
        <div>
          <h1 className="gradient-title">Job Search Pipeline</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '14px' }}>
            Track application progress, score resume match values, and practice mock interviews.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Glassmorphic TopCV/VietnamWorks crawler search bar */}
          <form onSubmit={handleScrapeJobs} className="search-container">
            <input
              type="text"
              placeholder="Tìm kiếm việc làm (TopCV, VietnamWorks)..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              className="search-input"
            />
            <button type="submit" className="btn-search" title="Scrape and ingest market jobs">
              🔍
            </button>
          </form>

          {/* Clear All Button */}
          <button 
            onClick={handleClearAll} 
            className="btn-secondary" 
            style={{ padding: '10px 16px', gap: '6px', borderColor: 'rgba(244, 63, 94, 0.2)' }}
            title="Clear all cards from database"
          >
            🧹 Clear All
          </button>

          <button className="btn-primary" onClick={() => setShowAddModal(true)}>
            <span>➕</span> Add New Position
          </button>
        </div>
      </header>

      {/* KPI Cards Row */}
      <div className="kpi-row">
        <div className="glass-card kpi-card">
          <p className="kpi-label">Wishlist Items</p>
          <h2 className="kpi-value" style={{ color: 'var(--text-primary)' }}>{countByStatus('WISHLIST')}</h2>
        </div>
        <div className="glass-card kpi-card">
          <p className="kpi-label">Applied Jobs</p>
          <h2 className="kpi-value" style={{ color: '#3b82f6' }}>{countByStatus('APPLIED')}</h2>
        </div>
        <div className="glass-card kpi-card">
          <p className="kpi-label">Interviews Active</p>
          <h2 className="kpi-value" style={{ color: 'var(--accent-teal)' }}>{countByStatus('INTERVIEWING')}</h2>
        </div>
        <div className="glass-card kpi-card">
          <p className="kpi-label">Offers Received</p>
          <h2 className="kpi-value" style={{ color: 'var(--accent-emerald)' }}>{countByStatus('OFFERED')}</h2>
        </div>
      </div>

      {/* Kanban Board Grid */}
      {loading ? (
        <LoadingSpinner message="Loading Kanban CRM Board..." />
      ) : (
        <div className="board-grid-container">
          {columns.map(col => {
            const colJobs = jobs.filter(j => j.status === col.status);
            return (
              <div 
                key={col.status} 
                className="kanban-board-column"
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, col.status)}
              >
                <div className="column-header-row">
                  <div className="column-title-group">
                    <span className="column-color-dot" style={{ backgroundColor: col.color }}></span>
                    <h3 className="column-title">{col.title}</h3>
                  </div>
                  <span className="column-count-badge">{colJobs.length}</span>
                </div>

                <div className="column-cards-list">
                  {colJobs.length === 0 ? (
                    <div className="column-empty-placeholder">Drag jobs here</div>
                  ) : (
                    colJobs.map(job => (
                      <JobCard 
                        key={job.id} 
                        job={job}
                        prediction={predictions[job.id]}
                        onDelete={handleDeleteJob}
                        onOptimize={onOptimize}
                        onInterview={onInterview}
                        onToggleForecast={handleFetchPredictions}
                        onDragStart={handleDragStart}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Track Position Form Modal */}
      <AddJobModal 
        isVisible={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSubmit={handleCreateJob}
      />

      {/* Scraping Progress Ingestion logs Overlay */}
      <PipelineLogsOverlay 
        steps={pipelineSteps}
        currentStep={currentStep}
        isVisible={scraping}
      />
    </div>
  );
}
