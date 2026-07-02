#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { createInterface } from 'node:readline/promises';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

import {
  TOOL_ROOT,
  appendGeneratedFilesToGitignore,
  loadEnvFile,
  loadOptionalManifest,
  mergeDecision,
  derivedWorkerVars,
  writeDevVars,
  writeGeneratedFiles
} from './lib/cloudflare-config.mjs';

function usage(stdout = console.log) {
  stdout(`Usage:
  setup-cloudflare-sandbox [options]

Options:
  --env-file <path>      Env file to read. Default: .env
  --tool-dir <path>      Cloudflare tool directory. Default: ${TOOL_ROOT}
  --dry-run              Print actions without writing files.
  -h, --help             Show this help.
`);
}

function parseArgs(argv) {
  const opts = {
    envFile: '.env',
    toolDir: TOOL_ROOT,
    dryRun: false,
    help: false
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '-h' || arg === '--help') opts.help = true;
    else if (arg === '--dry-run') opts.dryRun = true;
    else if (arg === '--env-file') opts.envFile = requiredValue(argv, ++i, arg);
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

function inferRepoUrl() {
  try {
    return execFileSync('git', ['config', '--get', 'remote.origin.url'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore']
    }).trim();
  } catch {
    return '';
  }
}

async function confirmDecisions(envValues, existingManifest, deps = {}) {
  const input = deps.input ?? process.stdin;
  const output = deps.output ?? process.stdout;
  const rl = deps.readline ?? createInterface({ input, output });
  const existingByName = new Map(
    (existingManifest?.variables ?? []).map((variable) => [variable.name, variable])
  );
  const decisions = [];

  for (const name of envValues.keys()) {
    const decision = mergeDecision(name, existingByName.get(name));
    output.write(`\n${name}: ${decision.mode}`);
    if (decision.provider) output.write(` (${decision.provider})`);
    if (decision.service) output.write(` (${decision.service})`);
    output.write('\n');
    const answer = await rl.question('Use this Cloudflare handling? [Y/n]: ');
    if (!answer || ['y', 'yes'].includes(answer.toLowerCase())) {
      decisions.push(decision);
      continue;
    }
    output.write('  r) runtime env visible to container\n');
    output.write('  p) proxy secret injected by Worker\n');
    output.write('  g) signing secret used by Worker egress signer\n');
    output.write('  k) skip\n');
    const mode = (await rl.question('Choose [r]: ')).toLowerCase() || 'r';
    if (mode === 'k') continue;
    if (mode === 'p') {
      const provider = await rl.question('Provider name, e.g. openai: ');
      const host = await rl.question('Egress host, e.g. api.openai.com: ');
      decisions.push({
        name,
        mode: 'proxy_secret',
        provider: provider || undefined,
        host: host || undefined,
        networkUrl: host ? `${host}:443` : undefined
      });
      continue;
    }
    if (mode === 'g') {
      const service = await rl.question('Signing service, e.g. r2: ');
      decisions.push({ name, mode: 'signing_secret', service: service || undefined });
      continue;
    }
    decisions.push({ name, mode: 'runtime_env' });
  }

  if (!deps.readline) rl.close();
  return decisions;
}

async function run(argv = process.argv.slice(2), deps = {}) {
  const opts = parseArgs(argv);
  if (opts.help) {
    usage(deps.stdout ?? console.log);
    return 0;
  }

  const appDir = process.cwd();
  const envValues = loadEnvFile(opts.envFile);
  if (!envValues.size) throw new Error(`${opts.envFile} contains no variables`);

  const existingManifest = loadOptionalManifest(`${appDir}/cloudflare-sandbox.toml`);
  if (existingManifest) {
    console.log(`Reusing Cloudflare decisions for ${existingManifest.variables.length} variable(s).`);
  }

  const variables = await confirmDecisions(envValues, existingManifest, deps);
  const manifest = {
    workspace: {
      appPath: '.',
      repoUrl: existingManifest?.workspace?.repoUrl || inferRepoUrl()
    },
    variables
  };

  console.log(appendGeneratedFilesToGitignore(appDir, { dryRun: opts.dryRun }));
  for (const message of writeGeneratedFiles(appDir, manifest, envValues, { dryRun: opts.dryRun })) {
    console.log(message);
  }

  const workerSecretEntries = variables
    .filter((variable) => variable.mode === 'proxy_secret' || variable.mode === 'signing_secret')
    .map((variable) => [variable.name, envValues.get(variable.name) ?? '']);
  console.log(writeDevVars(opts.toolDir, [
    ...workerSecretEntries,
    ...derivedWorkerVars(manifest, envValues)
  ], { dryRun: opts.dryRun }));
  return 0;
}

async function main(argv = process.argv.slice(2), deps = {}) {
  try {
    const code = await run(argv, deps);
    process.exit(code);
  } catch (err) {
    console.error(`setup-cloudflare-sandbox: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
}

export { confirmDecisions, parseArgs, run };

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main();
}
