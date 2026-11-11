/** A static site: `next build` writes plain HTML/JS to out/, which Vercel (or any host) serves. */
const nextConfig = { output: "export", reactStrictMode: true };
export default nextConfig;
