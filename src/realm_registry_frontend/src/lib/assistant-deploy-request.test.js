import assert from 'node:assert/strict';
import test from 'node:test';
import {
  formDataFromSpec,
  isExpired,
  parseAssistantRequestParam,
  readAssistantRequest,
  specFromFormData,
  specHash,
} from './assistant-deploy-request.js';

const ID = 'k3JrXz0aQ1m9Wv2nTt8bYp5dHc7LsEuA';

function rawRequest(overrides = {}) {
  return {
    id: ID,
    status: 'pending',
    client_name: 'Claude',
    delegate_principal: 'aaaaa-aa',
    note: 'You asked for a European realm.',
    expires_at: 1_900_000_000,
    cost_credits: 5,
    spec_hash: 'ab'.repeat(32),
    spec: {
      name: 'Riverside Commons',
      slug: 'riverside-commons',
      platform: { gos: 'realms-gos', version: 'latest' },
      subnet: { choice: 'european' },
      manifesto: 'We are the neighbours of the river.',
      welcome_message: 'Welcome to Riverside Commons!',
    },
    ...overrides,
  };
}

test('parseAssistantRequestParam: no parameter is the ordinary wizard', () => {
  assert.deepEqual(parseAssistantRequestParam(new URLSearchParams('step=2')), { active: false, id: '' });
});

test('parseAssistantRequestParam: a well-formed id', () => {
  assert.deepEqual(parseAssistantRequestParam(new URLSearchParams(`assistant_request=${ID}`)), {
    active: true,
    id: ID,
  });
});

test('parseAssistantRequestParam: a malformed id is active but empty, so the page says the link is not valid', () => {
  for (const bad of ['', 'short', 'has space in it, not an id!!', 'x'.repeat(31), 'x'.repeat(33), '../../etc']) {
    const params = new URLSearchParams({ assistant_request: bad });
    assert.deepEqual(parseAssistantRequestParam(params), { active: true, id: '' }, bad);
  }
});

test('readAssistantRequest keeps the fields the page uses', () => {
  const request = readAssistantRequest(rawRequest());

  assert.equal(request.id, ID);
  assert.equal(request.status, 'pending');
  assert.equal(request.clientName, 'Claude');
  assert.equal(request.delegatePrincipal, 'aaaaa-aa');
  assert.equal(request.note, 'You asked for a European realm.');
  assert.equal(request.expiresAt, 1_900_000_000);
  assert.equal(request.specHash, 'ab'.repeat(32));
  assert.deepEqual(request.spec.subnet, { choice: 'european' });
});

test('readAssistantRequest drops fields outside the six the assistant may set', () => {
  const raw = rawRequest();
  raw.spec.founder = 'attacker-principal';
  raw.spec.canister_ids = { backend: 'x' };
  raw.spec.deploy_mode = 'upgrade';
  raw.spec.platform.wasm_url = 'https://evil.example/x.wasm';
  raw.spec.subnet.extra = 1;

  const { spec } = readAssistantRequest(raw);

  assert.deepEqual(Object.keys(spec).sort(), ['manifesto', 'name', 'platform', 'slug', 'subnet', 'welcome_message']);
  assert.deepEqual(Object.keys(spec.platform).sort(), ['gos', 'version']);
  assert.deepEqual(spec.subnet, { choice: 'european' });
});

test('readAssistantRequest keeps the subnet id only for choice "other"', () => {
  const other = rawRequest();
  other.spec.subnet = { choice: 'other', subnet_id: 'abc12-xyz34' };
  assert.deepEqual(readAssistantRequest(other).spec.subnet, { choice: 'other', subnet_id: 'abc12-xyz34' });

  const european = rawRequest();
  european.spec.subnet = { choice: 'european', subnet_id: 'abc12-xyz34' };
  assert.deepEqual(readAssistantRequest(european).spec.subnet, { choice: 'european' });
});

test('readAssistantRequest caps what the assistant chose to show', () => {
  const request = readAssistantRequest(rawRequest({ client_name: 'N'.repeat(500), note: 'x'.repeat(5000) }));

  assert.equal(request.clientName.length, 64);
  assert.equal(request.note.length, 500);
});

test('readAssistantRequest has no note when the assistant sent none', () => {
  assert.equal(readAssistantRequest(rawRequest({ note: null })).note, '');
});

test('readAssistantRequest refuses a malformed reply', () => {
  const malformed = [
    null,
    {},
    rawRequest({ status: 'cancelled' }),
    rawRequest({ expires_at: 'soon' }),
    rawRequest({ spec: null }),
    rawRequest({ spec: { ...rawRequest().spec, name: 42 } }),
    rawRequest({ spec: { ...rawRequest().spec, subnet: { choice: 'moon' } } }),
    rawRequest({ spec: { ...rawRequest().spec, subnet: { choice: 'other' } } }),
  ];
  for (const raw of malformed) {
    assert.throws(() => readAssistantRequest(raw), /malformed/, JSON.stringify(raw)?.slice(0, 60));
  }
});

test('isExpired compares unix seconds with the clock', () => {
  assert.equal(isExpired(1000, 999_999), false);
  assert.equal(isExpired(1000, 1_000_000), true);
  assert.equal(isExpired(1000, 1_000_001), true);
});

test('formDataFromSpec fills the wizard form', () => {
  const { spec } = readAssistantRequest(rawRequest());

  assert.deepEqual(formDataFromSpec(spec, 'main'), {
    gos_implementation: 'realms-gos',
    name: 'Riverside Commons',
    slug: 'riverside-commons',
    deploy_version: 'main',
    subnet_choice: 'european',
    subnet_id: '',
    manifesto: 'We are the neighbours of the river.',
    welcome_message: 'Welcome to Riverside Commons!',
  });
});

test('formDataFromSpec: "latest" is the wizard default, a version loses its "v"', () => {
  const { spec } = readAssistantRequest(rawRequest());

  assert.equal(formDataFromSpec(spec, '0.7.0').deploy_version, '0.7.0');
  spec.platform.version = 'v0.5.1';
  assert.equal(formDataFromSpec(spec, 'main').deploy_version, '0.5.1');
  spec.platform.version = 'main';
  assert.equal(formDataFromSpec(spec, '0.7.0').deploy_version, 'main');
});

test('formDataFromSpec carries a chosen subnet id', () => {
  const raw = rawRequest();
  raw.spec.subnet = { choice: 'other', subnet_id: 'abc12-xyz34' };

  const form = formDataFromSpec(readAssistantRequest(raw).spec, 'main');

  assert.equal(form.subnet_choice, 'other');
  assert.equal(form.subnet_id, 'abc12-xyz34');
});

test('an untouched form is the original spec, whatever the version spelling', () => {
  for (const version of ['latest', 'main', '0.4.0']) {
    const raw = rawRequest();
    raw.spec.platform.version = version;
    const { spec } = readAssistantRequest(raw);

    const form = formDataFromSpec(spec, 'main');

    assert.deepEqual(specFromFormData(form, spec, 'main'), spec, version);
  }
});

test('specFromFormData shows what the user changed', () => {
  const { spec } = readAssistantRequest(rawRequest());
  const form = {
    ...formDataFromSpec(spec, 'main'),
    name: '  Riverside Co-op  ',
    slug: 'River Side',
    deploy_version: '0.4.0',
    subnet_choice: 'other',
    subnet_id: ' abc12-xyz34 ',
    manifesto: 'A new manifesto.',
  };

  assert.deepEqual(specFromFormData(form, spec, 'main'), {
    name: 'Riverside Co-op',
    slug: 'river-side',
    platform: { gos: 'realms-gos', version: '0.4.0' },
    subnet: { choice: 'other', subnet_id: 'abc12-xyz34' },
    manifesto: 'A new manifesto.',
    welcome_message: 'Welcome to Riverside Commons!',
  });
});

test('specFromFormData reports the default text for a box the user emptied', () => {
  const { spec } = readAssistantRequest(rawRequest());
  const form = { ...formDataFromSpec(spec, 'main'), manifesto: '   ', welcome_message: '' };

  const final = specFromFormData(form, spec, 'main');

  assert.equal(final.manifesto, 'Welcome to Riverside Commons.');
  assert.equal(final.welcome_message, 'Welcome to Riverside Commons!');
});

// Computed with Python: json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
// the way ggg-mcp hashes the original spec.
test('specHash matches the Python reference vectors', async () => {
  assert.equal(
    await specHash({
      name: 'Riverside Commons',
      slug: 'riverside-commons',
      platform: { gos: 'realms-gos', version: 'latest' },
      subnet: { choice: 'european' },
      manifesto: 'We are the neighbours of the river — «ñandú» 河',
      welcome_message: 'Welcome to Riverside Commons!',
    }),
    'b5f032aaafd00be3151fbc6e22dc10e4865075882268aeade04b6e0a9c3d0bd5',
  );
  assert.equal(
    await specHash({
      welcome_message: 'W',
      subnet: { subnet_id: 'abc12-xyz34', choice: 'other' },
      slug: 'pinned',
      platform: { version: '0.4.0', gos: 'realms-gos' },
      name: 'Pinned',
      manifesto: 'M',
    }),
    '9bd9d9a066f23c1761822dab59eee8ee6ec6978af63962b2eb6700bdca0caaf5',
  );
});

// The vector ggg-mcp's tests use: a newline, quotes, accents and an astral character.
test('specHash matches the ggg-mcp test vector', async () => {
  assert.equal(
    await specHash({
      name: 'Café',
      slug: 'cafe',
      platform: { gos: 'realms-gos', version: 'latest' },
      subnet: { choice: 'european' },
      manifesto: 'Línea 1\nLine "2" 🌍',
      welcome_message: '¡Hola!',
    }),
    'dd350fe946d4272f63eedaed9bd04f8f5f36740abbf680b6683f99333165ca16',
  );
});

test('specHash differs when the user changes a field', async () => {
  const { spec } = readAssistantRequest(rawRequest());
  const form = formDataFromSpec(spec, 'main');

  const before = await specHash(specFromFormData(form, spec, 'main'));
  const after = await specHash(specFromFormData({ ...form, welcome_message: 'Hello!' }, spec, 'main'));

  assert.notEqual(before, after);
});
