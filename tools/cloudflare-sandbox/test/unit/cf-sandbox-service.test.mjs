import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';

import {
  parseArgs,
  run
} from '../../scripts/cf-sandbox-service.mjs';

test('parseArgs supports tool dir and help', () => {
  assert.equal(parseArgs(['--tool-dir', '/tool']).toolDir, '/tool');
  assert.equal(parseArgs(['--help']).help, true);
  assert.throws(() => parseArgs(['--unknown']), /Unknown argument/);
});

test('run starts npm run dev in the tool directory and returns child exit code', async () => {
  const child = new EventEmitter();
  const calls = [];
  const codePromise = run(['--tool-dir', '/tool'], {
    spawn(command, args, options) {
      calls.push({ command, args, options });
      queueMicrotask(() => child.emit('exit', 7, null));
      return child;
    }
  });

  assert.equal(await codePromise, 7);
  assert.equal(calls[0].command, 'npm');
  assert.deepEqual(calls[0].args, ['run', 'dev']);
  assert.equal(calls[0].options.cwd, '/tool');
});

test('run maps child signals to 128', async () => {
  const child = new EventEmitter();
  const codePromise = run([], {
    spawn() {
      queueMicrotask(() => child.emit('exit', null, 'SIGTERM'));
      return child;
    }
  });

  assert.equal(await codePromise, 128);
});
