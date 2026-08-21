"use client";

import * as React from "react";
import { getClips, getJob, type Clip, type JobStatus } from "@/lib/api";
import { JobProgress } from "@/components/JobProgress";
import { ShortCard } from "@/components/ShortCard";
import { Button } from "@/components/ui/button";

const POLL_MS = 1500;

export default function JobPage({ params }: { params: { id: string } }) {
  const [job, setJob] = React.useState<JobStatus | null>(null);
  const [clips, setClips] = React.useState<Clip[]>([]);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const j = await getJob(params.id);
        if (cancelled) return;
        setJob(j);
        if (j.status === "completed") {
          const c = await getClips(params.id);
          if (!cancelled) setClips(c);
        } else if (j.status !== "failed") {
          timer = setTimeout(poll, POLL_MS);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Failed to load job.");
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [params.id]);

  if (loadError) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <p className="text-sm text-red-400">{loadError}</p>
        <a href="/" className="mt-4 text-sm text-zinc-300 underline underline-offset-4">
          Back home
        </a>
      </main>
    );
  }

  if (!job) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <span className="font-mono text-xs uppercase tracking-[0.4em] text-violet-400">Kryber</span>
        <p className="mt-4 text-sm text-zinc-500">Loading…</p>
      </main>
    );
  }

  const done = job.status === "completed";
  const headline = done
    ? "Your Shorts are ready."
    : job.status === "failed"
      ? "Processing failed."
      : "Preparing your video…";

  return (
    <main className="flex min-h-screen flex-col items-center px-6 py-16">
      <div className="flex w-full max-w-3xl flex-col items-center text-center animate-fade-in">
        <a href="/" className="font-mono text-xs uppercase tracking-[0.4em] text-violet-400">
          Kryber
        </a>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">{headline}</h1>

        {!done && job.status !== "failed" && (
          <div className="mt-10">
            <JobProgress job={job} />
          </div>
        )}

        {job.status === "failed" && (
          <div className="mt-10">
            <JobProgress job={job} />
          </div>
        )}

        {done && (
          <div className="mt-10 w-full">
            {clips.length > 0 ? (
              <>
                <p className="mb-4 text-sm text-zinc-500">
                  {clips.length} Short{clips.length > 1 ? "s" : ""} · target{" "}
                  {job.clip_length ?? 60}s
                </p>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {clips.map((clip) => (
                    <ShortCard key={clip.id} clip={clip} />
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-zinc-500">
                Shorts are being finalized — check back in a moment.
              </p>
            )}
          </div>
        )}

        <div className="mt-12">
          <a href="/">
            <Button variant="ghost" size="sm">
              ← New video
            </Button>
          </a>
        </div>
      </div>
    </main>
  );
}
