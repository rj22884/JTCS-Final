import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, ReactNode } from "react";

const tooltipSide = {
  top: "bottom-full left-1/2 mb-1 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-1 -translate-x-1/2",
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
};

export function Tooltip({
  label,
  side = "bottom",
  children,
}: {
  label: string;
  side?: keyof typeof tooltipSide;
  children: ReactNode;
}) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute z-30 hidden whitespace-nowrap rounded-md bg-wa-ink px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:hover)]:block",
          tooltipSide[side],
        )}
      >
        {label}
      </span>
    </span>
  );
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  side?: keyof typeof tooltipSide;
};

export function IconButton({
  label,
  side = "bottom",
  className,
  type = "button",
  children,
  ...props
}: IconButtonProps) {
  return (
    <Tooltip label={label} side={side}>
      <button
        type={type}
        aria-label={label}
        className={cn(
          "inline-flex h-10 w-10 items-center justify-center rounded-full text-wa-icon hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green disabled:cursor-not-allowed disabled:opacity-40",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    </Tooltip>
  );
}
