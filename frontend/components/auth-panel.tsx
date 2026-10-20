"use client";

import { useEffect, useState } from "react";
import { acceptConsent, getAuthStatus, logoutParticipant, redeemInvite } from "../lib/api";
import { AuthStatus } from "../lib/types";

type Props = { onStatusChange: (status: AuthStatus | null) => void };

export function AuthPanel({ onStatusChange }: Props) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
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

  async function redeem() {
    try {
      const next = await redeemInvite(token.trim());
      update(next);
      setToken("");
      setMessage("Invitation accepted. Review the consent document before recording data.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to redeem invitation.");
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
      setMessage("Signed out.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to sign out.");
    }
  }

  return (
    <section className="panel mb-6">
      <div className="panel-heading"><div><p className="eyebrow">Participant access</p><h2 className="panel-title">{status ? "Your private session" : "Use your invitation"}</h2></div><span className="step-badge">00</span></div>
      {!status ? (
        <div className="flex flex-col gap-3 sm:flex-row">
          <input className="flex-1" placeholder="Paste invitation token" value={token} onChange={(event) => setToken(event.target.value)} />
          <button type="button" className="primary-button" onClick={() => void redeem()}>Redeem invitation</button>
        </div>
      ) : status.consent_active ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--text-muted)]"><span>Authenticated · consent {status.consent_version}</span><button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button></div>
      ) : (
        <div className="grid gap-3 text-sm text-[var(--text-muted)]"><p>Authenticated, but consent is required before participant data can be recorded. Review the configured document and accept it to continue.</p><a className="text-[var(--primary)] underline" href={status.consent_document_url} target="_blank" rel="noreferrer">Open consent document · {status.consent_version}</a><div><button type="button" className="primary-button" onClick={() => void consent()}>Accept consent</button> <button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button></div></div>
      )}
      {message && <p className="field-help mt-3" role="status">{message}</p>}
    </section>
  );
}
