"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel, Stat } from "@/components/ui";
import {
  api,
  type CelebrateAudit,
  type CelebrateConfig,
  type CelebrateDashboard,
  type Coupon,
  type Guest,
} from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export default function CelebratePage() {
  const [dash, setDash] = useState<CelebrateDashboard | null>(null);
  const [config, setConfig] = useState<CelebrateConfig | null>(null);
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [audits, setAudits] = useState<CelebrateAudit[]>([]);
  const [guests, setGuests] = useState<Guest[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inviteLink, setInviteLink] = useState("");

  const load = useCallback(async () => {
    const [d, c, couponsRes, a, g] = await Promise.all([
      api.celebrateDashboard(),
      api.celebrateConfig(),
      api.celebrateCoupons(),
      api.celebrateAudits(),
      api.guests(),
    ]);
    setDash(d);
    setConfig(c);
    setCoupons(couponsRes);
    setAudits(a);
    setGuests(g);
  }, []);

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [load]);

  async function saveConfig(e: FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateCelebrateConfig(config);
      setConfig(updated);
      setMsg("Celebrate Rewards settings saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function runCampaigns() {
    setBusy(true);
    try {
      const res = await api.runCelebrateCampaigns();
      setMsg(
        `Campaigns: ${res.messages_queued} messages, ${res.coupons_ensured} coupons, ${res.coupons_expired} expired`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Campaign run failed");
    } finally {
      setBusy(false);
    }
  }

  async function invite(guestId: string) {
    setBusy(true);
    setError("");
    try {
      const res = await api.celebrateInvite(guestId);
      const url = `${window.location.origin}${res.invite_path}`;
      setInviteLink(url);
      setMsg(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setBusy(false);
    }
  }

  async function redeem(id: string) {
    const amount = Number(prompt("Redemption amount?", "2500") || "0");
    if (!amount) return;
    setBusy(true);
    try {
      await api.redeemCoupon(id, amount);
      setMsg("Coupon redeemed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Redeem failed");
    } finally {
      setBusy(false);
    }
  }

  if (!dash || !config) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading Celebrate Rewards…
      </div>
    );
  }

  const unlocked = guests.filter((g) => g.review_reward_unlocked && !g.birthday_locked);

  return (
    <div>
      <TopBar
        title="Celebrate Rewards"
        subtitle={dash.tagline}
        action={
          <Button onClick={runCampaigns} disabled={busy} variant="secondary">
            Run nightly campaigns
          </Button>
        }
      />
      {error && <p className="mb-4 text-sm text-coral-600">{error}</p>}
      {msg && <p className="mb-4 text-sm text-sea-700">{msg}</p>}
      {inviteLink && (
        <p className="mb-4 break-all rounded-xl bg-ink-50 p-3 text-xs text-ink-600">
          Guest link: {inviteLink}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Guests enrolled" value={dash.guests_enrolled} accent="sea" />
        <Stat label="Birthdays this week" value={dash.birthday_this_week} accent="sand" delay={40} />
        <Stat
          label="Anniversaries this month"
          value={dash.anniversaries_this_month}
          delay={80}
        />
        <Stat
          label="Coupons redeemed"
          value={dash.coupons_redeemed}
          hint={`Revenue ${formatCurrency(dash.revenue_generated, config.currency === "INR" ? "INR" : "EUR")}`}
          accent="sea"
          delay={120}
        />
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Repeat visits" value={dash.repeat_visits} delay={160} />
        <Stat
          label="Avg spend (enrolled)"
          value={formatCurrency(dash.average_spend, config.currency === "INR" ? "INR" : "EUR")}
          delay={200}
        />
        <Stat
          label="Discount cost (est.)"
          value={formatCurrency(dash.estimated_discount_cost, config.currency === "INR" ? "INR" : "EUR")}
          delay={240}
        />
        <Stat label="ROI" value={dash.roi != null ? `${dash.roi}x` : "—"} delay={280} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Panel title="Merchant configuration" className="[animation-delay:320ms]">
          <form onSubmit={saveConfig} className="space-y-4 text-sm">
            <fieldset className="space-y-2">
              <legend className="font-display text-lg text-ink-900">Birthday offer</legend>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={config.birthday_enabled}
                  onChange={(e) =>
                    setConfig({ ...config, birthday_enabled: e.target.checked })
                  }
                />
                Enabled
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-ink-500">
                  Discount %
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.birthday_discount_pct}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        birthday_discount_pct: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Min spend
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.birthday_min_spend}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        birthday_min_spend: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Days before
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.birthday_days_before}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        birthday_days_before: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Days after
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.birthday_days_after}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        birthday_days_after: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={config.birthday_stackable}
                  onChange={(e) =>
                    setConfig({ ...config, birthday_stackable: e.target.checked })
                  }
                />
                Stackable
              </label>
            </fieldset>

            <fieldset className="space-y-2 border-t border-ink-100 pt-4">
              <legend className="font-display text-lg text-ink-900">Anniversary offer</legend>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={config.anniversary_enabled}
                  onChange={(e) =>
                    setConfig({ ...config, anniversary_enabled: e.target.checked })
                  }
                />
                Enabled
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-ink-500">
                  Discount %
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.anniversary_discount_pct}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        anniversary_discount_pct: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Min spend
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.anniversary_min_spend}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        anniversary_min_spend: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Days before
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.anniversary_days_before}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        anniversary_days_before: Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label className="text-xs text-ink-500">
                  Days after
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-ink-200 px-2 py-1.5"
                    value={config.anniversary_days_after}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        anniversary_days_after: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
            </fieldset>
            <Button type="submit" disabled={busy}>
              Save settings
            </Button>
          </form>
        </Panel>

        <Panel title="Awaiting date lock" className="[animation-delay:360ms]">
          <p className="mb-3 text-xs text-ink-500">
            Reviewers who unlocked Celebrate Rewards but have not locked dates yet.
          </p>
          {unlocked.length === 0 ? (
            <Empty>No pending enrollments</Empty>
          ) : (
            <ul className="divide-y divide-ink-50">
              {unlocked.map((g) => (
                <li
                  key={g.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium text-ink-900">{g.name}</p>
                    <p className="text-xs text-ink-400">{g.email}</p>
                  </div>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => invite(g.id)}
                  >
                    Copy invite
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Coupons" className="mt-6 [animation-delay:400ms]">
        {coupons.length === 0 ? (
          <Empty>No coupons yet</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                  <th className="pb-3 font-medium">Code</th>
                  <th className="pb-3 font-medium">Guest</th>
                  <th className="pb-3 font-medium">Type</th>
                  <th className="pb-3 font-medium">Window</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {coupons.map((c) => (
                  <tr key={c.id}>
                    <td className="py-3 font-medium">{c.code}</td>
                    <td className="py-3">{c.guest_name}</td>
                    <td className="py-3 capitalize">
                      {c.offer_type} · {c.discount_pct}%
                      {c.personalized_perk ? ` · ${c.personalized_perk}` : ""}
                    </td>
                    <td className="py-3 text-xs text-ink-500">
                      {c.valid_from} → {c.valid_until}
                    </td>
                    <td className="py-3">
                      <Badge tone={c.status}>{c.status}</Badge>
                    </td>
                    <td className="py-3">
                      {c.status === "active" && (
                        <Button variant="ghost" onClick={() => redeem(c.id)}>
                          Redeem
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {dash.fraud_alerts.length > 0 && (
        <Panel title="Fraud alerts" className="mt-6 [animation-delay:440ms]">
          <ul className="space-y-2">
            {dash.fraud_alerts.map((a, i) => (
              <li key={i} className="rounded-xl bg-coral-500/10 px-3 py-2 text-sm text-coral-600">
                {a.type}: {a.phone} ({a.guest_count} guests)
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Date change audit" className="mt-6 [animation-delay:480ms]">
        {audits.length === 0 ? (
          <Empty>No celebrate audits</Empty>
        ) : (
          <ul className="divide-y divide-ink-50 text-sm">
            {audits.slice(0, 20).map((a) => (
              <li key={a.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{a.action}</Badge>
                  <span className="font-medium">{a.field_name}</span>
                  <span className="text-xs text-ink-400">by {a.changed_by}</span>
                </div>
                <p className="mt-1 text-xs text-ink-500">
                  {a.old_value || "—"} → {a.new_value || "—"}
                  {a.reason ? ` · ${a.reason}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
