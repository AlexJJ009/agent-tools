import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runCodex } from '../.agents/skills/build-eval/shared/evals/report/codex-exec.mjs';

const mock = `#!/usr/bin/env node
const fs = require('node:fs');
const cp = require('node:child_process');
const args = process.argv.slice(2);
if (args[0] === 'login') {
  console.error(process.env.MOCK_MODE === 'api' ? 'Logged in using an API key' : 'Logged in using ChatGPT');
  process.exit(0);
}
let prompt = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => prompt += d);
process.stdin.on('end', () => {
  fs.writeFileSync(process.env.MOCK_CAPTURE, JSON.stringify({args, prompt, cwd: process.cwd(),
    keys: ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'].filter(k => k in process.env)}));
  const mode = process.env.MOCK_MODE;
  if (mode === 'hang') {
    const child = cp.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {stdio:'ignore'});
    fs.writeFileSync(process.env.MOCK_PID, String(child.pid));
    setInterval(() => {}, 1000); return;
  }
  if (mode === 'invalid') {console.log('not JSON'); return;}
  if (mode === 'failed') {console.log(JSON.stringify({type:'turn.failed',error:{message:'fixture error'}})); return;}
  console.log(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'fixture answer'}}));
  const event = {type:'turn.completed',usage:{input_tokens:100,cached_input_tokens:40,output_tokens:7}};
  if (mode === 'model') event.model = 'fixture-model';
  if (mode === 'wrong-model') event.model = 'other-model';
  if (mode === 'missing-usage') delete event.usage;
  console.log(JSON.stringify(event));
});
`;

async function fixture(mode, fn) {
  const dir = mkdtempSync(join(tmpdir(), 'codex-eval-test-'));
  const values = { PATH: `${dir}:${process.env.PATH}`, MOCK_MODE: mode,
    MOCK_CAPTURE: join(dir, 'capture.json'), MOCK_PID: join(dir, 'pid'),
    OPENAI_API_KEY: 'fixture-not-secret', CODEX_API_KEY: 'fixture-not-secret', OPENAI_BASE_URL: 'http://fixture.invalid' };
  const old = Object.fromEntries(Object.keys(values).map(k => [k, process.env[k]]));
  writeFileSync(join(dir, 'codex'), mock, {mode:0o755});
  Object.assign(process.env, values);
  try { await fn({dir, capture: values.MOCK_CAPTURE, pid: values.MOCK_PID}); }
  finally {
    for (const [k,v] of Object.entries(old)) v === undefined ? delete process.env[k] : process.env[k] = v;
    rmSync(dir, {recursive:true, force:true});
  }
}
const request = dir => ({prompt:'Literal $HOME and `echo no`\nfixture', cwd:dir, model:'fixture-model',timeoutMs:5000});

test('subscription adapter mock contracts', async t => {
  await t.test('requires ChatGPT auth and does not start exec with API auth', async () => fixture('api', async ({dir,capture}) => {
    await assert.rejects(runCodex(request(dir)), e => e.failure_class === 'auth');
    assert.equal(existsSync(capture), false);
  }));
  await t.test('stdin, explicit invocation flags, env cleaning, cache accounting and absent served identity', async () => fixture('ok', async ({dir,capture}) => {
    const run = await runCodex(request(dir));
    const c = JSON.parse(readFileSync(capture,'utf8'));
    assert.equal(c.prompt,request(dir).prompt); assert.equal(c.cwd,dir); assert.deepEqual(c.keys,[]);
    for (const flag of ['exec','--ignore-user-config','--ephemeral','--json','--sandbox','read-only','--model','fixture-model']) assert.ok(c.args.includes(flag),flag);
    assert.equal(c.args.at(-1),'-'); assert.ok(c.args.includes('model_provider="openai"'));
    assert.deepEqual(run.usage,{input_tokens:60,output_tokens:7,cache_read_input_tokens:40});
    assert.equal(run.model,undefined); assert.equal(run.meta.served_model_verified,false);
    assert.equal(run.meta.requested_model,'fixture-model'); assert.equal(run.output,'fixture answer');
    assert.equal(run.transcript[0].content,request(dir).prompt); assert.match(run.raw_events,/turn.completed/);
  }));
  await t.test('observed identity is retained', async () => fixture('model', async ({dir}) => {
    const run = await runCodex(request(dir)); assert.equal(run.model,'fixture-model'); assert.equal(run.meta.served_model_verified,true);
  }));
  for (const [mode,kind] of [['wrong-model','serving_substitution'],['invalid','cli_protocol'],['failed','cli_execution'],['missing-usage','cli_protocol']]) {
    await t.test(`${mode} rejects`, async () => fixture(mode, async ({dir}) => {
      await assert.rejects(runCodex(request(dir)), e => e.failure_class === kind);
    }));
  }
  await t.test('timeout kills spawned process group', {skip:process.platform !== 'linux'}, async () => fixture('hang', async ({dir,pid}) => {
    await assert.rejects(runCodex({...request(dir),timeoutMs:1000}), e => e.failure_class === 'timeout');
    assert.ok(existsSync(pid),'child fixture must have started');
    const childPid = readFileSync(pid,'utf8');
    // A killed orphan can remain a zombie briefly before init reaps it; it is no longer running.
    let state;
    try { state = readFileSync(`/proc/${childPid}/stat`,'utf8').split(' ')[2]; }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    assert.ok(state === undefined || state === 'Z',`descendant still live: ${state}`);
  }));
});
