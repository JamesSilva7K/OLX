// _worker.js — Cloudflare Worker: Proxy reverso para o backend no Render
// Dominio publico: olxproduto.workers.dev → olx-9ee8.onrender.com

export default {
  async fetch(request, env, ctx) {
    const RENDER_BACKEND = "olx-9ee8.onrender.com";

    const url = new URL(request.url);
    url.hostname = RENDER_BACKEND;
    url.protocol = "https:";
    url.port = "";

    // Clona o request para o backend
    const proxyRequest = new Request(url.toString(), {
      method:  request.method,
      headers: request.headers,
      body:    request.method !== "GET" && request.method !== "HEAD"
               ? request.body
               : undefined,
      redirect: "follow",
    });

    try {
      const response = await fetch(proxyRequest);

      // Adiciona headers de seguranca extras na resposta
      const newHeaders = new Headers(response.headers);
      newHeaders.set("X-Proxied-By", "Cloudflare-Worker");
      newHeaders.set("X-Frame-Options", "SAMEORIGIN");
      newHeaders.set("X-Content-Type-Options", "nosniff");

      return new Response(response.body, {
        status:  response.status,
        headers: newHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ ok: false, error: "backend_unavailable" }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }
  }
};
