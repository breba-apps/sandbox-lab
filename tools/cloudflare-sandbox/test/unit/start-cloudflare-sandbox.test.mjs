import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  containerEnvFor,
  ensureWorkerService,
  parseArgs,
  sandboxAgentArgs,
  serviceDownMessage,
  workerReady
} from '../../scripts/start-cloudflare-sandbox.mjs';

test('parseArgs supports session, reset, tty, and passthrough command', () => {
  const opts = parseArgs([
    '--name',
    'demo',
    '--worker-url',
    'http://127.0.0.1:9999',
    '--reset',
    '--no-tty',
    '--',
    'bash',
    '-lc',
    'pwd'
  ]);

  assert.equal(opts.session, 'demo');
  assert.equal(opts.workerUrl, 'http://127.0.0.1:9999');
  assert.equal(opts.reset, true);
  assert.equal(opts.tty, false);
  assert.deepEqual(opts.command, ['bash', '-lc', 'pwd']);
});

test('workerReady returns false when fetch fails and true for non-500 response', async () => {
  assert.equal(await workerReady('http://x', async () => ({ status: 200 })), true);
  assert.equal(await workerReady('http://x', async () => ({ status: 404 })), true);
  assert.equal(await workerReady('http://x', async () => ({ status: 500 })), false);
  assert.equal(await workerReady('http://x', async () => { throw new Error('down'); }), false);
});

test('containerEnvFor uses placeholders for Worker-side secrets only', () => {
  const env = containerEnvFor(
    {
      variables: [
        { name: 'OPENAI_API_KEY', mode: 'proxy_secret' },
        { name: 'R2_SECRET_ACCESS_KEY', mode: 'signing_secret' },
        { name: 'REQUEST_TIMEOUT_SECONDS', mode: 'runtime_env' }
      ]
    },
    { REQUEST_TIMEOUT_SECONDS: '30' },
    { OPENAI_API_KEY: 'real', R2_SECRET_ACCESS_KEY: 'real-r2' }
  );

  assert.deepEqual(env, {
    REQUEST_TIMEOUT_SECONDS: '30',
    OPENAI_API_KEY: 'proxy-injected',
    R2_SECRET_ACCESS_KEY: 'proxy-injected'
  });
});

test('sandboxAgentArgs passes runtime and container env through JSON env vars', () => {
  const result = sandboxAgentArgs(
    {
      session: 'demo',
      workerUrl: 'http://localhost:8787',
      reset: true,
      shell: false,
      tty: false,
      command: ['echo', 'ok']
    },
    { workspace: { repoUrl: 'https://github.com/org/repo.git', branch: 'main' } },
    { A: '1' },
    { A: '1', SECRET: 'proxy-injected' }
  );

  assert.deepEqual(result.args, [
    '--session',
    'demo',
    '--worker-url',
    'http://localhost:8787',
    '--repo',
    'https://github.com/org/repo.git',
    '--branch',
    'main',
    '--reset',
    '--no-tty',
    '--',
    'echo',
    'ok'
  ]);
  assert.equal(JSON.parse(result.env.SANDBOX_RUNTIME_ENV_JSON).A, '1');
  assert.equal(JSON.parse(result.env.SANDBOX_CONTAINER_ENV_JSON).SECRET, 'proxy-injected');
});

test('ensureWorkerService succeeds when service is ready', async () => {
  const result = await ensureWorkerService(
    { workerUrl: 'http://ready', service: true },
    { fetch: async () => ({ status: 200 }) }
  );

  assert.equal(result, undefined);
});

test('ensureWorkerService errors with service startup instructions when service is down', async () => {
  await assert.rejects(
    () => ensureWorkerService(
      { workerUrl: 'http://down' },
      {
        appDir: '/repo/app',
        fetch: async () => { throw new Error('down'); }
      }
    ),
    /cf-sandbox-service[\s\S]*cd \/repo\/app[\s\S]*start-cloudflare-sandbox/
  );
});

test('serviceDownMessage includes worker URL and exact commands', () => {
  const message = serviceDownMessage({ workerUrl: 'http://localhost:8787' }, '/repo/app');

  assert.match(message, /http:\/\/localhost:8787/);
  assert.match(message, /cf-sandbox-service/);
  assert.match(message, /cd \/repo\/app/);
  assert.match(message, /start-cloudflare-sandbox/);
});
