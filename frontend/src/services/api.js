const API_BASE = 'http://localhost:8000/api';

class ApiService {
  async getJobs() {
    const res = await fetch(`${API_BASE}/crm`);
    if (!res.ok) throw new Error('Failed to fetch CRM jobs');
    return res.json();
  }

  async createJob(jobData) {
    const res = await fetch(`${API_BASE}/crm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jobData)
    });
    if (!res.ok) throw new Error('Failed to track new position');
    return res.json();
  }

  async updateJobStatus(id, status) {
    const res = await fetch(`${API_BASE}/crm/${id}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (!res.ok) throw new Error('Failed to update job status');
    return res.json();
  }

  async deleteJob(id) {
    const res = await fetch(`${API_BASE}/crm/${id}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete job application');
    return res.json();
  }

  async clearAll() {
    const res = await fetch(`${API_BASE}/crm/clear-all`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to clear applications');
    return res.json();
  }

  async getActiveResume() {
    const res = await fetch(`${API_BASE}/resume/active`);
    if (!res.ok) throw new Error('Failed to fetch active resume');
    return res.json();
  }

  async uploadResume(formData) {
    const res = await fetch(`${API_BASE}/resume/upload`, {
      method: 'POST',
      body: formData // Form data handles boundaries automatically
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Resume upload failed');
    }
    return res.json();
  }

  async analyzeResume(jobId) {
    const res = await fetch(`${API_BASE}/resume/analyze/${jobId}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'ATS analysis failed');
    }
    return res.json();
  }

  async startInterview(jobId) {
    const res = await fetch(`${API_BASE}/interview/start/${jobId}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Unable to boot mock interview session');
    }
    return res.json();
  }

  async answerInterview(sessionId, answer) {
    const res = await fetch(`${API_BASE}/interview/answer/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer })
    });
    if (!res.ok) throw new Error('Failed to evaluate answer');
    return res.json();
  }

  async scrapeJobs(keyword) {
    const res = await fetch(`${API_BASE}/analytics/scrape?keyword=${encodeURIComponent(keyword)}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to scrape jobs');
    }
    return res.json();
  }

  async predictSalary(appId) {
    const res = await fetch(`${API_BASE}/analytics/predict-salary/${appId}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to forecast salary');
    return res.json();
  }

  async predictSuccess(appId) {
    const res = await fetch(`${API_BASE}/analytics/predict-success/${appId}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to forecast success probability');
    return res.json();
  }

  async getTelemetry() {
    const res = await fetch(`${API_BASE}/analytics/telemetry`);
    if (!res.ok) throw new Error('Failed to load telemetry');
    return res.json();
  }

  async triggerEtl() {
    const res = await fetch(`${API_BASE}/analytics/trigger-etl`, { method: 'POST' });
    if (!res.ok) throw new Error('Prefect ETL flow trigger failed');
    return res.json();
  }

  async triggerMlRetrain() {
    const res = await fetch(`${API_BASE}/analytics/trigger-ml-retrain`, { method: 'POST' });
    if (!res.ok) throw new Error('Prefect ML retrain flow trigger failed');
    return res.json();
  }
}

export const api = new ApiService();
