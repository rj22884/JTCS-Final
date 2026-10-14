import { Inbox } from "@/components/Inbox";
import { Suspense } from "react";

export default function HomePage() {
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <Suspense fallback={<p className="p-6 text-sm text-wa-muted">Loading inbox…</p>}>
        <Inbox />
      </Suspense>
    </main>
  );
}
