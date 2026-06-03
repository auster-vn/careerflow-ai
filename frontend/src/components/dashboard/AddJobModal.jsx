import React, { useState } from 'react';

export default function AddJobModal({ isVisible, onClose, onSubmit }) {
  const [companyName, setCompanyName] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [jobUrl, setJobUrl] = useState('');
  const [salaryRange, setSalaryRange] = useState('');
  const [notes, setNotes] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [status, setStatus] = useState('WISHLIST');

  if (!isVisible) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!companyName.trim() || !jobTitle.trim() || !jobDescription.trim()) return;
    
    onSubmit({
      company_name: companyName.trim(),
      job_title: jobTitle.trim(),
      job_url: jobUrl.trim(),
      salary_range: salaryRange.trim(),
      notes: notes.trim(),
      job_description: jobDescription.trim(),
      status
    });

    // Reset fields
    setCompanyName('');
    setJobTitle('');
    setJobUrl('');
    setSalaryRange('');
    setNotes('');
    setJobDescription('');
    setStatus('WISHLIST');
  };

  return (
    <div className="modal-overlay">
      <div className="glass-card tracking-job-modal">
        <div className="modal-header">
          <h2 className="modal-title">Track New Position</h2>
          <button onClick={onClose} className="modal-close-btn">&times;</button>
        </div>
        
        <form onSubmit={handleSubmit} className="modular-form">
          <div className="form-row-grid">
            <div className="form-group">
              <label className="form-label">Company Name *</label>
              <input 
                type="text" 
                required 
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)} 
                className="form-input"
                placeholder="e.g. Google, Stripe"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Job Title *</label>
              <input 
                type="text" 
                required 
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)} 
                className="form-input"
                placeholder="e.g. Lead Data Engineer"
              />
            </div>
          </div>

          <div className="form-row-grid">
            <div className="form-group">
              <label className="form-label">Job URL</label>
              <input 
                type="text" 
                value={jobUrl}
                onChange={(e) => setJobUrl(e.target.value)} 
                className="form-input"
                placeholder="e.g. https://careers.company.com/..."
              />
            </div>
            <div className="form-group">
              <label className="form-label">Salary Range</label>
              <input 
                type="text" 
                value={salaryRange}
                onChange={(e) => setSalaryRange(e.target.value)} 
                className="form-input"
                placeholder="e.g. $130,000 - $160,000"
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">CRM Board Stage</label>
            <select 
              value={status} 
              onChange={(e) => setStatus(e.target.value)} 
              className="form-select"
            >
              <option value="WISHLIST">Wishlist</option>
              <option value="APPLIED">Applied</option>
              <option value="INTERVIEWING">Interviewing</option>
              <option value="OFFERED">Offered / Offer</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Job Description (ATS Check & Mock prep) *</label>
            <textarea 
              required
              rows="5"
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              className="form-textarea"
              placeholder="Paste the full job description details here. Polars and LanceDB will parse this for skill evaluations."
            ></textarea>
          </div>

          <div className="form-group">
            <label className="form-label">Personal Application Notes</label>
            <input 
              type="text" 
              value={notes}
              onChange={(e) => setNotes(e.target.value)} 
              className="form-input"
              placeholder="e.g. Referral from John, recruiter call scheduled for Friday"
            />
          </div>

          <div className="modal-footer-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Save Position
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
