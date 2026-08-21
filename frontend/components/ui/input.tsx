import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-12 w-full rounded-lg border border-zinc-800 bg-zinc-900/70 px-4 text-sm text-zinc-100",
        "placeholder:text-zinc-500 transition-colors",
        "focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
