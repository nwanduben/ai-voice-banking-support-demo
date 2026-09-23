// ElevenLabs signs each post-call webhook: header "elevenlabs-signature: t=<unix>,v0=<hex HMAC-SHA256 of `${t}.${rawBody}`>".
// This node rebuilds the exact signed text; the next (Crypto) node computes the HMAC with your ElevenLabs secret.
const item = $input.first();
const header = (item.json.headers || {})['elevenlabs-signature'] || '';
const parts = Object.fromEntries(header.split(',').map((p) => p.split('=')));
const raw = item.binary && item.binary.data ? Buffer.from(item.binary.data.data, 'base64').toString('utf8') : JSON.stringify(item.json.body || {});
return [{ json: { t: parts.t || '', v0: parts.v0 || '', signed_payload: `${parts.t}.${raw}`, raw } }];
