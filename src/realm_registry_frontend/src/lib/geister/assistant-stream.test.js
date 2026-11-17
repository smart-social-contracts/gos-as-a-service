import assert from 'node:assert/strict';
import test from 'node:test';

import { readAssistantStream } from './assistant-stream.js';

/** A stream reader that hands out `bytes` in the reads given by `cuts` (byte offsets). */
function readerOf(bytes, cuts = []) {
  const ends = [...cuts, bytes.length];
  let start = 0;
  return {
    async read() {
      if (!ends.length) return { done: true, value: undefined };
      const end = ends.shift();
      const value = bytes.slice(start, end);
      start = end;
      return { done: false, value };
    },
  };
}

const encode = (text) => new TextEncoder().encode(text);

// What ggg-ai sends: Python's json.dumps, so `": "` and `", "` with a space. The third event is the one a reader saw
// verbatim in an answer on staging (17 Nov 2026) when a read ended inside it.
const STREAM = [
  'data: {"type": "status", "text": "Reading the realm"}',
  'data: {"type": "text", "text": "The realm shows no proposals or votes yet"}',
  'data: {"type": "text", "text": ".\\n\\n"}',
  'data: {"type": "thinking", "text": "plan the list"}',
  ': keep-alive',
  'data: {"type": "text", "text": "Would you like help? — sí"}',
  'data: [DONE]',
  '',
].join('\n');
const ANSWER = 'The realm shows no proposals or votes yet.\n\nWould you like help? — sí';

test('reads the answer of a stream that arrives in one piece', async () => {
  assert.equal(await readAssistantStream(readerOf(encode(STREAM))), ANSWER);
});

test('an event cut in two by the network is read once, as text, wherever the cut falls', async () => {
  const bytes = encode(STREAM);
  for (let cut = 1; cut < bytes.length; cut += 1) {
    const answer = await readAssistantStream(readerOf(bytes, [cut]));
    assert.equal(answer, ANSWER, `cut at byte ${cut}`);
  }
});

test('a stream read one byte at a time gives the same answer', async () => {
  const bytes = encode(STREAM);
  const cuts = Array.from({ length: bytes.length - 1 }, (_, i) => i + 1);
  assert.equal(await readAssistantStream(readerOf(bytes, cuts)), ANSWER);
});

test('what the assistant says it is doing is never part of the answer', async () => {
  const statuses = [];
  const answer = await readAssistantStream(readerOf(encode(STREAM)), { onStatus: (s) => statuses.push(s) });
  assert.deepEqual(statuses, ['Reading the realm']);
  assert.ok(!answer.includes('Reading the realm'));
  assert.ok(!answer.includes('plan the list'), 'thinking is not the answer either');
});

test('onText gets the whole answer so far, each time it grows', async () => {
  const seen = [];
  await readAssistantStream(readerOf(encode(STREAM)), { onText: (t) => seen.push(t) });
  assert.deepEqual(seen, [
    'The realm shows no proposals or votes yet',
    'The realm shows no proposals or votes yet.\n\n',
    ANSWER,
  ]);
});

test('a backend that streams plain text is still read, including a last line with no newline', async () => {
  const answer = await readAssistantStream(readerOf(encode('Hello\ndata: not json\nbye'), [3, 9]));
  assert.equal(answer, 'Hellonot jsonbye');
});

test('an event that is JSON but not an object adds nothing and does not stop the stream', async () => {
  const answer = await readAssistantStream(readerOf(encode('data: null\ndata: "x"\ndata: {"text": "ok"}\n')));
  assert.equal(answer, 'ok');
});
