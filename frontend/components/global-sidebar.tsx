"use client";

import { Heart, LogIn, LogOut, MessagesSquare, Settings, Star, Store, UserRound, UserPlus, X, type LucideIcon } from "lucide-react";
import Image from "next/image";
import { useEffect, useId, useRef } from "react";
import { SIDEBAR_SECTIONS, YouPage } from "../lib/account";

export const TRIDENT_SRC = "/brand/ucsd-trident-gold.png"; // the same mark as the theme slider's thumb

const ICONS: Record<YouPage, LucideIcon> = {
  account: UserRound,
  "favourite-dishes": Heart,
  "favourite-venues": Store,
  ratings: Star,
  messages: MessagesSquare,
  settings: Settings
};

/** The header button that opens the sidebar: the Triton trident, not a hamburger. */
export function SidebarTrigger({ open, controls, onOpen }: { open: boolean; controls: string; onOpen: () => void }) {
  return (
    <button type="button" className="sidebar-trigger" aria-label="Open menu" aria-haspopup="dialog" aria-expanded={open} aria-controls={controls} onClick={onOpen}>
      <Image src={TRIDENT_SRC} alt="" width={26} height={26} priority className="sidebar-trigger-trident" />
    </button>
  );
}

type Props = {
  id: string;
  open: boolean;
  onClose: () => void;
  signedIn: boolean;
  email: string | null;
  current: YouPage | null;
  onSelect: (page: YouPage) => void;
  onSignOut: () => void;
  onSignIn: () => void;
  onSignUp: () => void;
};

/**
 * A left-side navigation drawer built on the native modal <dialog>: focus stays inside while it is
 * open, Escape closes it, a click outside the panel closes it, and focus returns to the trigger.
 */
export function GlobalSidebar({ id, open, onClose, signedIn, email, current, onSelect, onSignOut, onSignIn, onSignUp }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const closingOnPurpose = useRef(false);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      closingOnPurpose.current = true; // the "close" event that follows is ours, not the browser's
      dialog.close();
      // Back to the trident, also for pointer clicks that never focused it.
      document.querySelector<HTMLElement>(`[aria-controls="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
    }
  }, [open, id]);

  const choose = (action: () => void) => {
    onClose();
    action();
  };

  return (
    <dialog
      ref={ref}
      id={id}
      className="sidebar-drawer"
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); onClose(); }} // Escape
      onClose={() => {
        // The browser can close a modal dialog by itself; keep React's state in step when it does.
        if (closingOnPurpose.current) closingOnPurpose.current = false;
        else onClose();
      }}
      onClick={(event) => { if (event.target === ref.current) onClose(); }} // the backdrop, outside the panel
    >
      <div className="sidebar-panel">
        <div className="sidebar-head">
          <span className="sidebar-brand">
            <Image src={TRIDENT_SRC} alt="" width={24} height={24} className="sidebar-trigger-trident" />
            <span id={titleId} className="font-display text-lg font-bold tracking-tight text-[var(--text)]">TritonSpend <span className="text-[var(--primary)]">AI</span></span>
          </span>
          <button type="button" className="sidebar-close" aria-label="Close menu" onClick={onClose}><X size={18} aria-hidden="true" /></button>
        </div>

        {signedIn ? (
          <>
            {email && <p className="sidebar-who" title={email}>Signed in as <strong>{email}</strong></p>}
            <nav aria-label="Your TritonSpend" className="sidebar-nav">
              {SIDEBAR_SECTIONS.map((section) => (
                <section key={section.title} className="sidebar-section" aria-label={section.title}>
                  <h2 className="sidebar-section-title">{section.title}</h2>
                  <ul>
                    {section.items.map((item) => {
                      if (item.kind === "sign-out") {
                        return (
                          <li key="sign-out">
                            <button type="button" className="sidebar-link sidebar-link-danger" onClick={() => choose(onSignOut)}>
                              <LogOut size={17} aria-hidden="true" /> {item.label}
                            </button>
                          </li>
                        );
                      }
                      const Icon = ICONS[item.page];
                      const active = current === item.page;
                      return (
                        <li key={item.page}>
                          <a
                            href={`#you/${item.page}`}
                            className={`sidebar-link ${active ? "sidebar-link-active" : ""}`}
                            aria-current={active ? "page" : undefined}
                            onClick={(event) => { event.preventDefault(); choose(() => onSelect(item.page)); }}
                          >
                            <Icon size={17} aria-hidden="true" /> {item.label}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </nav>
          </>
        ) : (
          <div className="sidebar-signed-out">
            <p>Sign in to see your account, favourite venues and dishes, reviews and discussions.</p>
            <button type="button" className="primary-button w-full justify-center" onClick={() => choose(onSignIn)}><LogIn size={16} aria-hidden="true" /> Sign in</button>
            <button type="button" className="secondary-button w-full justify-center" onClick={() => choose(onSignUp)}><UserPlus size={16} aria-hidden="true" /> Create account</button>
          </div>
        )}
        <p className="sidebar-foot">Your favourites and these lists are private. Reviews and comments appear publicly under your Food Chat name, never your email.</p>
      </div>
    </dialog>
  );
}
