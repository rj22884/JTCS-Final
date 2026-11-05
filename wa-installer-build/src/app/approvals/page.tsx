import { ApprovalsScreen } from "@/components/ApprovalsScreen";
import { Suspense } from "react";

export default function ApprovalsPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-wa-muted">Loading approvals…</p>}>
      <ApprovalsScreen />
    </Suspense>
  );
}
