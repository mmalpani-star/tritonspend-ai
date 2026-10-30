"use client";

import { useEffect, useRef, useState } from "react";
import { acceptConsent, getAuthStatus, logIn, logoutParticipant, signUp } from "../lib/api";
import { AuthStatus } from "../lib/types";

export type AuthMode = "login" | "signup";
/** A request from elsewhere on the page to open the form in a mode; `at` makes repeat requests distinct. */
export type AuthRequest = { mode: AuthMode; at: number };
type Mode = AuthMode;

// compact: once signed in with consent, show a slim status bar instead of the full panel.
type Props = { onStatusChange: (status: AuthStatus | null) => void; compact?: boolean; request?: AuthRequest | null };

const MIN_PASSWORD_LENGTH = 8;

export function AuthPanel({ onStatusChange, compact = false, request = null }: Props) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const panelRef = useRef<HTMLElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const update = (next: AuthStatus | null) => {
    setStatus(next);
    onStatusChange(next);
  };

  useEffect(() => {
    void getAuthStatus().then((next) => {
      setStatus(next);
      onStatusChange(next);
    }).catch((error) => setMessage(error instanceof Error ? error.message : "Unable to check session."));
  }, [onStatusChange]);

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
    setPassword("");
    setConfirmation("");
  }

  // Sign up / Log in buttons elsewhere on the landing page bring the form into view in that mode.
  useEffect(() => {
    if (!request) return;
    setMode(request.mode);
    setError("");
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    panelRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
    emailRef.current?.focus({ preventScroll: true });
  }, [request]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (mode === "signup") {
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(`Use a password with at least ${MIN_PASSWORD_LENGTH} characters.`);
        return;
      }
      if (password !== confirmation) {
        setError("Passwords do not match.");
        return;
      }
    }
    setSubmitting(true);
    try {
      const next = mode === "signup" ? await signUp(email, password, confirmation) : await logIn(email, password);
      setPassword("");
      setConfirmation("");
      update(next);
      setMessage(mode === "signup" ? "Account created. Review the consent document to start recording data." : "Signed in.");
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function consent() {
    try {
      update(await acceptConsent());
      setMessage("Consent recorded. Participant data collection is enabled.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to record consent.");
    }
  }

  async function logout() {
    try {
      await logoutParticipant();
      update(null);
      setMode("login");
      setMessage("Signed out.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to sign out.");
    }
  }

  const who = status?.email ?? "pilot participant";

  if (compact && status?.consent_active) {
    return (
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-xs text-[var(--text-muted)]">
        <span>Signed in as <strong className="text-[var(--text)]">{who}</strong>{message ? ` · ${message}` : ""}</span>
        <button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button>
      </div>
    );
  }

  return (
    <section ref={panelRef} id="account" className="panel mb-6 scroll-mt-6">
      <div className="panel-heading"><div><p className="eyebrow">Your account</p><h2 className="panel-title">{status ? "Almost ready" : mode === "signup" ? "Create your account" : "Sign in to TritonSpend"}</h2></div></div>
      {!status ? (
        <form onSubmit={submit} className="grid max-w-xl gap-4" noValidate>
          <div className="scale-selector mb-0" role="group" aria-label="Account action">
            <button type="button" className={`scale-button ${mode === "login" ? "scale-button-selected" : ""}`} aria-pressed={mode === "login"} onClick={() => switchMode("login")}>Sign in</button>
            <button type="button" className={`scale-button ${mode === "signup" ? "scale-button-selected" : ""}`} aria-pressed={mode === "signup"} onClick={() => switchMode("signup")}>Create account</button>
          </div>
          <label className="field-label">Email<input ref={emailRef} type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /><span className="field-help mt-1">Any email address works; it does not need to be @ucsd.edu. We don&apos;t send email, so it isn&apos;t verified.</span></label>
          <label className="field-label">Password<input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} required value={password} onChange={(event) => setPassword(event.target.value)} />{mode === "signup" && <span className="field-help mt-1">At least {MIN_PASSWORD_LENGTH} characters.</span>}</label>
          {mode === "signup" && <label className="field-label">Confirm password<input type="password" autoComplete="new-password" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>}
          {error && <p className="error-box" role="alert">{error}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className="primary-button" disabled={submitting}>{submitting ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}</button>
          </div>
        </form>
      ) : status.consent_active ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--text-muted)]"><span>Signed in as {who} · consent {status.consent_version}</span><button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button></div>
      ) : (
        <div className="grid gap-3 text-sm text-[var(--text-muted)]"><p>Signed in as <strong className="text-[var(--text)]">{who}</strong>. Before you record balances or save forecasts, review the consent document and accept it.</p><a className="text-[var(--primary)] underline" href={status.consent_document_url} target="_blank" rel="noreferrer">Open consent document · {status.consent_version}</a><div><button type="button" className="primary-button" onClick={() => void consent()}>Accept consent</button> <button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button></div></div>
      )}
      {message && <p className="field-help mt-3" role="status">{message}</p>}
    </section>
  );
}
