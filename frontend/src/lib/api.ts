const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export type DashboardStats = {
  arrivals_today: number;
  departures_today: number;
  pending_messages: number;
  negative_reviews: number;
  pending_approvals: number;
  upsells_waiting: number;
  open_tasks: number;
  revenue_today: number;
  upsell_revenue: number;
  repeat_guests: number;
  average_spend: number;
  review_conversion: number;
  google_rating: number;
  response_time_hours: number;
  ai_saved_hours: number;
  occupancy_pct: number;
  active_reservations: number;
  total_guests: number;
};

export type Guest = {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  country?: string;
  language: string;
  stay_count: number;
  lifetime_spend: number;
  travel_type?: string;
  purpose?: string;
  children: number;
  communication_preference: string;
  ltv_score: number;
  satisfaction_score: number;
  complaint_history: number;
  dietary_preferences?: string;
};

export type Reservation = {
  id: string;
  guest_id: string;
  guest_name?: string;
  source: string;
  status: string;
  room_type: string;
  check_in: string;
  check_out: string;
  total_amount: number;
  currency: string;
  adults: number;
  children: number;
  special_requests?: string;
};

export type Message = {
  id: string;
  guest_id: string;
  guest_name?: string;
  channel: string;
  language: string;
  subject?: string;
  body: string;
  status: string;
  message_type: string;
  confidence?: number;
  created_at: string;
  sent_at?: string;
};

export type Review = {
  id: string;
  guest_name?: string;
  platform: string;
  rating: number;
  title?: string;
  body: string;
  sentiment: string;
  themes?: string;
  ai_draft_response?: string;
  published_response?: string;
  responded: boolean;
  created_at: string;
};

export type Approval = {
  id: string;
  approval_type: string;
  title: string;
  content: string;
  status: string;
  confidence?: number;
  related_type?: string;
  related_id?: string;
  reviewed_by?: string;
  reviewed_at?: string;
  created_at: string;
};

export type Offer = {
  id: string;
  name: string;
  description?: string;
  price: number;
  currency: string;
  status: string;
  confidence: number;
  guest_name?: string;
};

export type Task = {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  assignee?: string;
  due_at?: string;
};

export type AIDecision = {
  id: string;
  action: string;
  channel?: string;
  language?: string;
  timing?: string;
  offer?: string;
  confidence: number;
  reasoning?: string;
  executed: boolean;
  created_at: string;
};

export type EventItem = {
  id: string;
  event_type: string;
  source: string;
  processed: boolean;
  created_at: string;
};

export type Connector = {
  id: string;
  provider: string;
  status: string;
  last_sync_at?: string;
};

export type Workflow = {
  id: string;
  name: string;
  trigger_event: string;
  status: string;
  runs: number;
};

export type Notification = {
  id: string;
  title: string;
  body: string;
  level: string;
  read: boolean;
  created_at: string;
};

export type IntelligenceReport = {
  themes: { theme: string; mentions: number; sentiment: string }[];
  most_praised?: string;
  main_complaint?: string;
  total_reviews: number;
};

export type Property = {
  id: string;
  name: string;
  type: string;
  city: string;
  country: string;
  brand_voice: string;
  google_rating: number;
  rooms: number;
};

export const api = {
  stats: () => request<DashboardStats>("/api/dashboard/stats"),
  properties: () => request<Property[]>("/api/properties"),
  guests: () => request<Guest[]>("/api/guests"),
  reservations: () => request<Reservation[]>("/api/reservations"),
  messages: () => request<Message[]>("/api/messages"),
  reviews: () => request<Review[]>("/api/reviews"),
  approvals: (status?: string) =>
    request<Approval[]>(
      status ? `/api/approvals?status=${status}` : "/api/approvals"
    ),
  offers: () => request<Offer[]>("/api/offers"),
  tasks: () => request<Task[]>("/api/tasks"),
  events: () => request<EventItem[]>("/api/events"),
  decisions: () => request<AIDecision[]>("/api/ai-decisions"),
  workflows: () => request<Workflow[]>("/api/workflows"),
  connectors: () => request<Connector[]>("/api/connectors"),
  notifications: () => request<Notification[]>("/api/notifications"),
  intelligence: () => request<IntelligenceReport>("/api/intelligence"),
  actApproval: (id: string, action: "approve" | "reject") =>
    request<Approval>(`/api/approvals/${id}`, {
      method: "POST",
      body: JSON.stringify({ action, reviewed_by: "Sofia Marino" }),
    }),
  syncPms: () =>
    request<{ imported: number; events_emitted: number; message: string }>(
      "/api/connectors/sync",
      { method: "POST" }
    ),
  createReservation: (payload: Record<string, unknown>) =>
    request<Reservation>("/api/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  decide: (reservationId: string) =>
    request(`/api/reservations/${reservationId}/decide`, { method: "POST" }),
  acceptOffer: (id: string) =>
    request(`/api/offers/${id}/accept`, { method: "POST" }),
  completeTask: (id: string) =>
    request(`/api/tasks/${id}/complete`, { method: "POST" }),
  checkout: (id: string) =>
    request(`/api/reservations/${id}/checkout`, { method: "POST" }),
  publishReviewResponse: (id: string) =>
    request(`/api/reviews/${id}/publish-response`, { method: "POST" }),
};
