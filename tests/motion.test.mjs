import { test } from "node:test";
import assert from "node:assert/strict";
import { createSequence, createLatestRequest } from "../static/js/crewcast.js";

function harness() {
  const tasks = new Map();
  const states = [];
  let clock = 0;
  let id = 0;
  const sequence = createSequence(
    3,
    (active, complete) => states.push({ active, complete }),
    () => {},
    (callback) => {
      tasks.set(++id, callback);
      return id;
    },
    (timer) => tasks.delete(timer),
    () => clock,
  );
  return {
    sequence,
    tasks,
    states,
    later: () => {
      clock += 2000;
    },
  };
}
test("rapid replay settles and cancels outstanding callbacks", () => {
  const h = harness();
  h.sequence.play();
  const staleCallbacks = [...h.tasks.values()];
  assert.equal(h.tasks.size, 3);
  h.sequence.play();
  assert.equal(h.tasks.size, 0);
  assert.deepEqual(h.states.at(-1), { active: null, complete: true });
  const count = h.states.length;
  staleCallbacks.forEach((callback) => callback());
  assert.equal(
    h.states.length,
    count,
    "cancelled generation cannot overwrite settled state",
  );
});
test("keyboard and reduced-motion requests immediately show completed explanation", () => {
  const h = harness();
  h.sequence.play(true);
  assert.equal(h.tasks.size, 0);
  assert.deepEqual(h.states, [{ active: null, complete: true }]);
});
test("a finished sequence can be replayed later and cancelled on page hide", () => {
  const h = harness();
  h.sequence.play();
  [...h.tasks.values()].forEach((callback) => callback());
  h.later();
  h.sequence.play();
  assert.deepEqual(h.states.at(-1), { active: 0, complete: false });
  h.sequence.finish();
  assert.equal(h.tasks.size, 0);
  assert.deepEqual(h.states.at(-1), { active: null, complete: true });
});

test('only the latest date response commits, even when the first response ignores abort', async () => {
  const pending = new Map();
  const committed = [];
  const busy = [];
  const load = createLatestRequest((url, signal) => new Promise((resolve, reject) => pending.set(url, {resolve, reject, signal})),
    (value, url) => committed.push([value, url]), () => assert.fail('No fallback expected'), value => busy.push(value));
  const first = load('Friday');
  const second = load('Saturday');
  assert.equal(pending.get('Friday').signal.aborted, true);
  pending.get('Saturday').resolve('Saturday jobs');
  await second;
  pending.get('Friday').resolve('Friday jobs');
  await first;
  assert.deepEqual(committed, [['Saturday jobs', 'Saturday']]);
  assert.deepEqual(busy, [true, true, false]);
});

test('date failure keeps current content and permits a later retry', async () => {
  const committed = [];
  const failed = [];
  let attempt = 0;
  const load = createLatestRequest(async () => {
    if (++attempt === 1) throw new Error('Offline');
    return 'Recovered jobs';
  }, value => committed.push(value), url => failed.push(url), () => {});
  await load('Sunday');
  assert.deepEqual(committed, []);
  assert.deepEqual(failed, ['Sunday']);
  await load('Sunday');
  assert.deepEqual(committed, ['Recovered jobs']);
});

test('returning to the rendered date cancels a pending Back response', async () => {
  let resolve;
  let signal;
  const commits = [];
  const busy = [];
  const load = createLatestRequest((url, requestSignal) => {
    signal = requestSignal;
    return new Promise(done => { resolve = done; });
  }, value => commits.push(value), () => assert.fail('Cancelled response must not fail'), value => busy.push(value));
  const back = load('previous date');
  load.cancel();
  assert.equal(signal.aborted, true);
  resolve('obsolete previous date');
  await back;
  assert.deepEqual(commits, []);
  assert.deepEqual(busy, [true, false]);
});
