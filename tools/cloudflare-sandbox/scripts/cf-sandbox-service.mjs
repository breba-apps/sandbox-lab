#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { realpathSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

import { TOOL_ROOT } from './lib/cloudflare-config.mjs';

function usage(stdout = console.log) {
  stdout(`Usage:
  cf-sandbox-service [options]

Options:
  --tool-dir <path>   Cloudflare tool directory. Default: ${TOOL_ROOT}
  -h, --help          Show this help.
`);
}

function parseArgs(argv) {
  const opts = { toolDir: TOOL_ROOT, help: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '-h' || arg === '--help') opts.help = true;
    else if (arg === '--tool-dir') opts.toolDir = requiredValue(argv, ++i, arg);
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return opts;
}

function requiredValue(argv, index, flag) {
  const value = argv[index];
  if (!value || value.startsWith('--')) throw new Error(`Missing value for ${flag}`);
  return value;
}

async function run(argv = process.argv.slice(2), deps = {}) {
  const opts = parseArgs(argv);
  if (opts.help) {
    usage(deps.stdout ?? console.log);
    return 0;
  }

  const spawnFn = deps.spawn ?? spawn;
  const child = spawnFn('npm', ['run', 'dev'], {
    cwd: opts.toolDir,
    stdio: 'inherit',
    env: process.env
  });

  return new Promise((resolve) => {
    child.on('exit', (code, signal) => {
      if (signal) resolve(128);
      else resolve(code ?? 1);
    });
  });
}

async function main(argv = process.argv.slice(2)) {
  try {
    const code = await run(argv);
    process.exit(code);
  } catch (err) {
    console.error(`cf-sandbox-service: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
}

export { parseArgs, run };

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main();
}
