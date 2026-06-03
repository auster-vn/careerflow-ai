import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import SpeechVisualizer from '../components/interview/SpeechVisualizer';
import TranscriptBubble from '../components/interview/TranscriptBubble';

export default function InterviewSimulator({ selectedJob, setSelectedJob }) {
  const [jobs, setJobs] = useState([]);
  const [targetJobId, setTargetJobId] = useState('');
  
  // Session states
  const [activeSession, setActiveSession] = useState(null); // { id, company, role, current_question }
  const [loadingSession, setLoadingSession] = useState(false);
  const [history, setHistory] = useState([]); // Array of transcript logs
  
  // Active round Q&A states
  const [userAnswer, setUserAnswer] = useState('');
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Voice & Speech Synthesis/Recognition States
  const [isMuted, setIsMuted] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef(null);

  const chatEndRef = useRef(null);

  // Text-To-Speech (TTS) Reader
  const speakQuestion = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    if (isMuted) return;

    // Clean brackets or tags for cleaner natural speech
    const cleanText = text.replace(/\[.*?\]\s*/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    
    const voices = window.speechSynthesis.getVoices();
    const engVoice = voices.find(v => v.lang.startsWith('en')) || voices[0];
    if (engVoice) {
      utterance.voice = engVoice;
    }
    
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    
    window.speechSynthesis.speak(utterance);
  };

  // Speech-To-Text (STT) Dictation
  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please use Google Chrome or Safari.");
      return;
    }

    const recog = new SpeechRecognition();
    recog.continuous = true;
    recog.interimResults = true;
    recog.lang = 'en-US';

    recog.onstart = () => {
      setIsListening(true);
    };

    recog.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setUserAnswer(prev => {
        const prefix = prev.trim() ? prev.trim() + ' ' : '';
        return prefix + transcript;
      });
    };

    recog.onerror = (e) => {
      console.error("Speech recognition error:", e);
      setIsListening(false);
    };

    recog.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recog;
    recog.start();
  };

  // Safe quit session and cancel audio
  const handleQuitSession = () => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsSpeaking(false);
    setIsListening(false);
    setActiveSession(null);
  };

  // Load CRM jobs on mount
  const loadJobs = async () => {
    try {
      const data = await api.getJobs();
      setJobs(data);
      
      // Auto-select job if cross-routed from Dashboard
      if (selectedJob) {
        setTargetJobId(selectedJob.id);
      } else if (data.length > 0) {
        setTargetJobId(data[0].id);
      }
    } catch (e) {
      console.error("Failed to load crm jobs:", e);
    }
  };

  useEffect(() => {
    loadJobs();
    return () => {
      setSelectedJob(null);
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Scroll to bottom on transcript updates
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, submittingAnswer]);

  // Start interview session handler
  const handleStartInterview = async (e) => {
    e.preventDefault();
    if (!targetJobId) return;

    setLoadingSession(true);
    setErrorMsg('');
    setInterviewComplete(false);

    try {
      const data = await api.startInterview(targetJobId);
      setActiveSession({
        id: data.session_id,
        company: data.company_name,
        role: data.job_title,
        current_question: data.initial_question
      });
      
      // Initialize local history
      setHistory([
        {
          speaker: 'AI',
          message: data.initial_question,
          created_date: new Date().toISOString()
        }
      ]);

      // Auto-read initial question
      setTimeout(() => speakQuestion(data.initial_question), 500);
    } catch (err) {
      setErrorMsg(err.message || "Failed to start session due to server connection issues.");
    } finally {
      setLoadingSession(false);
    }
  };

  // Submit response handler
  const handleSendAnswer = async (e) => {
    e.preventDefault();
    const answerText = userAnswer.trim();
    if (!answerText || submittingAnswer) return;

    setUserAnswer('');
    setSubmittingAnswer(true);

    // Stop listening if active
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    }

    // 1. Optimistically add user answer to history
    const tempUserLog = {
      speaker: 'USER',
      message: answerText,
      created_date: new Date().toISOString()
    };
    setHistory(prev => [...prev, tempUserLog]);

    try {
      // 2. POST user response to backend
      const data = await api.answerInterview(activeSession.id, answerText);
      
      // 3. Update active user log with score/feedback in local history
      setHistory(prev => 
        prev.map((log, index) => 
          (index === prev.length - 1) 
            ? { ...log, score: data.evaluation.score, feedback: data.evaluation.feedback, model_answer: data.evaluation.model_answer }
            : log
        )
      );

      if (data.is_complete) {
        setInterviewComplete(true);
        speakQuestion("The mock interview has concluded. Thank you for your responses. Please review the detailed report card.");
      } else {
        // Add next AI question to transcript history
        setHistory(prev => [
          ...prev,
          {
            speaker: 'AI',
            message: data.next_question,
            created_date: new Date().toISOString()
          }
        ]);
        // Update active session question reference
        setActiveSession(prev => ({ ...prev, current_question: data.next_question }));
        speakQuestion(data.next_question);
      }
    } catch {
      setErrorMsg("Failed to evaluate answer.");
    } finally {
      setSubmittingAnswer(false);
    }
  };

  const calculateAverageScore = () => {
    const scores = history.filter(h => h.speaker === 'USER' && h.score !== undefined).map(h => h.score);
    if (scores.length === 0) return 0;
    return (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      {!activeSession && (
        <header>
          <h1 className="gradient-title">AI Interview Practice</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '4px', fontSize: '14px' }}>
            Practice real technical questions modeled on specific job requirements. Get rated on-the-fly with detailed model answers.
          </p>
        </header>
      )}

      {/* 1. Selection Screen (No active session) */}
      {!activeSession && (
        <div className="glass-card" style={{ padding: '24px', maxWidth: '550px' }}>
          <h3 style={{ fontSize: '18px', marginBottom: '12px' }}>Start Mock Session</h3>
          {jobs.length === 0 ? (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Add job posts in your CRM board first to generate custom mock interviews.
            </p>
          ) : (
            <form onSubmit={handleStartInterview} className="modular-form" style={{ marginTop: '20px' }}>
              <div className="form-group">
                <label className="form-label">Target Job Profile</label>
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
              </div>

              <button className="btn-primary" type="submit" disabled={loadingSession}>
                {loadingSession ? 'Generating Session Context...' : '🗣️ Start AI Mock Interview'}
              </button>
            </form>
          )}

          {errorMsg && (
            <div className="error-banner-overlay" style={{ marginTop: '20px' }}>
              <span>⚠️</span>
              <p style={{ fontSize: '13px' }}>{errorMsg}</p>
            </div>
          )}
        </div>
      )}

      {/* 2. Active Dual-Panel Mock Interview Room */}
      {activeSession && (
        <div className="interview-workspace-container">
          
          {/* Left Panel: The Virtual Interview Room */}
          <div className="glass-card interview-interviewer-panel">
            <div className="interviewer-header-info">
              <span className="interviewer-avatar-icon">🤖</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h4 style={{ fontSize: '14.5px', color: 'var(--text-primary)', fontWeight: '600' }}>
                  {activeSession.company} Interviewer
                </h4>
                <p style={{ fontSize: '11px', color: 'var(--accent-teal)', fontWeight: '600', marginTop: '2px' }}>
                  Role: Lead {activeSession.role} Recruiter
                </p>
              </div>
              
              {/* Speaker Volume/Mute button */}
              <button 
                onClick={() => {
                  const nextMute = !isMuted;
                  setIsMuted(nextMute);
                  if (nextMute && window.speechSynthesis) {
                    window.speechSynthesis.cancel();
                    setIsSpeaking(false);
                  } else if (!nextMute && activeSession.current_question && !interviewComplete) {
                    speakQuestion(activeSession.current_question);
                  }
                }}
                className="volume-mute-btn"
                title={isMuted ? "Unmute Voice" : "Mute Voice"}
              >
                {isMuted ? "🔇" : "🔊"}
              </button>
            </div>

            {/* Pulsing visual avatar & audio waves */}
            <SpeechVisualizer isSpeaking={isSpeaking} isListening={isListening} />

            {/* In focus Active Question display */}
            <div className="active-focus-question-box">
              <div className="active-focus-question-header">
                <span className="active-focus-question-label">Active Question</span>
                {activeSession.current_question && !interviewComplete && (
                  <button 
                    onClick={() => speakQuestion(activeSession.current_question)} 
                    className="active-focus-question-voice-btn"
                    title="Read question out loud"
                  >
                    🔁 Play Voice
                  </button>
                )}
              </div>
              {interviewComplete ? (
                <p className="active-focus-question-text">
                  Interview finished! Review your performance metrics in the transcript pane on the right.
                </p>
              ) : (
                <p className="active-focus-question-text">
                  "{activeSession.current_question}"
                </p>
              )}
            </div>

            <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={handleQuitSession}>
              Quit Session
            </button>
          </div>

          {/* Right Panel: Chat Transcript & Feedbacks */}
          <div className="glass-card interview-transcript-panel">
            <div className="transcript-header">
              <h3 style={{ fontSize: '15px', color: 'var(--text-primary)' }}>Live Interview Transcript</h3>
              {interviewComplete && <span className="column-count-badge" style={{ color: 'var(--accent-emerald)', borderColor: 'rgba(16,185,129,0.3)' }}>Finished</span>}
            </div>

            {/* Scrollable transcript pane */}
            <div className="transcript-scroll-area">
              {history.map((log, idx) => (
                <TranscriptBubble key={idx} log={log} />
              ))}

              {submittingAnswer && (
                <div className="typing-grading-indicator">
                  <div className="pulse-indicator"></div>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>AI Hiring Manager is grading your answer...</span>
                </div>
              )}

              {/* Interview summary report card when finished */}
              {interviewComplete && (
                <div className="glass-card session-summary-scorecard">
                  <h3 style={{ fontSize: '19px', color: 'var(--accent-teal)' }}>Interview Report Card</h3>
                  <div className="session-summary-grid">
                    <div className="session-summary-kpi">
                      <span className="session-summary-kpi-label">Average Score</span>
                      <h2 style={{ fontSize: '34px', color: 'var(--accent-emerald)', marginTop: '4px', fontWeight: 'bold' }}>
                        {calculateAverageScore()}/10
                      </h2>
                    </div>
                    <div style={{ flex: 1 }}>
                      <h4 style={{ fontSize: '14px', marginBottom: '6px', color: 'var(--text-primary)' }}>Hiring Decision</h4>
                      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.45' }}>
                        {calculateAverageScore() >= 8.0 
                          ? "Strong recommendation for onsite round! Excellent conceptual depth and use of technical skills."
                          : calculateAverageScore() >= 6.0
                          ? "Pass with recommendations. Review the missing technical keywords and ideal model guides."
                          : "Needs improvement. Recommend focusing on expanding answer length and using exact technical terminology."
                        }
                      </p>
                    </div>
                  </div>
                  <button className="btn-primary" style={{ marginTop: '16px', width: '100%', justifyContent: 'center' }} onClick={handleQuitSession}>
                    Return to Board
                  </button>
                </div>
              )}

              <div ref={chatEndRef}></div>
            </div>

            {/* Answer text input bottom row */}
            {!interviewComplete && (
              <form onSubmit={handleSendAnswer} className="active-interview-reply-form">
                <div className="dictation-input-container">
                  <textarea 
                    rows="3"
                    value={userAnswer}
                    disabled={submittingAnswer}
                    onChange={(e) => setUserAnswer(e.target.value)}
                    className="dictation-input-textarea"
                    placeholder="Type or speak your answer here. Describe underlying architectures, tradeoffs, or project experiences..."
                  ></textarea>
                  
                  {/* Microphone speech recognition button */}
                  <button
                    type="button"
                    onClick={toggleListening}
                    className={`dictation-mic-trigger-btn ${isListening ? 'active' : ''}`}
                    title={isListening ? "Stop listening" : "Dictate response"}
                    disabled={submittingAnswer}
                  >
                    {isListening ? "🛑" : "🎤"}
                  </button>
                </div>
                
                <div className="dictation-status-bar">
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {isListening ? "🔊 Listening... Speak clearly in English." : "💡 Click the mic icon to dictate your answer."}
                  </span>
                  <button 
                    type="submit" 
                    className="btn-primary"
                    disabled={submittingAnswer || !userAnswer.trim()}
                  >
                    {submittingAnswer ? 'Grading...' : 'Submit Answer'}
                  </button>
                </div>
              </form>
            )}

          </div>

        </div>
      )}
    </div>
  );
}
