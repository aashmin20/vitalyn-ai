"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { authErrorMessage } from "@/lib/api/auth";
import { useAuth } from "@/components/auth/AuthProvider";
import { AuthError, AuthLayout, authButton, authField, authLabel } from "@/components/auth/AuthLayout";

function LoginForm() {
  const { signIn } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await signIn(email.trim(), password);
      if (me.status === "active") router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout kicker="Staff sign in" title="Welcome back." subtitle="Sign in with the email and password of your staff account.">
      <form onSubmit={submit} className="space-y-5">
        <label className={authLabel}>
          Email
          <input className={authField} type="email" autoComplete="username" placeholder="name@hospital.org" value={email} onChange={(e) => setEmail(e.target.value)} disabled={busy} required />
        </label>
        <label className={authLabel}>
          Password
          <input className={authField} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} required />
        </label>
        {error && <AuthError>{error}</AuthError>}
        <button type="submit" className={authButton} disabled={busy || !email || !password}>
          {busy ? "Signing in…" : <>Sign in <ArrowRight className="h-4 w-4" /></>}
        </button>
      </form>
      <p className="mt-8 border-t border-line pt-6 text-sm text-ink-muted">
        New staff member?{" "}
        <Link href="/signup" className="font-medium text-ink underline decoration-line underline-offset-4 hover:decoration-ink">Create an account</Link>
      </p>
    </AuthLayout>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
