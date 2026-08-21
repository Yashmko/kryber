"use client";

import type { Clip } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function ShortCard({ clip }: { clip: Clip }) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
      {/* 9:16 preview frame */}
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[240px] bg-zinc-900">
        <video
          src={`/api/clips/${clip.id}/download`}
          controls
          playsInline
          preload="metadata"
          className="h-full w-full object-contain"
        />
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-100">
            Short {String(clip.rank).padStart(2, "0")}
          </p>
          <p className="text-xs text-zinc-500">{formatDuration(clip.duration)}</p>
        </div>
        <a href={`/api/clips/${clip.id}/download`} download>
          <Button variant="secondary" size="sm">
            Download
          </Button>
        </a>
      </div>
    </div>
  );
}
