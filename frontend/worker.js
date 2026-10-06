// Proxies /api/* to the Railway backend, keeping the frontend's relative API calls
// same-origin from the browser's point of view. wrangler.jsonc's
// assets.run_worker_first restricts this to /api/* only; every other path is
// served as a static asset without ever reaching this script.
const BACKEND_ORIGIN = "https://hewg-production.up.railway.app";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = new URL(url.pathname + url.search, BACKEND_ORIGIN);
    return fetch(new Request(target, request));
  },
};
