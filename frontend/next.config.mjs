/**
 * Same-origin API proxy for hosted deployments.
 *
 * The session cookie is SameSite=Lax and host-only, so a browser will not send it from the site's
 * domain (e.g. *.vercel.app) to a backend on another site (e.g. *.onrender.com). When
 * TRITONSPEND_BACKEND_URL is set at build time, /api/* on the frontend's own origin is proxied to
 * the FastAPI backend, which keeps the cookie first-party; the browser build then uses
 * NEXT_PUBLIC_API_BASE_URL="/" (same origin). Local development sets neither and talks to
 * http://localhost:8000 directly, exactly as before.
 */
const backendUrl = (process.env.TRITONSPEND_BACKEND_URL || "").trim().replace(/\/+$/, "");
if (backendUrl && !/^https?:\/\/[^/]+$/.test(backendUrl)) {
  throw new Error("TRITONSPEND_BACKEND_URL must be an origin such as https://api.example.com (no path)");
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return backendUrl ? [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }] : [];
  }
};

export default nextConfig;
