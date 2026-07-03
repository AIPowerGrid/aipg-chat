import React, { useState, useEffect, useRef } from "react";
import { ImageShape } from "@/app/app/services/streamingModels";

// Placeholder box sized to mirror the final InMessageImage bounds per shape, so
// when generation finishes the real image drops into the same footprint with no
// layout jump. Krea 2 Turbo defaults to portrait, so that's the default here.
const SHAPE_BOX: Record<ImageShape, string> = {
  square: "w-96 aspect-square",
  landscape: "w-[28rem] aspect-[3/2]",
  portrait: "w-72 aspect-[2/3]",
};

export default function GeneratingImageDisplay({
  isCompleted = false,
  shape = "portrait",
}: {
  isCompleted?: boolean;
  shape?: ImageShape;
}) {
  const [progress, setProgress] = useState(0);
  const progressRef = useRef(0);
  const animationRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    // Animation setup
    let lastUpdateTime = 0;
    const updateInterval = 500;
    const animationDuration = 30000;

    const animate = (timestamp: number) => {
      const elapsedTime = timestamp - startTimeRef.current;

      // Calculate progress using logarithmic curve
      const maxProgress = 99.9;
      const progress =
        maxProgress * (1 - Math.exp(-elapsedTime / animationDuration));

      // Update progress if enough time has passed
      if (timestamp - lastUpdateTime > updateInterval) {
        progressRef.current = progress;
        setProgress(Math.round(progress * 10) / 10);
        lastUpdateTime = timestamp;
      }

      // Continue animation if not completed
      if (!isCompleted && elapsedTime < animationDuration) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    // Start animation
    startTimeRef.current = performance.now();
    animationRef.current = requestAnimationFrame(animate);

    // Cleanup function
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isCompleted]);

  // Handle completion
  useEffect(() => {
    if (isCompleted) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      setProgress(100);
    }
  }, [isCompleted]);

  return (
    <div
      className={`border border-background-200 bg-background-100 flex flex-col items-center justify-center gap-4 overflow-hidden rounded-lg max-w-full transition-opacity duration-300 opacity-100 ${
        SHAPE_BOX[shape] ?? SHAPE_BOX.portrait
      }`}
    >
      {/* Progress ring with pulsing image glyph in the center */}
      <div className="relative flex items-center justify-center">
        <svg className="w-16 h-16 transform -rotate-90" viewBox="0 0 100 100">
          <circle
            className="text-background-300"
            strokeWidth="8"
            stroke="currentColor"
            fill="transparent"
            r="44"
            cx="50"
            cy="50"
          />
          <circle
            className="text-text-800 transition-all duration-300"
            strokeWidth="8"
            strokeDasharray={276.46}
            strokeDashoffset={276.46 * (1 - progress / 100)}
            strokeLinecap="round"
            stroke="currentColor"
            fill="transparent"
            r="44"
            cx="50"
            cy="50"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <svg
            className="w-6 h-6 text-text-500 animate-pulse-strong"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </div>
      </div>

      {/* Message + inline spinner */}
      <div className="flex flex-col items-center gap-1 px-6 text-center">
        <div className="flex items-center gap-2 text-sm font-medium text-text-800">
          <svg
            className="w-4 h-4 animate-spin text-text-500"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-90"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>
            Generating your image
            {progress > 0 ? ` · ${Math.round(progress)}%` : "…"}
          </span>
        </div>
        <span className="text-xs text-text-400">
          Running on the AI Power Grid — this usually takes a few seconds
        </span>
      </div>
    </div>
  );
}
