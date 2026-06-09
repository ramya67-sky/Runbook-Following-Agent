import React from 'react';
import './IntroTransition.css';

/**
 * Visual transition for the intro sequence.
 * Receives the current `stage` ('welcome' | 'scan' | 'complete')
 * and renders the overlay with appropriate CSS classes.
 */
export default function IntroTransition({ stage }) {
  if (stage === 'exit') return null;

  return (
    <div className={`intro-loader-overlay ${stage === 'complete' ? 'fade-out' : ''}`}>
      <div className="intro-glow-bg"></div>

      <div className="intro-content">
        {/* Cyberpunk Scanner Box */}
        <div className="intro-scanner-box">
          <div className="intro-scanner-laser"></div>

          <div className="logo-container">
            <span className="logo-letter">V</span>
            <span className="logo-letter">E</span>
            <span className="logo-letter">G</span>
            <span className="logo-letter">A</span>
          </div>

          <div className="intro-status-text">
            {stage === 'welcome' && (
              <span className="typing-text">SYSTEM INITIATION...</span>
            )}
            {stage === 'scan' && (
              <span className="scanning-text">RUNNING SECURITY SCAN...</span>
            )}
            {stage === 'complete' && (
              <span className="complete-text">SECURE ACCESS GRANTED</span>
            )}
          </div>
        </div>

        {/* Diagnostic loading statistics */}
        <div className="intro-stats-panel">
          <div className="stats-row">
            <span>GUARDIAN ENGINE:</span>
            <span className={stage !== 'welcome' ? 'stats-active' : ''}>
              {stage === 'welcome' ? 'OFFLINE' : 'ONLINE'}
            </span>
          </div>
          <div className="stats-row">
            <span>OLLAMA MODEL:</span>
            <span className={stage === 'complete' ? 'stats-active' : ''}>
              {stage === 'welcome' ? 'CONNECTING...' : 'CONNECTED'}
            </span>
          </div>
          <div className="stats-row">
            <span>STATUS:</span>
            <span className={stage === 'complete' ? 'stats-active' : 'stats-warning'}>
              {stage === 'welcome' && 'PENDING'}
              {stage === 'scan' && 'ANALYZING POLICY...'}
              {stage === 'complete' && 'SECURED'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
