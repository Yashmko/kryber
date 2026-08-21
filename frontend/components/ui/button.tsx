import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost";
type Size = "default" | "sm" | "lg" | "icon";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-violet-600 text-white hover:bg-violet-500 active:bg-violet-700 disabled:bg-zinc-800 disabled:text-zinc-500 shadow-[0_0_0_1px_rgba(139,92,246,0.3)]",
  secondary:
    "bg-zinc-900 text-zinc-100 border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800",
  ghost: "bg-transparent text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100",
};

const sizeClasses: Record<Size, string> = {
  default: "h-10 px-4 text-sm",
  sm: "h-8 px-3 text-xs",
  lg: "h-12 px-6 text-base",
  icon: "h-10 w-10",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/50",
        "disabled:cursor-not-allowed",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
