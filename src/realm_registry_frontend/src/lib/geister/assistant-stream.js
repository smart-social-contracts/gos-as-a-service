/**
 * The assistant's answer, read from ggg-ai's event stream: one `data: {"type": …, "text": …}` line per event.
 *
 * A network read can end anywhere, also in the middle of a line. A line is therefore only read once its end has
 * arrived: read early, the first half of an event is not JSON and the second half does not start with `data: `, so
 * both used to be taken for answer text, and the reader saw the event itself (`{"type": "text", "text": "…"}`).
 *
 * `onStatus(status)` gets what the assistant says it is doing; it is never part of the answer.
 * `onText(answer)` gets the whole answer so far, each time it grows. The answer is also what the promise resolves to.
 */
export async function readAssistantStream(reader, { onStatus = () => {}, onText = () => {} } = {}) {
  const decoder = new TextDecoder();
  let answer = '';
  let partial = '';

  function readLine(line) {
    const piece = answerPiece(line, onStatus);
    if (!piece) return;
    answer += piece;
    onText(answer);
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const lines = (partial + decoder.decode(value, { stream: true })).split('\n');
    partial = lines.pop();
    lines.forEach(readLine);
  }
  readLine(partial + decoder.decode());
  return answer;
}

/** What one whole line of the stream adds to the answer: '' for anything that is not answer text. */
function answerPiece(line, onStatus) {
  if (!line.startsWith('data: ')) {
    // A backend that streams plain text sends lines of its own; `:` starts an SSE comment (a keep-alive).
    return line.trim() && !line.startsWith(':') ? line : '';
  }
  const payload = line.slice(6);
  if (payload === '[DONE]') return '';
  let event;
  try {
    event = JSON.parse(payload);
  } catch {
    return payload; // a whole line that is not JSON is plain text
  }
  const type = typeof event?.type === 'string' ? event.type : event?.text ? 'text' : '';
  const text = typeof event?.text === 'string' ? event.text : '';
  if (type === 'status') {
    if (text) onStatus(text);
    return '';
  }
  return type === 'thinking' ? '' : text;
}
