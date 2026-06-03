import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import ATSScoreChart from '../components/resume/ATSScoreChart';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function ResumeOptimizer({ selectedJob, setSelectedJob, onFetchResume }) {
  const [activeResume, setActiveResume] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [jobs, setJobs] = useState([]);
  
  // Analysis states
  const [targetJobId, setTargetJobId] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Technical Category Mapping - Categorizes keywords into semantic groups
  const categorizeSkills = (skills) => {
    const categories = {
      "Languages": ["python", "javascript", "typescript", "golang", "go", "java", "scala", "rust", "sql", "c#", "cpp", "php", "ruby", "c++"],
      "Frameworks & Libraries": ["react", "reactjs", "nextjs", "angular", "vue", "fastapi", "django", "flask", "pytorch", "tensorflow", "pandas", "numpy", "polars", "langchain", "llamaindex", "scikit-learn", "xgboost", "boto3", "prefect"],
      "Databases & Storage": ["postgresql", "postgres", "mysql", "sqlite", "duckdb", "clickhouse", "mongodb", "redis", "lancedb", "qdrant", "pinecone", "chromadb", "snowflake", "bigquery", "databricks"],
      "DevOps, Cloud & Infrastructure": ["docker", "kubernetes", "k8s", "aws", "gcp", "terraform", "ansible", "airflow", "dbt", "mlflow", "git", "linux", "graphql", "rest", "api", "grpc"]
    };
    
    const grouped = {
      "Languages": [],
      "Frameworks & Libraries": [],
      "Databases & Storage": [],
      "DevOps, Cloud & Infrastructure": [],
      "Other Technical Skills": []
    };

    skills.forEach(skill => {
      const s_lower = skill.toLowerCase().trim();
      let categorized = false;
      for (const [cat, list] of Object.entries(categories)) {
        if (list.includes(s_lower)) {
          grouped[cat].push(skill);
          categorized = true;
          break;
        }
      }
      if (!categorized) {
        grouped["Other Technical Skills"].push(skill);
      }
    });

    return Object.entries(grouped).reduce((acc, [cat, list]) => {
      if (list.length > 0) acc[cat] = list;
      return acc;
    }, {});
  };

  const renderGroupedSkills = (skills, badgeClass) => {
    if (!skills || skills.length === 0) {
      return <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>None identified</span>;
    }
    const grouped = categorizeSkills(skills);
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '12px' }}>
        {Object.entries(grouped).map(([category, items]) => (
          <div key={category} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700', letterSpacing: '0.8px' }}>
              {category}
            </span>
            <div className="skills-tech-tags-list">
              {items.map(s => (
                <span key={s} className={`tech-tag-badge ${badgeClass}`}>{s}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // Fetch active resume & crm jobs on mount
  const loadData = async () => {
    try {
      // 1. Fetch active resume
      const dataResume = await api.getActiveResume();
      if (dataResume.active) {
        setActiveResume(dataResume);
      } else {
        setActiveResume(null);
      }

      // 2. Fetch CRM jobs
      const dataJobs = await api.getJobs();
      setJobs(dataJobs);
      
      // Auto-select job if cross-routed from Dashboard
      if (selectedJob) {
        setTargetJobId(selectedJob.id);
        triggerAnalysis(selectedJob.id);
      } else if (dataJobs.length > 0) {
        setTargetJobId(dataJobs[0].id);
      }
    } catch (e) {
      console.error("Failed to load initial optimizer data:", e);
    }
  };

  useEffect(() => {
    loadData();
    // Clean up selected job preset on unmount
    return () => setSelectedJob(null);
  }, []);

  // Trigger analysis helper
  const triggerAnalysis = async (jobId) => {
    if (!jobId) return;
    setAnalyzing(true);
    setErrorMsg('');
    setMatchResult(null);

    try {
      const data = await api.analyzeResume(jobId);
      setMatchResult(data);
    } catch (e) {
      setErrorMsg(e.message || "ATS Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  };

  // Upload file handler
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    setUploading(true);
    setErrorMsg('');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      await api.uploadResume(formData);
      onFetchResume(); // Refresh sidebar active badge
      await loadData(); // Reload local states
      // Trigger auto-analysis if job was already chosen
      if (targetJobId) {
        triggerAnalysis(targetJobId);
      }
    } catch (err) {
      setErrorMsg(err.message || "Resume upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const handleRunAnalysis = (e) => {
    e.preventDefault();
    if (!activeResume) {
      setErrorMsg("Please upload a PDF resume before running the matching analysis.");
      return;
    }
    triggerAnalysis(targetJobId);
  };

  return (
    <div className="page-container">
      {/* Page Title */}
      <header>
        <h1 className="gradient-title">Resume ATS Matcher</h1>
        <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '14px' }}>
          Optimize your resume keywords against specific Job Descriptions using Polars text processing and LanceDB similarity vector modeling.
        </p>
      </header>

      {/* Grid: Left Column (Upload) & Right Column (Selector & Scores) */}
      <div className="optimizer-grid">
        
        {/* Left Column - Resume Status & Upload Dropzone */}
        <div className="optimizer-column">
          <div className="glass-card master-resume-card">
            <h3 style={{ fontSize: '16.5px', marginBottom: '16px' }}>Master Resume Profile</h3>
            
            {activeResume ? (
              <div className="resume-active-badge-row">
                <div className="pdf-icon-wrapper">📄</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h4 className="pdf-active-name" title={activeResume.file_name}>
                    {activeResume.file_name}
                  </h4>
                  <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Uploaded: {new Date(activeResume.created_date).toLocaleString()}
                  </p>
                </div>
              </div>
            ) : (
              <div className="resume-empty-prompt">
                No master resume has been uploaded yet. Upload a PDF resume to initialize keyword matching.
              </div>
            )}

            <div className="resume-upload-dropzone">
              <span className="upload-icon-label">📤</span>
              <p className="upload-prompt-text">
                {uploading ? 'Processing PDF text...' : 'Select a new resume PDF to replace active master'}
              </p>
              <input 
                type="file" 
                accept=".pdf" 
                disabled={uploading} 
                onChange={handleFileUpload} 
                className="file-input-invisible" 
              />
              <button className="btn-secondary" style={{ marginTop: '16px' }} disabled={uploading}>
                {uploading ? 'Reading text...' : 'Upload PDF'}
              </button>
            </div>
          </div>
          
          {errorMsg && (
            <div className="error-banner-overlay">
              <span>⚠️</span>
              <p style={{ fontSize: '13px', lineHeight: '1.4' }}>{errorMsg}</p>
            </div>
          )}
        </div>

        {/* Right Column - Selection & Results Dashboard */}
        <div className="optimizer-column wide">
          <div className="glass-card optimizer-selection-card">
            <h3 style={{ fontSize: '16.5px', marginBottom: '16px' }}>Match Configuration</h3>
            
            <form onSubmit={handleRunAnalysis} className="modular-form">
              <div className="form-group">
                <label className="form-label">Select Target Position from CRM</label>
                {jobs.length === 0 ? (
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px' }}>
                    No jobs tracked yet. Go to the Kanban CRM Board to add your target job descriptions first!
                  </div>
                ) : (
                  <select 
                    value={targetJobId} 
                    onChange={(e) => setTargetJobId(e.target.value)} 
                    className="form-select"
                  >
                    {jobs.map(j => (
                      <option key={j.id} value={j.id}>
                        {j.company_name} - {j.job_title}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <button 
                type="submit" 
                className="btn-primary" 
                disabled={analyzing || jobs.length === 0 || !activeResume}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                {analyzing ? 'Analyzing Skill Vectors...' : 'Analyze Resume Compatibility'}
              </button>
            </form>
          </div>

          {/* Match Results Display */}
          {analyzing && (
            <div style={{ padding: '40px 0', textAlign: 'center' }}>
              <LoadingSpinner message="Polars counting word densities & LanceDB running cosine similarity searches..." />
            </div>
          )}

          {matchResult && !analyzing && (
            <div className="optimizer-results-container">
              {/* Radial Score card */}
              <div className="glass-card ats-score-summary-card">
                <ATSScoreChart score={matchResult.fit_score} />

                <div style={{ flex: 1, minWidth: 0 }}>
                  <h3 style={{ fontSize: '18px', color: 'var(--text-primary)' }}>ATS Compatibility Assessment</h3>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px', lineHeight: '1.45' }}>
                    Calculated semantic overlap of your resume versus technical expectations for the **{matchResult.job_title}** role at **{matchResult.company_name}**.
                  </p>
                </div>
              </div>

              {/* Skills Tags Matching Row */}
              <div className="skills-comparison-grid">
                <div className="skills-keywords-card">
                  <h4 className="skills-keywords-header matching">Matching Technologies</h4>
                  {renderGroupedSkills(matchResult.matching_skills, 'matched')}
                </div>

                <div className="skills-keywords-card">
                  <h4 className="skills-keywords-header missing">Missing Keywords (ATS Gaps)</h4>
                  {matchResult.missing_skills.length === 0 ? (
                    <span style={{ fontSize: '12px', color: 'var(--accent-emerald)', fontWeight: '600', display: 'block', marginTop: '12px' }}>
                      ✓ 100% matched!
                    </span>
                  ) : (
                    renderGroupedSkills(matchResult.missing_skills, 'missing')
                  )}
                </div>
              </div>

              {/* Recommendations Checklist */}
              <div className="glass-card" style={{ padding: '20px' }}>
                <h4 style={{ fontSize: '14.5px', marginBottom: '12px', color: 'var(--text-primary)' }}>Optimizations Checklist</h4>
                <ul className="recommendations-checklist">
                  {matchResult.recommendations.map((rec, i) => (
                    <li key={i} className="recommendation-item">
                      <span style={{ color: 'var(--accent-teal)', fontWeight: 'bold' }}>▸</span>
                      <p>{rec}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
