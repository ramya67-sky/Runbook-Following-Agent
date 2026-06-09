import React, { useEffect, useState } from 'react';
import IntroTransition from './IntroTransition';

/**
 * IntroLoader – handles the timing/stage logic.
 * The visual rendering is delegated to IntroTransition.
 */
export default function IntroLoader({ onComplete }) {
  const [stage, setStage] = useState('welcome'); // welcome -> scan -> complete -> exit

  useEffect(() => {
    // Stage 1: Welcome message
    const welcomeTimer = setTimeout(() => {
      setStage('scan');
    }, 1200);

    // Stage 2: Safety scanning simulated visual effect
    const scanTimer = setTimeout(() => {
      setStage('complete');
    }, 2800);

    // Stage 3: Complete check
    const completeTimer = setTimeout(() => {
      setStage('exit');
    }, 3800);

    // Stage 4: Trigger exit callback to reveal the app
    const exitTimer = setTimeout(() => {
      if (onComplete) onComplete();
    }, 4500);

    return () => {
      clearTimeout(welcomeTimer);
      clearTimeout(scanTimer);
      clearTimeout(completeTimer);
      clearTimeout(exitTimer);
    };
  }, []); // Run only once on mount to avoid re-triggering on App re-renders

  return <IntroTransition stage={stage} />;
}
