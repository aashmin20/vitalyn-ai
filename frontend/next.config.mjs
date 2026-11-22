/** @type {import('next').NextConfig} */
// NEXT_DIST_DIR lets a second dev server (for testing) run beside the main one.
const nextConfig = { distDir: process.env.NEXT_DIST_DIR || ".next" };

export default nextConfig;
