import type { ActivityEntry, ConversationStatus, DeliveryState, Label, Message, MessageDirection } from "@/lib/types";

export type StoredConversation = {
  id: string;
  name: string;
  phone: string;
  status: ConversationStatus;
  labels: Label[];
  notes: string;
  assignee: string;
  unreadCount: number;
  messages: Message[];
  activity: ActivityEntry[];
  archived?: boolean;
  pinned?: boolean;
  mutedUntil?: string | null;
  favourite?: boolean;
  blocked?: boolean;
};

const hour = 60 * 60 * 1000;
const day = 24 * hour;

function at(offsetMs: number) {
  return new Date(Date.now() + offsetMs).toISOString();
}

function message(
  id: string,
  direction: MessageDirection,
  body: string,
  offsetMs: number,
  delivery: DeliveryState | null = null,
): Message {
  return {
    id,
    direction,
    body,
    at: at(offsetMs),
    delivery: direction === "outbound" ? delivery : null,
  };
}

function activity(id: string, label: string, offsetMs: number): ActivityEntry {
  return { id, label, at: at(offsetMs) };
}

export function createSeedConversations(): StoredConversation[] {
  return [
    {
      id: "maya-chen",
      name: "Maya Chen",
      phone: "+1 415 555 0148",
      status: "open",
      labels: ["GST", "TDS"],
      notes: "Asked accounting to match invoice 1842. Send the receipt once the portal updates.",
      assignee: "Unassigned",
      unreadCount: 2,
      messages: [
        message("maya-1", "inbound", "Hi, can you confirm invoice 1842 was received?", -20 * hour),
        message(
          "maya-2",
          "outbound",
          "Yes. Invoice 1842 is in the queue and should be marked paid today.",
          -19 * hour,
          "delivered",
        ),
        message("maya-3", "inbound", "The portal still shows it as open.", -2 * hour),
        message("maya-4", "inbound", "Could you send the receipt when it updates?", -70 * 60 * 1000),
      ],
      activity: [
        activity("maya-a1", "Sample thread opened from the demo inbox", -20 * hour),
        activity("maya-a2", "Label Billing added in the sample record", -19 * hour),
      ],
    },
    {
      id: "luis-ortega",
      name: "Luis Ortega",
      phone: "+1 628 555 0194",
      status: "open",
      labels: ["DSC"],
      notes: "Wholesale lead. Asked about 20 units shipped to Austin.",
      assignee: "Unassigned",
      unreadCount: 1,
      messages: [
        message("luis-1", "inbound", "Do you ship to Austin?", -8 * hour),
        message("luis-2", "outbound", "Yes. Standard ground is two business days.", -7 * hour, "read"),
        message("luis-3", "inbound", "Can I get a quote for 20 units?", -35 * 60 * 1000),
      ],
      activity: [activity("luis-a1", "Sample lead created", -8 * hour)],
    },
    {
      id: "northline",
      name: "Northline Freight",
      phone: "+1 206 555 0177",
      status: "pending",
      labels: ["ITR"],
      notes: "Waiting on their dock to confirm Friday morning.",
      assignee: "Samira Cole",
      unreadCount: 0,
      messages: [
        message("north-1", "inbound", "We need a pickup for three pallets in Seattle.", -6 * hour),
        message(
          "north-2",
          "outbound",
          "We can pick up Friday between 9 and 11. Does that window work?",
          -5 * hour,
          "delivered",
        ),
        message("north-3", "inbound", "I need to confirm with the dock. I'll reply this afternoon.", -4 * hour),
      ],
      activity: [
        activity("north-a1", "Assigned to Samira Cole in the sample record", -6 * hour),
        activity("north-a2", "Status set to Pending", -4 * hour),
      ],
    },
    {
      id: "asha-reddy",
      name: "Asha Reddy",
      phone: "+1 512 555 0133",
      status: "open",
      labels: ["Misc"],
      notes: "Order 5521 missed the carrier scan. Offer a replacement if it does not move today.",
      assignee: "Evan Brooks",
      unreadCount: 3,
      messages: [
        message("asha-1", "inbound", "Order 5521 still has not shipped.", -30 * hour),
        message(
          "asha-2",
          "outbound",
          "I see the label was created yesterday. I'll check the carrier scan.",
          -29 * hour,
          "delivered",
        ),
        message("asha-3", "outbound", "The carrier has the package. I'll watch the next scan.", -26 * hour, "sent"),
        message("asha-4", "inbound", "It still shows label created on my side.", -6 * hour),
        message("asha-5", "inbound", "This was promised for today.", -5 * hour),
        message("asha-6", "inbound", "Please tell me if I should expect a replacement.", -4 * hour),
      ],
      activity: [
        activity("asha-a1", "Marked Urgent in the sample record", -6 * hour),
        activity("asha-a2", "Assigned to Evan Brooks in the sample record", -29 * hour),
      ],
    },
    {
      id: "jonah-brooks",
      name: "Jonah Brooks",
      phone: "+1 347 555 0180",
      status: "resolved",
      labels: ["TDS"],
      notes: "On-site visit confirmed for Thursday at 2 PM. No follow-up unless he writes again.",
      assignee: "Samira Cole",
      unreadCount: 0,
      messages: [
        message("jonah-1", "inbound", "Can someone come by Thursday afternoon?", -3 * day),
        message("jonah-2", "outbound", "Thursday at 2 PM is open. Should I book it?", -3 * day + hour, "read"),
        message("jonah-3", "inbound", "Yes, that works.", -3 * day + 2 * hour),
        message(
          "jonah-4",
          "outbound",
          "You're confirmed for Thursday at 2 PM. We'll text if the tech is running late.",
          -3 * day + 3 * hour,
          "read",
        ),
      ],
      activity: [
        activity("jonah-a1", "Appointment noted in the sample record", -3 * day + 3 * hour),
        activity("jonah-a2", "Status set to Resolved", -3 * day + 4 * hour),
      ],
    },
    {
      id: "priya-nair",
      name: "Priya Nair",
      phone: "+1 737 555 0162",
      status: "open",
      labels: ["DSC"],
      notes: "Quote is 20 units at $48 with shipping included. The file send in this sample failed.",
      assignee: "Unassigned",
      unreadCount: 0,
      messages: [
        message("priya-1", "inbound", "Can you resend the quote from yesterday?", -2 * day),
        message("priya-2", "outbound", "Sharing the revised quote file here.", -2 * day + 20 * 60 * 1000, "failed"),
        message("priya-3", "inbound", "I didn't get a file.", -26 * hour),
        message(
          "priya-4",
          "outbound",
          "20 units at $48 each, shipping included. I can hold that price until Friday.",
          -25 * hour,
          "delivered",
        ),
      ],
      activity: [
        activity("priya-a1", "Sample file message marked failed in the transcript", -2 * day + 20 * 60 * 1000),
      ],
    },
    {
      id: "helen-cho",
      name: "Helen Cho",
      phone: "+1 213 555 0119",
      status: "pending",
      labels: ["GST"],
      notes: "Waiting on the signed tax form before the next invoice.",
      assignee: "Evan Brooks",
      unreadCount: 0,
      messages: [
        message("helen-1", "inbound", "Do you still need the signed tax form?", -4 * day),
        message(
          "helen-2",
          "outbound",
          "Yes. Once we have it, the next invoice can go out under the new details.",
          -4 * day + 2 * hour,
          "delivered",
        ),
        message("helen-3", "inbound", "I'll send the form tomorrow morning.", -4 * day + 3 * hour),
      ],
      activity: [activity("helen-a1", "Status set to Pending", -4 * day + 3 * hour)],
    },
    {
      id: "omar-farouk",
      name: "Omar Farouk",
      phone: "+1 646 555 0104",
      status: "resolved",
      labels: ["TDS"],
      notes: "Replacement headset was delivered. Close unless a new issue comes in.",
      assignee: "Samira Cole",
      unreadCount: 0,
      messages: [
        message("omar-1", "inbound", "The replacement arrived. Thank you.", -5 * day),
        message("omar-2", "outbound", "Glad it got there. I'll close this out.", -5 * day + hour, "read"),
        message("omar-3", "inbound", "Sounds good.", -5 * day + 2 * hour),
      ],
      activity: [activity("omar-a1", "Status set to Resolved", -5 * day + 2 * hour)],
    },
  ];
}
