"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const LENGTHS = [30, 45, 60] as const;

export function UrlForm() {
  const router = useRouter();
  const [url, setUrl] = React.useState("");
  const [length, setLength] = React.useState<number>(60);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function submitUrl(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!url.trim()) {
      setError("Please paste a video URL or upload a file.");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), clip_length: length }),
      });
      const body = await res.json();
      if (!res.ok) {
        throw new ApiError(
          res.status,
          body?.error?.code ?? "HTTP_ERROR",
          body?.error?.message ?? "Request failed",
          body?.error?.stage ?? null,
        );
      }
      router.push(`/jobs/${body.job_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setLoading(false);
    }
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("clip_length", String(length));
      const res = await fetch("/api/jobs/upload", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) {
        throw new ApiError(
          res.status,
          body?.error?.code ?? "HTTP_ERROR",
          body?.error?.message ?? "Request failed",
          body?.error?.stage ?? null,
        );
      }
      router.push(`/jobs/${body.job_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submitUrl} className="w-full max-w-xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste YouTube or video URL"
          aria-label="Video URL"
          spellCheck={false}
          autoComplete="off"
          className="flex-1"
        />
        <Button type="submit" size="lg" disabled={loading} className="sm:w-auto w-full">
          {loading ? "Creating…" : "Create Shorts"}
        </Button>
      </div>

      <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-start">
        <span className="text-xs text-zinc-500">Short length</span>
        <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900/60 p-0.5">
          {LENGTHS.map((n) => (
            <button
              key={n}
              type="button"
              disabled={loading}
              onClick={() => setLength(n)}
              className={cn(
                "rounded-md px-3.5 py-1.5 text-xs font-medium transition-colors",
                length === n
                  ? "bg-violet-600 text-white"
                  : "text-zinc-400 hover:text-zinc-100",
              )}
            >
              {n}s
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-600">· or</span>
        <button
          type="button"
          disabled={loading}
          onClick={() => fileRef.current?.click()}
          className="text-xs font-medium text-violet-400 hover:text-violet-300 disabled:opacity-50"
        >
          upload a video file
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="video/mp4,video/webm,video/quicktime,video/x-m4v,video/x-matroska,video/ogg,.mp4,.webm,.mov,.m4v,.mkv,.ogv"
          className="hidden"
          onChange={onFileChosen}
        />
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
