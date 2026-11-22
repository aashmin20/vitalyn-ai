"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { authErrorMessage, signup } from "@/lib/api/auth";
import { AuthError, AuthLayout, authButton, authField, authLabel } from "@/components/auth/AuthLayout";

export default function SignupPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) return setError("Use a password of at least 8 characters.");
    if (password !== confirm) return setError("The two passwords do not match.");
    setBusy(true);
    setError(null);
    try {
      setDone((await signup(fullName.trim(), email.trim(), password)).message);
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      kicker="New staff account"
      title="Join your ward."
      subtitle="Create an account and sign in straight away. An administrator can change your role later."
    >
      {done ? (
        <div className="space-y-6">
          <div className="flex gap-3 border-l-2 border-vital bg-paper px-4 py-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-vital" />
            <p className="text-sm leading-relaxed text-ink">{done}</p>
          </div>
          <Link href="/login" className={authButton}>Go to sign in <ArrowRight className="h-4 w-4" /></Link>
        </div>
      ) : (
        <>
          <form onSubmit={submit} className="space-y-5">
            <label className={authLabel}>
              Full name
              <input className={authField} value={fullName} maxLength={80} autoComplete="name" onChange={(e) => setFullName(e.target.value)} disabled={busy} required />
            </label>
            <label className={authLabel}>
              Email
              <input className={authField} type="email" autoComplete="username" placeholder="name@hospital.org" value={email} onChange={(e) => setEmail(e.target.value)} disabled={busy} required />
            </label>
            <div className="grid gap-5 sm:grid-cols-2">
              <label className={authLabel}>
                Password
                <input className={authField} type="password" autoComplete="new-password" placeholder="8+ characters" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} required />
              </label>
              <label className={authLabel}>
                Confirm
                <input className={authField} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={busy} required />
              </label>
            </div>
            {error && <AuthError>{error}</AuthError>}
            <button type="submit" className={authButton} disabled={busy}>
              {busy ? "Creating…" : <>Create account <ArrowRight className="h-4 w-4" /></>}
            </button>
          </form>
          <p className="mt-8 border-t border-line pt-6 text-sm text-ink-muted">
            Already have an account?{" "}
            <Link href="/login" className="font-medium text-ink underline decoration-line underline-offset-4 hover:decoration-ink">Sign in</Link>
          </p>
        </>
      )}
    </AuthLayout>
  );
}
