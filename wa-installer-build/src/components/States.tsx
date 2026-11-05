import { CircleAlert, MessageCircle, RefreshCw } from "lucide-react";

export function ErrorState({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center gap-3 px-6 text-center">
      <CircleAlert aria-hidden="true" className="h-8 w-8 text-red-700" />
      <h2 className="font-display text-base font-bold tracking-tight">{title}</h2>
      <p className="max-w-sm text-sm text-wa-muted">{detail}</p>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex h-9 items-center gap-2 rounded-full bg-wa-green px-4 text-sm font-medium text-white hover:bg-wa-green-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-wa-green focus-visible:ring-offset-2"
      >
        <RefreshCw aria-hidden="true" className="h-4 w-4" />
        Try again
      </button>
    </div>
  );
}

export function InboxSkeleton() {
  return (
    <div className="flex min-h-0 flex-1" aria-busy="true" aria-live="polite">
      <div className="flex w-full min-h-0 flex-col border-wa-line md:w-[380px] md:border-r">
        <div className="border-b border-wa-line px-4 py-4">
          <p className="text-sm font-medium">Loading conversations</p>
        </div>
        <div className="space-y-3 px-4 py-3">
          {Array.from({ length: 8 }, (_, index) => (
            <div key={index} className="flex items-center gap-3">
              <div className="h-12 w-12 animate-pulse rounded-full bg-wa-app" />
              <div className="flex-1 space-y-2">
                <div className="h-3 w-1/2 animate-pulse rounded bg-wa-app" />
                <div className="h-3 w-4/5 animate-pulse rounded bg-wa-app" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="hidden min-w-0 flex-1 bg-wa-app md:block" />
    </div>
  );
}

export function EmptyThread({ live = false }: { live?: boolean }) {
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center px-6 text-center">
      <span className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-white text-wa-green shadow-sm">
        <MessageCircle aria-hidden="true" className="h-8 w-8" />
      </span>
      <h2 className="font-display text-lg font-bold tracking-tight">Select a conversation</h2>
      <p className="mt-2 max-w-sm text-sm leading-5 text-wa-muted">
        {live
          ? "New WhatsApp messages to this number show up in the list."
          : "This inbox is in demo mode. The list is sample data, and the workspace is not connected to WhatsApp."}
      </p>
    </div>
  );
}
