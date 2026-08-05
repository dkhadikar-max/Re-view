const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://127.0.0.1:8000"
    : ""; // browser: same-origin /api via Next rewrite

type RequestOptions = RequestInit & { auth?: boolean };

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("gra_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("gra_token", token);
  else localStorage.removeItem("gra_token");
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const headers = new Headers(init?.headers || {});
  const useAuth = init?.auth !== false;
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");
  if (useAuth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
      cache: "no-store",
    });
    if (res.status === 401 && typeof window !== "undefined" && !path.includes("/auth/login")) {
      setToken(null);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    if (!res.ok) {
      let detail = `Request failed: ${res.status}`;
      try {
        const body = await res.json();
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail || body);
      } catch {
        detail = await res.text();
      }
      throw new Error(detail || `Request failed: ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export type User = {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  role: string;
};

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
  metrics_note?: string;
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
  birthday?: string;
  anniversary?: string;
  birthday_locked?: boolean;
  anniversary_locked?: boolean;
  review_reward_unlocked?: boolean;
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
  guest_id?: string;
  guest_name?: string;
  platform: string;
  rating: number;
  title?: string;
  body: string;
  sentiment: string;
  themes?: string[] | string;
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
  payment_link_url?: string;
  payment_session_id?: string;
  paid_at?: string;
};

export type SalesAnalytics = {
  review_rate: number;
  repeat_guests: number;
  repeat_guest_rate: number;
  revenue_generated: number;
  upsell_revenue: number;
  room_revenue_active: number;
  ai_messages: number;
  ai_messages_sent: number;
  upsell_conversion: number;
  guest_satisfaction: number;
  google_rating_proxy: number;
  celebrations_enrolled: number;
  period_days: number;
  generated_at: string;
};

export type IntegrationStatus = {
  provider: string;
  priority: number;
  configured: boolean;
  mode: string;
  detail: string;
};

export type V1Readiness = {
  version: string;
  milestone: string;
  queue_backend: string;
  integrations: IntegrationStatus[];
  ready_for_first_hotel: boolean;
  blockers: string[];
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
  validated?: boolean;
  executed: boolean;
  created_at: string;
};

export type EventItem = {
  id: string;
  event_type: string;
  source: string;
  processed: boolean;
  status?: string;
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
  login: async (email: string, password: string) => {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const res = await request<{
      access_token: string;
      token_type: string;
      expires_in: number;
      user: User;
    }>("/api/auth/login", {
      method: "POST",
      auth: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    setToken(res.access_token);
    return res;
  },
  me: () => request<User>("/api/auth/me"),
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
      body: JSON.stringify({ action }),
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
  createPaymentLink: (id: string) =>
    request<{ id: string; url: string; mode: string }>(
      `/api/offers/${id}/payment-link`,
      { method: "POST" }
    ),
  salesAnalytics: (periodDays = 30) =>
    request<SalesAnalytics>(`/api/analytics/sales?period_days=${periodDays}`),
  integrationsStatus: () => request<V1Readiness>("/api/integrations/status"),
  syncCloudbeds: () =>
    request<{ imported: number; events_emitted: number; message: string }>(
      "/api/connectors/cloudbeds/sync",
      { method: "POST" }
    ),
  completeTask: (id: string) =>
    request(`/api/tasks/${id}/complete`, { method: "POST" }),
  checkout: (id: string) =>
    request(`/api/reservations/${id}/checkout`, { method: "POST" }),
  publishReviewResponse: (id: string) =>
    request(`/api/reviews/${id}/publish-response`, { method: "POST" }),
  tickWorkers: () =>
    request<{
      events_processed: number;
      messages_delivered: number;
      workflows_advanced: number;
      celebrate_campaigns?: Record<string, number>;
    }>("/api/workers/tick", { method: "POST" }),

  celebrateConfig: () => request<CelebrateConfig>("/api/celebrate/config"),
  updateCelebrateConfig: (payload: Partial<CelebrateConfig>) =>
    request<CelebrateConfig>("/api/celebrate/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  celebrateDashboard: () =>
    request<CelebrateDashboard>("/api/celebrate/dashboard"),
  celebrateCoupons: () => request<Coupon[]>("/api/celebrate/coupons"),
  celebrateAudits: () => request<CelebrateAudit[]>("/api/celebrate/audits"),
  redeemCoupon: (id: string, amount: number) =>
    request<Coupon>(`/api/celebrate/coupons/${id}/redeem`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  celebrateInvite: (guestId: string) =>
    request<{ guest_id: string; token: string; invite_path: string; message: string }>(
      `/api/celebrate/guests/${guestId}/invite`,
      { method: "POST" }
    ),
  unlockCelebrateFromReview: (guestId: string, reviewId: string) =>
    request<{ unlocked: boolean; invite_path: string; token: string }>(
      `/api/celebrate/guests/${guestId}/unlock-from-review/${reviewId}`,
      { method: "POST" }
    ),
  runCelebrateCampaigns: () =>
    request<Record<string, number>>("/api/celebrate/campaigns/run", {
      method: "POST",
    }),
  celebratePublicStatus: (token: string) =>
    request<GuestCelebrateStatus>(`/api/celebrate/public/${token}`, {
      auth: false,
    }),
  celebrateSubmitDates: (
    token: string,
    payload: { birthday: string; anniversary?: string; confirm: boolean }
  ) =>
    request<{ message: string; coupons_created: string[] }>(
      `/api/celebrate/public/${token}/dates`,
      {
        method: "POST",
        auth: false,
        body: JSON.stringify(payload),
      }
    ),
};

export type CelebrateConfig = {
  id: string;
  tenant_id: string;
  birthday_enabled: boolean;
  birthday_discount_pct: number;
  birthday_days_before: number;
  birthday_days_after: number;
  birthday_min_spend: number;
  birthday_max_uses_per_year: number;
  birthday_stackable: boolean;
  anniversary_enabled: boolean;
  anniversary_discount_pct: number;
  anniversary_days_before: number;
  anniversary_days_after: number;
  anniversary_min_spend: number;
  anniversary_max_uses_per_year: number;
  anniversary_stackable: boolean;
  currency: string;
};

export type CelebrateDashboard = {
  guests_enrolled: number;
  birthday_this_week: number;
  anniversaries_this_month: number;
  coupons_redeemed: number;
  revenue_generated: number;
  repeat_visits: number;
  average_spend: number;
  estimated_discount_cost: number;
  roi?: number | null;
  fraud_alerts: { type: string; phone?: string; guest_count?: number; severity: string }[];
  tagline: string;
};

export type Coupon = {
  id: string;
  guest_id: string;
  guest_name?: string;
  offer_type: string;
  code: string;
  discount_pct: number;
  min_spend: number;
  currency: string;
  year: number;
  valid_from: string;
  valid_until: string;
  status: string;
  personalized_perk?: string;
  redemption_amount?: number;
};

export type CelebrateAudit = {
  id: string;
  guest_id: string;
  field_name: string;
  old_value?: string;
  new_value?: string;
  changed_by: string;
  reason?: string;
  action: string;
  created_at: string;
};

export type GuestCelebrateStatus = {
  guest_id: string;
  guest_name: string;
  property_name?: string;
  review_reward_unlocked: boolean;
  birthday?: string;
  anniversary?: string;
  birthday_locked: boolean;
  anniversary_locked: boolean;
  can_submit_dates: boolean;
  offers: {
    birthday: { enabled: boolean; discount_pct: number; window: string; min_spend: number };
    anniversary: { enabled: boolean; discount_pct: number; window: string; min_spend: number };
  };
  tagline: string;
};
