"use client";

import { useEffect } from "react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="text-base font-semibold">Something went wrong</h1>
      <p className="max-w-sm text-sm text-wa-muted">The inbox could not be shown. You can try loading it again.</p>
      <button
        type="button"
        onClick={reset}
        className="h-9 rounded-full bg-wa-green px-4 text-sm font-medium text-white hover:bg-wa-green-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green focus-visible:ring-offset-2"
      >
        Try again
      </button>
    </div>
  );
}
