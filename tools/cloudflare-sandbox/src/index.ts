import { switchPort } from '@cloudflare/containers';
import { AwsClient } from 'aws4fetch';
import {
  Sandbox as BaseSandbox,
  ContainerProxy,
  getSandbox,
  proxyToSandbox
} from '@cloudflare/sandbox';
import {
  autoApprove,
  compose,
  enforceModel,
  enforcePolicy,
  type HandlerContext,
  isRequest,
  type JsonRpcMessage,
  log,
  type MessageHandler,
  tryParse
} from './rpc';

export { ContainerProxy };

export class Sandbox extends BaseSandbox<Env> {
  enableInternet = false;
  interceptHttps = true;
}

declare global {
  interface Env {
    OPENAI_API_KEY?: string;
    ANTHROPIC_API_KEY?: string;
    CLAUDE_CODE_OAUTH_TOKEN?: string;
    AUTH_TOKEN?: string;
    GITHUB_TOKEN?: string;
    SANDBOX_SLEEP_AFTER?: string;
    R2_ACCESS_KEY_ID?: string;
    R2_SECRET_ACCESS_KEY?: string;
    CF_SANDBOX_ALLOWED_HOSTS?: string;
    [key: string]: string | undefined;
  }
}

const CODEX_WS_PORT = 4500;
const SANDBOX_ID_RE = /^\/ws\/([a-zA-Z0-9_-]{1,64})$/;
const AGENT_SANDBOX_START_RE = /^\/sandbox\/([a-zA-Z0-9_-]{1,64})\/start$/;

const DEFAULT_ALLOWED_HOSTS = new Set([
  'apache.org',
  'apis.google.com',
  'api.github.com',
  'api.nuget.org',
  'archive.ubuntu.com',
  'astral.sh',
  'auth.docker.io',
  'bitbucket.org',
  'bootstrap.pypa.io',
  'bun.sh',
  'cdn.jsdelivr.net',
  'codeload.github.com',
  'cocoapods.org',
  'cpan.org',
  'crates.io',
  'deb.debian.org',
  'debian.org',
  'deno.land',
  'dl-cdn.alpinelinux.org',
  'docker.com',
  'docker.io',
  'download.docker.com',
  'dot.net',
  'dotnet.microsoft.com',
  'eclipse.org',
  'fastly.com',
  'files.pythonhosted.org',
  'gcr.io',
  'getcomposer.org',
  'ghcr.io',
  'github.com',
  'github-releases.githubusercontent.com',
  'gitlab.com',
  'golang.org',
  'goproxy.io',
  'gradle.org',
  'hex.pm',
  'index.crates.io',
  'java.com',
  'java.net',
  'jsdelivr.net',
  'maven.org',
  'metacpan.org',
  'nodejs.org',
  'nodesource.com',
  'npmjs.com',
  'npmjs.org',
  'nuget.org',
  'objects.githubusercontent.com',
  'packagist.com',
  'packagist.org',
  'packages.microsoft.com',
  'pkg.go.dev',
  'playwright.azureedge.net',
  'ports.ubuntu.com',
  'production.cloudflare.docker.com',
  'production.cloudfront.docker.com',
  'proxy.golang.org',
  'pub.dev',
  'pypa.io',
  'pypi.org',
  'pypi.python.org',
  'pythonhosted.org',
  'quay.io',
  'raw.githubusercontent.com',
  'registry-1.docker.io',
  'registry.k8s.io',
  'registry.npmjs.org',
  'release-assets.githubusercontent.com',
  'repo.maven.apache.org',
  'rubygems.org',
  'rubyonrails.org',
  'rustup.rs',
  'security.ubuntu.com',
  'services.gradle.org',
  'sh.rustup.rs',
  'spring.io',
  'static.crates.io',
  'static.rust-lang.org',
  'sum.golang.org',
  'swift.org',
  'unpkg.com',
  'yarnpkg.com',
  'ziglang.org'
]);

const DEFAULT_ALLOWED_SUFFIXES = [
  '.amazontrust.com',
  '.bun.sh',
  '.debian.org',
  '.digicert.com',
  '.docker.com',
  '.docker.io',
  '.github.com',
  '.githubcopilot.com',
  '.githubusercontent.com',
  '.gitlab.com',
  '.googleapis.com',
  '.googleusercontent.com',
  '.gstatic.com',
  '.gvt1.com',
  '.hashicorp.com',
  '.lencr.org',
  '.microsoft.com',
  '.npmjs.org',
  '.one.digicert.com',
  '.packagist.org',
  '.pki.goog',
  '.production.cloudflare.docker.com',
  '.production.cloudfront.docker.com',
  '.pythonhosted.org',
  '.rubygems.org',
  '.sectigo.com',
  '.ubuntu.com',
  '.yarnpkg.com'
];

// --- Egress control ---
// The container uses OPENAI_BASE_URL=http://api.openai.com/v1 so requests
// hit the outbound handler, which injects the real API key and upgrades to
// HTTPS. The key never enters the container. With interceptHttps = true,
// HTTPS requests are also intercepted via the Cloudflare CA cert.

Sandbox.outboundByHost = {
  'api.openai.com': async (request: Request, env: Env) => {
    if (!env.OPENAI_API_KEY) {
      return new Response('Missing OPENAI_API_KEY', { status: 500 });
    }
    const url = new URL(request.url);
    const headers = new Headers(request.headers);
    headers.set('Authorization', `Bearer ${env.OPENAI_API_KEY}`);
    headers.delete('X-Api-Key');
    return fetch(`https://api.openai.com${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body: request.body
    });
  },
  'api.anthropic.com': async (request: Request, env: Env) => {
    const url = new URL(request.url);
    const headers = new Headers(request.headers);

    // Claude picks the auth header based on which env var it sees in the
    // container; mirror that choice here when swapping in the real secret.
    if (headers.has('x-api-key') && env.ANTHROPIC_API_KEY) {
      headers.set('x-api-key', env.ANTHROPIC_API_KEY);
    } else if (env.CLAUDE_CODE_OAUTH_TOKEN) {
      headers.set('Authorization', `Bearer ${env.CLAUDE_CODE_OAUTH_TOKEN}`);
      headers.delete('x-api-key');
    }

    const resp = await fetch(`https://api.anthropic.com${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body: request.body
    });
    console.log(`[egress] api.anthropic.com ${request.method} ${url.pathname} -> ${resp.status}`);
    return resp;
  },
  'platform.claude.com': async (request: Request, env: Env) => {
    // Claude Code's OAuth flow validates the subscription token here
    // (e.g. /v1/oauth/hello) before hitting api.anthropic.com.
    // TODO: need to verify that this code block is even needed. Should double-check if this path gets
    //  executed actually or if this was part of some sort of debugging of a problem.
    const url = new URL(request.url);
    const headers = new Headers(request.headers);
    if (env.CLAUDE_CODE_OAUTH_TOKEN) {
      headers.set('Authorization', `Bearer ${env.CLAUDE_CODE_OAUTH_TOKEN}`);
      headers.delete('x-api-key');
    }
    const resp = await fetch(`https://platform.claude.com${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body: request.body
    });
    console.log(`[egress] platform.claude.com ${request.method} ${url.pathname} -> ${resp.status}`);
    return resp;
  },
  'github.com': async (request: Request, env: Env) => {
    const url = new URL(request.url);
    const headers = new Headers(request.headers);
    if (env.GITHUB_TOKEN) {
      headers.set(
        'Authorization',
        `Basic ${btoa(`x-access-token:${env.GITHUB_TOKEN}`)}`
      );
    }
    const target = `https://github.com${url.pathname}${url.search}`;
    console.log(`[egress] Allowed: ${request.method} ${target}`);
    return fetch(target, {
      method: request.method,
      headers,
      body: request.body
    });
  }
};

Sandbox.outbound = async (request: Request, rawEnv: unknown) => {
  const env = rawEnv as Env | undefined;
  if (env && shouldSignR2Request(request, env)) {
    return signAndFetchR2(request, env);
  }
  if (isAllowedCodingRequest(request, env)) {
    return fetch(request);
  }
  console.log(`[egress] Blocked: ${request.method} ${request.url}`);
  return new Response('Forbidden by egress policy', { status: 403 });
};

function shouldSignR2Request(request: Request, env: Env): boolean {
  if (!env.R2_ACCESS_KEY_ID || !env.R2_SECRET_ACCESS_KEY) return false;
  const url = new URL(request.url);
  if (!url.hostname.endsWith('.r2.cloudflarestorage.com')) return false;
  return allowedHost(url.hostname, env);
}

function allowedHost(hostname: string, env: Env): boolean {
  const configured = env.CF_SANDBOX_ALLOWED_HOSTS;
  if (!configured) return false;
  return hostMatches(hostname, configured.split(','));
}

function isAllowedCodingRequest(request: Request, env?: Env): boolean {
  const hostname = new URL(request.url).hostname.toLowerCase();
  if (DEFAULT_ALLOWED_HOSTS.has(hostname)) return true;
  if (DEFAULT_ALLOWED_SUFFIXES.some((suffix) => hostname.endsWith(suffix))) return true;
  if (env?.CF_SANDBOX_ALLOWED_HOSTS && hostMatches(hostname, env.CF_SANDBOX_ALLOWED_HOSTS.split(','))) {
    return true;
  }
  return false;
}

function hostMatches(hostname: string, patterns: string[]): boolean {
  const normalized = hostname.toLowerCase();
  return patterns
    .map((pattern) => pattern.trim().toLowerCase())
    .filter(Boolean)
    .some((pattern) => {
      const host = pattern.replace(/:\d+$/, '');
      if (host === normalized) return true;
      if (host.startsWith('*.')) return normalized.endsWith(host.slice(1));
      if (host.startsWith('**.')) return normalized.endsWith(host.slice(2));
      return false;
    });
}

async function signAndFetchR2(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  headers.delete('authorization');
  headers.delete('x-amz-date');
  headers.delete('x-amz-content-sha256');
  headers.delete('x-amz-security-token');

  const aws = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID!,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY!,
    service: 's3',
    region: 'auto'
  });

  console.log(`[egress] R2 signed: ${request.method} ${url.hostname}${url.pathname}`);
  return aws.fetch(`https://${url.hostname}${url.pathname}${url.search}`, {
    method: request.method,
    headers,
    body: request.body
  });
}

// --- Custom command: sandbox/setup ---
// Wipes /workspace and clones a fresh copy of the repo.

function sandboxSetup(sandbox: ReturnType<typeof getSandbox>): MessageHandler {
  return (msg, ctx) => {
    if (
      ctx.direction !== 'client-to-server' ||
      !isRequest(msg) ||
      msg.method !== 'sandbox/setup'
    ) {
      return msg;
    }

    const params = (msg.params ?? {}) as Record<string, unknown>;
    const repoUrl = params.repoUrl as string | undefined;
    if (!repoUrl) {
      ctx.sendToClient({
        id: msg.id,
        error: { code: -32602, message: 'Missing param: repoUrl' }
      });
      return null;
    }

    (async () => {
      try {
        await sandbox.exec(
          'find /workspace -mindepth 1 -delete 2>/dev/null; true'
        );
        const result = await sandbox.gitCheckout(repoUrl, {
          branch: params.branch as string | undefined,
          targetDir: '/workspace',
          depth: 1
        });
        ctx.sendToClient({ id: msg.id, result: { ok: true, ...result } });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        ctx.sendToClient({ id: msg.id, error: { code: -32000, message } });
      }
    })();

    return null;
  };
}

// --- Custom command: sandbox/exec ---

function sandboxExec(sandbox: ReturnType<typeof getSandbox>): MessageHandler {
  return (msg, ctx) => {
    if (
      ctx.direction !== 'client-to-server' ||
      !isRequest(msg) ||
      msg.method !== 'sandbox/exec'
    ) {
      return msg;
    }

    const params = (msg.params ?? {}) as Record<string, unknown>;
    const command = params.command as string | undefined;
    if (!command) {
      ctx.sendToClient({
        id: msg.id,
        error: { code: -32602, message: 'Missing param: command' }
      });
      return null;
    }

    sandbox
      .exec(command)
      .then((result) => ctx.sendToClient({ id: msg.id, result }))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err);
        ctx.sendToClient({ id: msg.id, error: { code: -32000, message } });
      });

    return null;
  };
}

// --- Sandbox lifecycle ---

async function ensureCodexRunning(
  sandbox: ReturnType<typeof getSandbox>
): Promise<string> {
  const procs = await sandbox.listProcesses();
  const existing = procs.find((p) => p.id === 'codex-app-server');
  if (
    existing &&
    (existing.status === 'running' || existing.status === 'starting')
  ) {
    const { stdout } = await sandbox.exec('cat /tmp/codex-ws-token');
    return stdout.trim();
  }

  const token = crypto.randomUUID();

  await sandbox.setEnvVars({
    OPENAI_BASE_URL: 'http://api.openai.com/v1',
    OPENAI_API_KEY: 'proxy-injected',
    ANTHROPIC_BASE_URL: 'http://api.anthropic.com'
  });

  await sandbox.exec(
    `printf '%s' '${token}' > /tmp/codex-ws-token && chmod 600 /tmp/codex-ws-token`
  );

  const proc = await sandbox.startProcess(
    'bash -lc "codex app-server --listen ws://0.0.0.0:4500 --ws-auth capability-token --ws-token-file /tmp/codex-ws-token"',
    { processId: 'codex-app-server' }
  );
  await proc.waitForPort(CODEX_WS_PORT, { mode: 'tcp' });

  return token;
}

async function prepareSandbox(
  sandbox: ReturnType<typeof getSandbox>,
  sandboxId: string,
  params: {
    repoUrl?: string;
    branch?: string;
    reset?: boolean;
    runtimeEnv?: Record<string, string>;
  } = {}
) {
  if (params.reset) await sandbox.destroy();

  await sandbox.setEnvVars({
    OPENAI_BASE_URL: 'http://api.openai.com/v1',
    OPENAI_API_KEY: 'proxy-injected',
    ANTHROPIC_BASE_URL: 'http://api.anthropic.com',
    ...params.runtimeEnv
  });

  await sandbox.exec(
    `printf '%s' '${sandboxId}' > /tmp/sandbox-session-name && chmod 644 /tmp/sandbox-session-name`
  );

  if (params.repoUrl) {
    await sandbox.exec(
      'find /workspace -mindepth 1 -delete 2>/dev/null; true'
    );
    const checkout = await sandbox.gitCheckout(params.repoUrl, {
      branch: params.branch,
      targetDir: '/workspace',
      depth: 1
    });
    return { ok: true, session: sandboxId, setup: checkout };
  }

  return { ok: true, session: sandboxId };
}

// --- Auth ---

function checkAuth(request: Request, url: URL, env: Env): Response | null {
  const token = env.AUTH_TOKEN;
  if (!token) return null;

  const header = request.headers.get('Authorization');
  if (header === `Bearer ${token}`) return null;

  if (url.searchParams.get('token') === token) return null;

  return new Response('Unauthorized', { status: 401 });
}

// --- Worker ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const proxied = await proxyToSandbox(request, env);
    if (proxied) return proxied;

    const url = new URL(request.url);
    const match = url.pathname.match(SANDBOX_ID_RE);
    if (match) return handleWebSocket(request, url, env, match[1]);

    const agentStart = url.pathname.match(AGENT_SANDBOX_START_RE);
    if (agentStart) return handleAgentSandboxStart(request, url, env, agentStart[1]);

    if (url.pathname !== '/') return env.Assets.fetch(request);

    const wsProto = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return new HTMLRewriter()
      .on('html', {
        element(el) {
          el.setAttribute('data-ws-endpoint', `${wsProto}//${url.host}/ws`);
        }
      })
      .transform(await env.Assets.fetch(request));
  }
};

async function handleAgentSandboxStart(
  request: Request,
  url: URL,
  env: Env,
  sandboxId: string
): Promise<Response> {
  const denied = checkAuth(request, url, env);
  if (denied) return denied;

  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', {
      status: 405,
      headers: { Allow: 'POST' }
    });
  }

  let params: {
    repoUrl?: string;
    branch?: string;
    reset?: boolean;
    runtimeEnv?: Record<string, string>;
  } = {};
  if (request.headers.get('content-type')?.includes('application/json')) {
    params = await request.json() as {
      repoUrl?: string;
      branch?: string;
      reset?: boolean;
      runtimeEnv?: Record<string, string>;
    };
  }

  const sleepAfter = env.SANDBOX_SLEEP_AFTER || '1h';
  const sandbox = getSandbox(env.Sandbox, `codex-${sandboxId}`, { sleepAfter });
  const result = await prepareSandbox(sandbox, sandboxId, params);

  return Response.json(result);
}

// --- WebSocket bridge ---

async function connectToContainer(
  sandbox: ReturnType<typeof getSandbox>,
  token: string
): Promise<WebSocket> {
  const wsRequest = switchPort(
    new Request('http://container/ws', {
      headers: {
        Upgrade: 'websocket',
        Connection: 'Upgrade',
        Authorization: `Bearer ${token}`
      }
    }),
    CODEX_WS_PORT
  );
  const ws = (await sandbox.fetch(wsRequest)).webSocket;
  if (!ws) throw new Error('Failed to connect to Codex container');
  return ws;
}

async function handleWebSocket(
  request: Request,
  url: URL,
  env: Env,
  sandboxId: string
): Promise<Response> {
  const denied = checkAuth(request, url, env);
  if (denied) return denied;

  if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
    return new Response('Expected WebSocket upgrade', { status: 426 });
  }

  const sleepAfter = env.SANDBOX_SLEEP_AFTER || '1m';
  const sandbox = getSandbox(env.Sandbox, `codex-${sandboxId}`, { sleepAfter });
  await sandbox.destroy();
  await prepareSandbox(sandbox, sandboxId);
  const token = await ensureCodexRunning(sandbox);

  const containerWs = await connectToContainer(sandbox, token);

  const [clientWs, serverWs] = Object.values(new WebSocketPair());
  const sendJson = (ws: WebSocket) => (msg: JsonRpcMessage) =>
    ws.send(JSON.stringify(msg));
  const toClient = sendJson(serverWs);
  const toServer = sendJson(containerWs);

  const clientToServerCtx: HandlerContext = {
    direction: 'client-to-server',
    sendToClient: toClient,
    sendToServer: toServer
  };
  const serverToClientCtx: HandlerContext = {
    direction: 'server-to-client',
    sendToClient: toClient,
    sendToServer: toServer
  };

  const pipeline = compose(
    log(),
    enforceModel('gpt-5.4'),
    enforcePolicy({
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'externalSandbox', networkAccess: 'restricted' }
    }),
    sandboxSetup(sandbox),
    sandboxExec(sandbox),
    autoApprove()
  );

  serverWs.accept();
  containerWs.accept();

  const bridge = (from: WebSocket, to: WebSocket, ctx: HandlerContext) => {
    from.addEventListener('message', (event) => {
      const raw = typeof event.data === 'string' ? event.data : '';
      const msg = tryParse(raw);
      if (!msg) {
        to.send(raw);
        return;
      }
      const result = pipeline(msg, ctx);
      if (!result) return;
      to.send(result === msg ? raw : JSON.stringify(result));
    });
  };

  bridge(serverWs, containerWs, clientToServerCtx);
  bridge(containerWs, serverWs, serverToClientCtx);

  const safeClose = (ws: WebSocket, code: number, reason: string) => {
    try {
      ws.close(code, reason);
    } catch {
      /* already closed */
    }
  };

  serverWs.addEventListener('close', (e: CloseEvent) =>
    safeClose(containerWs, e.code, e.reason)
  );
  containerWs.addEventListener('close', (e: CloseEvent) =>
    safeClose(serverWs, e.code, e.reason)
  );
  serverWs.addEventListener('error', () =>
    safeClose(containerWs, 1011, 'Client error')
  );
  containerWs.addEventListener('error', () =>
    safeClose(serverWs, 1011, 'Container error')
  );

  return new Response(null, { status: 101, webSocket: clientWs });
}
