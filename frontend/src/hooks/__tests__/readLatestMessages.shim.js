/**
 * Test shim: mirrors production readLatestMessages (useChatStream.js) so the
 * regression test can run without mounting the full hook. Keep in sync with
 * the production implementation.
 */
export function readLatestMessagesShim(setMessages) {
  return new Promise(resolve => {
    setMessages(prev => {
      resolve(prev);
      return prev; // pass-through: keep state intact, never return undefined
    });
  });
}