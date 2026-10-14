"use client";

import { useAppDialog } from "@/components/AppDialog";
import { useAuth } from "@/components/AuthProvider";
import { Avatar } from "@/components/Avatar";
import { cn } from "@/lib/cn";
import {
  disablePushNotifications,
  getNotifyPermission,
  getNotifyPreference,
  pushSupport,
  requestNotifyPermission,
  showDesktopNotification,
} from "@/lib/desktop-notifications";
import { Bell, Camera, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

type Profile = {
  id: string;
  name: string;
  email: string;
  mobile: string | null;
  role: "admin" | "member";
  hasAvatar: boolean;
  avatarUrl: string | null;
};

export function ProfileScreen() {
  const router = useRouter();
  const { session, ready, refresh, applySession, csrfToken, authedFetch } = useAuth();
  const { confirm } = useAppDialog();
  const fileRef = useRef<HTMLInputElement>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNext, setShowNext] = useState(false);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [notifyOn, setNotifyOn] = useState(false);
  const [notifyPermission, setNotifyPermission] = useState<string>("unsupported");

  useEffect(() => {
    setNotifyPermission(getNotifyPermission());
    setNotifyOn(getNotifyPreference() === "on" && getNotifyPermission() === "granted");
  }, []);

  const load = useCallback(async () => {
    const response = await fetch("/api/auth/profile", { cache: "no-store" });
    if (!response.ok) throw new Error("load_failed");
    const data = (await response.json()) as { profile: Profile };
    setProfile(data.profile);
    setName(data.profile.name || "");
    setPhase("ready");
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (!session?.authenticated) {
      router.replace(`/login?next=${encodeURIComponent("/account")}`);
      return;
    }
    void load().catch(() => setPhase("error"));
  }, [ready, session?.authenticated, load, router]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (!csrfToken || !session?.authenticated) return;
    setBusy("save");
    setMessage(null);
    try {
      const body: { name: string; currentPassword?: string; nextPassword?: string } = { name };
      if (nextPassword) {
        body.currentPassword = currentPassword;
        body.nextPassword = nextPassword;
      }
      const response = await fetch("/api/auth/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify(body),
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        profile?: Profile;
      };
      if (!response.ok) throw new Error(data.detail || data.error || "Could not save profile.");
      if (data.profile) {
        setProfile(data.profile);
        setName(data.profile.name || "");
      }
      setCurrentPassword("");
      setNextPassword("");
      await refresh();
      setMessage({ ok: true, text: data.detail || "Profile saved." });
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not save profile." });
    } finally {
      setBusy("");
    }
  }

  async function uploadPhoto(file: File | null) {
    if (!file || !csrfToken) return;
    setBusy("photo");
    setMessage(null);
    try {
      const form = new FormData();
      form.set("photo", file);
      const response = await fetch("/api/auth/profile/avatar", {
        method: "POST",
        headers: { "x-csrf-token": csrfToken },
        body: form,
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        profile?: Profile;
      };
      if (!response.ok) throw new Error(data.detail || data.error || "Could not upload photo.");
      if (data.profile) setProfile(data.profile);
      await refresh();
      setMessage({ ok: true, text: data.detail || "Photo saved." });
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not upload photo." });
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removePhoto() {
    if (!csrfToken || !profile?.hasAvatar) return;
    if (!(await confirm("Remove your profile photo?", { title: "Remove photo", confirmLabel: "Remove", danger: true }))) {
      return;
    }
    setBusy("photo");
    setMessage(null);
    try {
      const response = await fetch("/api/auth/profile/avatar", {
        method: "DELETE",
        headers: { "x-csrf-token": csrfToken },
      });
      const data = (await response.json().catch(() => ({}))) as {
        detail?: string;
        error?: string;
        profile?: Profile;
      };
      if (!response.ok) throw new Error(data.detail || data.error || "Could not remove photo.");
      if (data.profile) setProfile(data.profile);
      await refresh();
      setMessage({ ok: true, text: data.detail || "Photo removed." });
    } catch (reason) {
      setMessage({ ok: false, text: reason instanceof Error ? reason.message : "Could not remove photo." });
    } finally {
      setBusy("");
    }
  }

  async function logout() {
    if (!csrfToken) return;
    setBusy("logout");
    try {
      const response = await fetch("/api/admin/session", {
        method: "DELETE",
        headers: { "x-csrf-token": csrfToken },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("logout_failed");
      applySession({
        authenticated: false,
        adminConfigured: true,
        csrfToken: "",
        email: null,
        name: null,
        role: null,
        avatarUrl: null,
      });
      await refresh();
      router.replace("/login");
    } catch {
      setMessage({ ok: false, text: "Could not sign out." });
      setBusy("");
    }
  }

  if (!ready || phase === "loading") {
    return <p className="p-6 text-sm text-wa-muted">Loading profile…</p>;
  }
  if (phase === "error" || !profile) {
    return <p className="p-6 text-sm text-red-700">Could not load profile.</p>;
  }

  const displayName = name.trim() || profile.email;

  return (
    <main className="min-h-0 flex-1 overflow-y-auto bg-wa-app px-4 py-6 md:px-6">
      <div className="mx-auto w-full max-w-lg rounded-xl border border-wa-line bg-white p-4 shadow-sm sm:p-5">
        <h1 className="font-display text-xl font-bold tracking-tight">Profile settings</h1>
        <p className="mt-1 text-sm text-wa-muted">Update your photo, name, and password. Changes save to your account.</p>

        <div className="mt-5 flex flex-col items-center gap-3">
          <div className="relative">
            <Avatar name={displayName} size={88} src={profile.avatarUrl} />
            <button
              type="button"
              disabled={Boolean(busy)}
              onClick={() => fileRef.current?.click()}
              className="absolute -bottom-1 -right-1 grid h-9 w-9 place-items-center rounded-full border border-wa-line bg-white text-wa-ink shadow-sm hover:bg-wa-app disabled:opacity-40"
              aria-label="Change profile photo"
            >
              {busy === "photo" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(event) => void uploadPhoto(event.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <button
              type="button"
              disabled={Boolean(busy)}
              onClick={() => fileRef.current?.click()}
              className="h-8 rounded-lg border border-wa-line px-3 text-xs font-medium hover:bg-wa-app disabled:opacity-40"
            >
              Upload photo
            </button>
            {profile.hasAvatar ? (
              <button
                type="button"
                disabled={Boolean(busy)}
                onClick={() => void removePhoto()}
                className="h-8 rounded-lg border border-wa-line px-3 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
              >
                Remove photo
              </button>
            ) : null}
          </div>
          <p className="text-center text-[11px] text-wa-muted">JPG, PNG, or WebP · max 2 MB</p>
        </div>

        <div className="mt-5 rounded-lg border border-wa-line bg-wa-app/60 p-3">
          <div className="flex items-start gap-3">
            <Bell className="mt-0.5 h-4 w-4 shrink-0 text-wa-green-dark" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">Push notifications</p>
              <p className="mt-0.5 text-xs text-wa-muted">
                Alerts for new WhatsApp messages on desktop and mobile — including when this tab or browser is closed.
                On iPhone/iPad, install the app to the Home Screen first (Share → Add to Home Screen), then enable.
              </p>
              {notifyPermission === "unsupported" || !pushSupport() ? (
                <p className="mt-2 text-xs text-red-700">
                  This browser does not support push notifications. Use Chrome/Edge/Firefox, or install the PWA on
                  iOS 16.4+.
                </p>
              ) : notifyPermission === "denied" ? (
                <p className="mt-2 text-xs text-red-700">
                  Blocked in browser settings. Click the lock icon in the address bar → Notifications → Allow.
                </p>
              ) : (
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => {
                    void (async () => {
                      if (notifyOn) {
                        await disablePushNotifications(authedFetch);
                        setNotifyOn(false);
                        setMessage({ ok: true, text: "Push notifications turned off." });
                        return;
                      }
                      const result = await requestNotifyPermission(authedFetch);
                      setNotifyPermission(result);
                      const on = result === "granted";
                      setNotifyOn(on);
                      if (on) {
                        showDesktopNotification({
                          title: "WhatsApp CRM",
                          body: "Push notifications are on — including when the browser is closed.",
                          tag: "wa-notify-enabled",
                        });
                        setMessage({ ok: true, text: "Push notifications enabled." });
                      } else {
                        setMessage({ ok: false, text: "Notification permission was not granted." });
                      }
                    })();
                  }}
                  className={cn(
                    "mt-2 h-8 rounded-lg px-3 text-xs font-medium",
                    notifyOn
                      ? "border border-wa-line bg-white hover:bg-white"
                      : "bg-wa-green text-white hover:bg-wa-green-dark",
                  )}
                >
                  {notifyOn ? "Turn off" : "Enable notifications"}
                </button>
              )}
            </div>
          </div>
        </div>

        <form onSubmit={(event) => void saveProfile(event)} className="mt-5 space-y-3">
          <label className="block text-sm font-medium" htmlFor="profile-name">
            Name
            <input
              id="profile-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
            />
          </label>

          <label className="block text-sm font-medium" htmlFor="profile-email">
            Email
            <input
              id="profile-email"
              value={profile.email}
              readOnly
              className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-wa-app px-3 text-sm text-wa-muted"
            />
          </label>

          <label className="block text-sm font-medium" htmlFor="profile-mobile">
            Mobile
            <input
              id="profile-mobile"
              value={profile.mobile ? `+${profile.mobile}` : "—"}
              readOnly
              className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-wa-app px-3 text-sm text-wa-muted"
            />
          </label>

          <label className="block text-sm font-medium" htmlFor="profile-role">
            Role
            <input
              id="profile-role"
              value={profile.role === "admin" ? "Admin" : "Member"}
              readOnly
              className="mt-1 h-10 w-full rounded-lg border border-wa-line bg-wa-app px-3 text-sm text-wa-muted capitalize"
            />
          </label>

          <div className="border-t border-wa-line pt-3">
            <p className="text-sm font-medium">Change password</p>
            <p className="mt-0.5 text-xs text-wa-muted">Leave blank to keep your current password.</p>
            <label className="mt-2 block text-sm font-medium" htmlFor="profile-current">
              Current password
              <span className="mt-1 flex gap-2">
                <input
                  id="profile-current"
                  type={showCurrent ? "text" : "password"}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  className="h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrent((value) => !value)}
                  className="h-10 shrink-0 rounded-lg border border-wa-line px-3 text-xs"
                >
                  {showCurrent ? "Hide" : "Show"}
                </button>
              </span>
            </label>
            <label className="mt-2 block text-sm font-medium" htmlFor="profile-next">
              New password
              <span className="mt-1 flex gap-2">
                <input
                  id="profile-next"
                  type={showNext ? "text" : "password"}
                  autoComplete="new-password"
                  value={nextPassword}
                  onChange={(event) => setNextPassword(event.target.value)}
                  className="h-10 w-full rounded-lg border border-wa-line px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-wa-green"
                />
                <button
                  type="button"
                  onClick={() => setShowNext((value) => !value)}
                  className="h-10 shrink-0 rounded-lg border border-wa-line px-3 text-xs"
                >
                  {showNext ? "Hide" : "Show"}
                </button>
              </span>
            </label>
          </div>

          {message ? (
            <p className={cn("text-sm", message.ok ? "text-wa-green-dark" : "text-red-700")} aria-live="polite">
              {message.text}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy === "save"}
            className="inline-flex h-10 w-full items-center justify-center rounded-lg bg-wa-green text-sm font-medium text-white hover:bg-wa-green-dark disabled:opacity-40"
          >
            {busy === "save" ? "Saving…" : "Save profile"}
          </button>
        </form>

        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => void logout()}
          className="mt-3 inline-flex h-10 w-full items-center justify-center rounded-lg border border-wa-line text-sm font-medium hover:bg-wa-app disabled:opacity-40"
        >
          {busy === "logout" ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </main>
  );
}
