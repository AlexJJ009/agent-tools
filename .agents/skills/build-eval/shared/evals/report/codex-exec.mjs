// Thin subscription CLI adapter. No SDK, API key, or configuration writes.
import { spawn } from 'node:child_process';

function failure(message, kind, extra = {}) {
  return Object.assign(new Error(message), { failure_class: kind, ...extra });
}

function invoke(args, { cwd, prompt = '', timeoutMs }) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    for (const key of ['OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL']) delete env[key];
    const child = spawn('codex', args, {
      cwd, env, detached: process.platform !== 'win32', stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '', stderr = '', bytes = 0, stopped;
    const terminate = reason => {
      if (stopped) return;
      stopped = reason;
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
      } else {
        try { process.kill(-child.pid, 'SIGKILL'); } catch (e) { if (e.code !== 'ESRCH') child.kill('SIGKILL'); }
      }
    };
    const timer = setTimeout(() => terminate('timeout'), timeoutMs);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', data => {
      bytes += Buffer.byteLength(data);
      if (bytes > 32 * 1024 * 1024) terminate('output_limit');
      else stdout += data;
    });
    child.stderr.on('data', data => { stderr = (stderr + data).slice(-8192); });
    child.on('error', e => { clearTimeout(timer); reject(failure(e.message, 'cli_launch')); });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      if (stopped) reject(failure(`Codex ${stopped}`, stopped, { raw_events: stdout, stderr }));
      else resolve({ code, signal, stdout, stderr });
    });
    child.stdin.on('error', () => {}); // an early CLI exit may close stdin
    child.stdin.end(prompt);
  });
}

/** Run one agent/judge in a prepared workspace using saved ChatGPT auth.
 * Deliberately leaves app fixtures, graders and case selection to the caller.
 */
export async function runCodex({ prompt, cwd, model, effort = 'medium',
  sandbox = 'read-only', timeoutMs = 120000, outputSchema } = {}) {
  if (typeof prompt !== 'string' || !prompt.trim() || typeof cwd !== 'string' || !cwd)
    throw failure('prompt and an explicit prepared cwd are required', 'input');
  if (!['read-only', 'workspace-write'].includes(sandbox))
    throw failure('sandbox must be read-only or workspace-write', 'input');
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 2147483647)
    throw failure('timeoutMs must be a positive timer-safe integer', 'input');
  if (model != null && (typeof model !== 'string' || !model.trim()))
    throw failure('model must be a nonempty string', 'input');
  if (!['minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'].includes(effort))
    throw failure('unsupported effort value', 'input');
  const started = Date.now();
  const auth = await invoke(['login', 'status'], { cwd, timeoutMs: Math.min(timeoutMs, 15000) });
  if (auth.code !== 0 || !/Logged in using ChatGPT/i.test(auth.stdout + auth.stderr))
    throw failure('Codex ChatGPT login is required; configuration was not changed', 'auth');
  const remaining = timeoutMs - (Date.now() - started);
  if (remaining <= 0) throw failure('Codex timeout during auth check', 'timeout');
  const args = ['exec', '--ignore-user-config', '-c', 'model_provider="openai"',
    '-c', `model_reasoning_effort=${JSON.stringify(effort)}`, '--ephemeral', '--json',
    '--sandbox', sandbox, '--skip-git-repo-check', '-C', cwd];
  if (model) args.push('--model', model);
  if (outputSchema) args.push('--output-schema', outputSchema);
  args.push('-');
  const proc = await invoke(args, { cwd, prompt, timeoutMs: remaining });
  let events;
  try { events = proc.stdout.split('\n').filter(s => s.trim()).map(s => JSON.parse(s)); }
  catch { throw failure('Invalid Codex JSONL', 'cli_protocol', { raw_events: proc.stdout }); }
  const completion = events.filter(e => e.type === 'turn.completed');
  const failed = events.some(e => e.type === 'turn.failed');
  if (proc.code !== 0 || failed || completion.length !== 1)
    throw failure(`Codex did not complete one turn (exit ${proc.code})`, 'cli_execution',
      { raw_events: proc.stdout, stderr: proc.stderr });
  const u = completion[0].usage;
  if (!u || !Number.isFinite(u.input_tokens) || !Number.isFinite(u.output_tokens))
    throw failure('Codex completion omitted token usage', 'cli_protocol', { raw_events: proc.stdout });
  const cached = u.cached_input_tokens;
  if (!Number.isFinite(cached) || cached < 0 || cached > u.input_tokens || u.output_tokens < 0)
    throw failure('Invalid Codex cached/token usage', 'cli_protocol', { raw_events: proc.stdout });
  const items = events.filter(e => e.type === 'item.completed').map(e => e.item);
  const messages = items.filter(i => i?.type === 'agent_message');
  if (!messages.length) throw failure('Codex omitted final answer', 'cli_protocol', { raw_events: proc.stdout });
  const observedModel = completion[0].model;
  if (observedModel && model && observedModel !== model)
    throw failure('Codex reported a different model', 'serving_substitution', { raw_events: proc.stdout });
  const transcript = [{ role: 'user', content: prompt }];
  for (const item of items) {
    if (item?.type === 'agent_message') transcript.push({ role: 'assistant', content: item.text });
    else transcript.push({ role: 'tool_result', name: item?.type ?? 'codex_item', content: JSON.stringify(item) });
  }
  return {
    output: messages.at(-1).text, transcript, raw_events: proc.stdout,
    model: observedModel, status: 'ok', stop_reason: 'turn.completed',
    usage: { input_tokens: u.input_tokens - cached, output_tokens: u.output_tokens,
      cache_read_input_tokens: cached,
      ...(Number.isFinite(u.cache_write_input_tokens) ? { cache_creation_input_tokens: u.cache_write_input_tokens } : {}) },
    meta: { requested_model: model ?? null, served_model_verified: !!observedModel,
      auth: 'chatgpt', transport: 'codex-exec', internal_retries: 'not_observable',
      subscription_cost_usd: null, remaining_quota: null },
  };
}
