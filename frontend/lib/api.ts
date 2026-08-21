export interface JobStatus {
  id: string;
  status: string;
  stage: string | null;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  source_url: string;
  source_platform: string;
  title: string | null;
  duration: number | null;
  clip_length: number;
  created_at: string;
  updated_at: string;
}

export interface Clip {
  id: string;
  job_id: string;
  rank: number;
  start_time: number;
  end_time: number;
  score: number | null;
  hook: string | null;
  caption_title: string | null;
  reason: string | null;
  status: string;
  created_at: string;
  duration: number;
}

export class ApiError extends Error {
  code: string;
  stage: string | null;
  status: number;

  constructor(status: number, code: string, message: string, stage: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.stage = stage;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; stage?: string | null } } | null = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      res.status,
      body?.error?.code ?? "HTTP_ERROR",
      body?.error?.message ?? `Request failed (${res.status})`,
      body?.error?.stage ?? null,
    );
  }
  return (await res.json()) as T;
}

export async function createJob(
  url: string,
  clipLength: number,
): Promise<{ job_id: string; status: string }> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, clip_length: clipLength }),
  });
  return handle(res);
}

export async function getJob(id: string): Promise<JobStatus> {
  const res = await fetch(`/api/jobs/${id}`);
  return handle(res);
}

export async function getClips(id: string): Promise<Clip[]> {
  const res = await fetch(`/api/jobs/${id}/clips`);
  return handle(res);
}
