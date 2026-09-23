// Ada's public ElevenLabs agent id. Replace the placeholder, commit, redeploy.
//
// The id is public by design — the widget sends it from the browser. What keeps
// the demo from being abused is set in the ElevenLabs dashboard, not here:
//   - allowlist the deployed host, so only this site can start a conversation
//   - cap concurrent conversations and conversations per day
//   - cap the length of a single conversation
// Without those, anyone who views source can run up your conversation minutes.
window.ENTIN_AGENT_ID = 'agent_9901kjdn8xr0fees5bazpfnn1y18';
