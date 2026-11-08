import { Github, Instagram, Linkedin, Mail, type LucideIcon } from "lucide-react";
import { EXTERNAL_LINK } from "../lib/menu-links";
import { PhotoCredits } from "./visual/photo-credits";

/** Creator links. LinkedIn is taken from the creator's own portfolio site data. Email opens the
 * visitor's mail app, so it is the one link that does not open a new tab. */
export const SOCIAL_LINKS: { label: string; handle: string; href: string; Icon: LucideIcon; external?: false }[] = [
  { label: "Email", handle: "malpanimadhav45@gmail.com", href: "mailto:malpanimadhav45@gmail.com", Icon: Mail, external: false },
  { label: "GitHub", handle: "mmalpani-star", href: "https://github.com/mmalpani-star", Icon: Github },
  { label: "Instagram", handle: "@madhav_malpani105", href: "https://www.instagram.com/madhav_malpani105/?hl=en", Icon: Instagram },
  { label: "LinkedIn", handle: "Madhav Malpani", href: "https://www.linkedin.com/in/madhav-malpani-a79189261/", Icon: Linkedin }
];

/** The cinematic footer: a "Reach Out" band with social links, then the fine print and credits. */
export function SiteFooter() {
  return (
    <footer className="site-footer-v2" aria-labelledby="reach-out-title">
      <div className="page-shell">
        <div className="footer-grid">
          <div>
            <p className="stage-eyebrow">Reach out</p>
            <h2 id="reach-out-title" className="footer-title mt-3">Built by a Triton, <em>for Tritons.</em></h2>
            <p className="footer-lede">Ideas, bugs or a favourite dining hack? Say hello. TritonSpend is an independent student project.</p>
          </div>
          <nav aria-label="Reach out" className="social-row lg:justify-end">
            {SOCIAL_LINKS.map(({ label, handle, href, Icon, external }) => (
              <a key={label} className="social-link" href={href} {...(external === false ? {} : EXTERNAL_LINK)}
                aria-label={external === false ? `${label}: ${handle}` : `${label}: ${handle} (opens in a new tab)`}>
                <span><Icon size={20} aria-hidden="true" /></span>
                <span>{label}<small>{handle}</small></span>
              </a>
            ))}
          </nav>
        </div>
        <div className="footer-meta">
          <span>TritonSpend AI · Keep your own account rules in the driver&apos;s seat.</span>
          <span>Forecasts are illustrative planning estimates. Food photos are illustrative, not menu items.</span>
          <div className="basis-full"><PhotoCredits /></div>
        </div>
      </div>
    </footer>
  );
}
