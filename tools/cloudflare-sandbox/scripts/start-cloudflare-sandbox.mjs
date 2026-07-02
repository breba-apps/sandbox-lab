#!/usr/bin/env node

import process from 'node:process';
import { realpathSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

import { runCli } from './sandbox-agent.mjs';
import {
  TOOL_ROOT,
  loadOptionalManifest,
  proxyEntriesFromFiles,
  runtimeEntriesFromFiles
} from './lib/cloudflare-config.mjs';

const DEFAULT_WORKER_URL = 'http://localhost:8787';

function usage(stdout = console.log) {
  stdout(`Usage:
  start-cloudflare-sandbox [options] [-- command ...]

Options:
  --name, --session <name>  Sandbox session name. Default: current directory name.
  --worker-url <url>        Worker URL. Default: ${DEFAULT_WORKER_URL}
  --tool-dir <path>         Cloudflare tool directory. Default: ${TOOL_ROOT}
  --reset                   Destroy and recreate the sandbox before attaching.
  --shell                   Run bash instead of the default agent command.
  --no-tty                  Use non-interactive docker exec.
  -h, --help                Show this help.
`);
}

function parseArgs(argv) {
  const opts = {
    session: null,
    workerUrl: DEFAULT_WORKER_URL,
    toolDir: TOOL_ROOT,
    reset: false,
    shell: false,
    tty: true,
    command: []
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--') {
      opts.command = argv.slice(i + 1);
      break;
    }
    if (arg === '-h' || arg === '--help') opts.help = true;
    else if (arg === '--name' || arg === '--session') opts.session = requiredValue(argv, ++i, arg);
    else if (arg === '--worker-url') opts.workerUrl = requiredValue(argv, ++i, arg);
    else if (arg === '--tool-dir') opts.toolDir = requiredValue(argv, ++i, arg);
    else if (arg === '--reset') opts.reset = true;
    else if (arg === '--shell') opts.shell = true;
    else if (arg === '--no-tty') opts.tty = false;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return opts;
}

function requiredValue(argv, index, flag) {
  const value = argv[index];
  if (!value || value.startsWith('--')) throw new Error(`Missing value for ${flag}`);
  return value;
}

async function workerReady(workerUrl, fetchFn = fetch) {
  try {
    const response = await fetchFn(workerUrl);
    return response.status < 500;
  } catch {
    return false;
  }
}

function serviceDownMessage(opts, appDir = process.cwd()) {
  return `Cloudflare sandbox service is not running at ${opts.workerUrl}.

Start it in another terminal:

  cf-sandbox-service

Then rerun from the app directory:

  cd ${appDir}
  start-cloudflare-sandbox`;
}

async function ensureWorkerService(opts, deps = {}) {
  const fetchFn = deps.fetch ?? fetch;
  if (await workerReady(opts.workerUrl, fetchFn)) {
    return;
  }
  throw new Error(serviceDownMessage(opts, deps.appDir));
}

function containerEnvFor(manifest, runtimeEnv, proxyEnv) {
  const env = { ...runtimeEnv };
  for (const variable of manifest.variables ?? []) {
    if (variable.mode === 'proxy_secret' || variable.mode === 'signing_secret') {
      if (proxyEnv[variable.name] !== undefined) env[variable.name] = 'proxy-injected';
    }
  }
  return env;
}

function sandboxAgentArgs(opts, manifest, runtimeEnv, containerEnv) {
  const args = [];
  if (opts.session) args.push('--session', opts.session);
  args.push('--worker-url', opts.workerUrl);
  if (manifest.workspace?.repoUrl) args.push('--repo', manifest.workspace.repoUrl);
  if (manifest.workspace?.branch) args.push('--branch', manifest.workspace.branch);
  if (opts.reset) args.push('--reset');
  if (opts.shell) args.push('--shell');
  if (!opts.tty) args.push('--no-tty');
  args.push('--');
  if (opts.command.length) args.push(...opts.command);

  return {
    args,
    env: {
      ...process.env,
      SANDBOX_RUNTIME_ENV_JSON: JSON.stringify(runtimeEnv),
      SANDBOX_CONTAINER_ENV_JSON: JSON.stringify(containerEnv)
    }
  };
}

async function run(argv = process.argv.slice(2), deps = {}) {
  const opts = parseArgs(argv);
  if (opts.help) {
    usage(deps.stdout ?? console.log);
    return 0;
  }

  const appDir = process.cwd();
  const manifest = loadOptionalManifest(`${appDir}/cloudflare-sandbox.toml`);
  if (!manifest) {
    throw new Error('cloudflare-sandbox.toml not found. Run setup-cloudflare-sandbox from the app directory first.');
  }

  const runtimeEnv = runtimeEntriesFromFiles(appDir);
  const proxyEnv = proxyEntriesFromFiles(appDir);
  const containerEnv = containerEnvFor(manifest, runtimeEnv, proxyEnv);
  await ensureWorkerService(opts, { ...deps, appDir });
  const { args, env } = sandboxAgentArgs(opts, manifest, runtimeEnv, containerEnv);
  return await runCli(args, { env, cwd: appDir });
}

async function main(argv = process.argv.slice(2)) {
  try {
    const code = await run(argv);
    process.exit(code);
  } catch (err) {
    console.error(`start-cloudflare-sandbox: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
}

export {
  containerEnvFor,
  ensureWorkerService,
  parseArgs,
  run,
  sandboxAgentArgs,
  serviceDownMessage,
  workerReady
};

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main();
}
