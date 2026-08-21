import { UrlForm } from "@/components/UrlForm";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="flex w-full max-w-2xl flex-col items-center text-center animate-fade-in">
        <span className="font-mono text-xs uppercase tracking-[0.4em] text-violet-400">
          Kryber
        </span>
        <h1 className="mt-4 text-5xl font-bold tracking-tight text-white sm:text-6xl">
          Turn long videos into Shorts.
        </h1>
        <p className="mt-4 text-lg text-zinc-400">
          Paste a video. Kryber finds the moments worth watching.
        </p>

        <div className="mt-10 w-full">
          <UrlForm />
        </div>

        <p className="mt-8 max-w-md text-xs leading-relaxed text-zinc-600">
          Kryber analyzes your video, finds the strongest moments, writes the hook, and renders
          vertical 9:16 Shorts with synced captions — automatically.
        </p>
      </div>
    </main>
  );
}
