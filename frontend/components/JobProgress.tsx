"use client";

import * as React from "react";
import type { JobStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "ingesting", label: "Downloading" },
  { key: "transcribing", label: "Transcribing" },
  { key: "analyzing", label: "Finding best moments" },
  { key: "rendering", label: "Rendering Shorts" },
] as const;

const ORDER = ["queued", "ingesting", "transcribing", "analyzing", "rendering", "completed"];

// How long a job may sit in "queued" before we explain the likely cause.
// Normally a worker claims a job within a second or two.
const QUEUED_HINT_AFTER_MS = 30_000;

function stepState(status: string, stepKey: string): "done" | "current" | "pending" {
  const currentIdx = ORDER.indexOf(status);
  const stepIdx = ORDER.indexOf(stepKey);
  if (currentIdx > stepIdx) return "done";
  if (currentIdx === stepIdx) return "current";
  return "pending";
}

export function JobProgress({ job }: { job: JobStatus }) {
  const isQueued = job.status === "queued";
  const [stuckInQueue, setStuckInQueue] = React.useState(false);

  // A job that never leaves "queued" almost always means no worker is
  // consuming the queue. Say so instead of spinning forever.
  React.useEffect(() => {
    if (!isQueued) {
      setStuckInQueue(false);
      return;
    }
    const timer = setTimeout(() => setStuckInQueue(true), QUEUED_HINT_AFTER_MS);
    return () => clearTimeout(timer);
  }, [isQueued]);

  if (job.status === "failed") {
    return (
      <div className="w-full max-w-xl rounded-xl border border-red-900/50 bg-red-950/30 p-5 text-left">
        <p className="text-sm font-medium text-red-300">Processing failed</p>
        <p className="mt-1 text-sm text-red-200/80">
          Stage <span className="font-mono text-red-200">{job.stage ?? "unknown"}</span> failed
          {job.error_code ? ` (${job.error_code})` : ""}.
        </p>
        {job.error_message && (
          <p className="mt-2 text-xs leading-relaxed text-red-200/60">{job.error_message}</p>
        )}
        <a
          href="/"
          className="mt-4 inline-block text-sm text-zinc-300 underline underline-offset-4 hover:text-white"
        >
          Try another video
        </a>
      </div>
    );
  }

  return (
    <div className="w-full max-w-xl">
      <ul className="space-y-3 text-left">
        {STEPS.map((step) => {
          const state = stepState(job.status, step.key);
          return (
            <li key={step.key} className="flex items-center gap-3">
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                  state === "done" && "bg-violet-600 text-white",
                  state === "current" && "bg-zinc-800 text-violet-300 ring-1 ring-violet-500/50 animate-pulse-soft",
                  state === "pending" && "bg-zinc-900 text-zinc-600 ring-1 ring-zinc-800",
                )}
              >
                {state === "done" ? "✓" : ""}
              </span>
              <span
                className={cn(
                  "text-sm",
                  state === "done" && "text-zinc-100",
                  state === "current" && "text-zinc-200",
                  state === "pending" && "text-zinc-600",
                )}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ul>

      {isQueued && stuckInQueue && (
        <div
          role="status"
          className="mt-6 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-left"
        >
          <p className="text-sm font-medium text-amber-200">Still waiting in the queue</p>
          <p className="mt-1 text-xs leading-relaxed text-amber-100/70">
            This job was accepted but no worker has picked it up yet. The usual cause is
            that the backend is running without a worker, so jobs stay queued.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-amber-100/70">
            For a local or Codespaces setup, start the API with{" "}
            <code className="font-mono text-amber-200">KRYBER_QUEUE_BACKEND=memory</code> and{" "}
            <code className="font-mono text-amber-200">KRYBER_INPROC_WORKER=1</code>. The
            backend&apos;s <code className="font-mono text-amber-200">/healthz</code> endpoint
            reports the current queue and worker state.
          </p>
        </div>
      )}
    </div>
  );
}
