import { AuthScreen } from "@/components/AuthScreen";
import { Suspense } from "react";

export default function ForgotUserIdPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-wa-muted">Loading…</p>}>
      <AuthScreen mode="forgot-user-id" />
    </Suspense>
  );
}
