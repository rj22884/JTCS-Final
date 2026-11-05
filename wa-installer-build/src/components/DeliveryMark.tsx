import { Check, CheckCheck, CircleAlert } from "lucide-react";
import type { DeliveryState } from "@/lib/types";

export function DeliveryMark({ status }: { status: DeliveryState }) {
  if (status === "not_sent") {
    return <span className="text-[11px] font-medium text-[#9a6b12]">Not sent</span>;
  }

  const label =
    status === "read" ? "Read" : status === "delivered" ? "Delivered" : status === "sent" ? "Sent" : "Failed";

  return (
    <span className="inline-flex items-center">
      {status === "failed" ? (
        <CircleAlert aria-hidden="true" className="h-3.5 w-3.5 text-red-700" />
      ) : status === "sent" ? (
        <Check aria-hidden="true" className="h-3.5 w-3.5 text-wa-muted" />
      ) : (
        <CheckCheck
          aria-hidden="true"
          className={status === "read" ? "h-3.5 w-3.5 text-wa-read" : "h-3.5 w-3.5 text-wa-muted"}
        />
      )}
      <span className="sr-only">{label}</span>
    </span>
  );
}
