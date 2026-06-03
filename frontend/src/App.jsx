import React, { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import ResumeOptimizer from './pages/ResumeOptimizer';
import InterviewSimulator from './pages/InterviewSimulator';
import Analytics from './pages/Analytics';
import Sidebar from './components/layout/Sidebar';
import { api } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  
  // Shared context states to seamlessly pass target jobs between pages
  const [selectedJob, setSelectedJob] = useState(null);
  const [activeResume, setActiveResume] = useState(null);

  // Fetch active resume periodically to update the sidebar footer badge
  const fetchActiveResume = async () => {
    try {
      const data = await api.getActiveResume();
      if (data.active) {
        setActiveResume(data);
      } else {
        setActiveResume(null);
      }
    } catch (e) {
      console.warn("API offline or resume lookup failed:", e);
    }
  };

  useEffect(() => {
    fetchActiveResume();
  }, [activeTab]);

  // Handle cross-navigation from CRM cards
  const navigateToOptimize = (job) => {
    setSelectedJob(job);
    setActiveTab('optimizer');
  };

  const navigateToInterview = (job) => {
    setSelectedJob(job);
    setActiveTab('practice');
  };

  return (
    <div className="app-container">
      {/* Sidebar Layout Component */}
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        activeResume={activeResume} 
      />

      {/* Main Content viewport */}
      <main className="main-content">
        {activeTab === 'dashboard' && (
          <Dashboard 
            onOptimize={navigateToOptimize} 
            onInterview={navigateToInterview} 
          />
        )}
        
        {activeTab === 'optimizer' && (
          <ResumeOptimizer 
            selectedJob={selectedJob} 
            setSelectedJob={setSelectedJob}
            onFetchResume={fetchActiveResume}
          />
        )}
        
        {activeTab === 'practice' && (
          <InterviewSimulator 
            selectedJob={selectedJob} 
            setSelectedJob={setSelectedJob} 
          />
        )}

        {activeTab === 'analytics' && (
          <Analytics />
        )}
      </main>
    </div>
  );
}
