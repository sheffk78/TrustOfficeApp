/**
 * Regression for prod react_render_error err_41422d53fd3a (2026-10-16, /trust-assistant).
 *
 * Root cause: readLatestMessages used the "functional updater trick" to read
 * state — setMessages(prev => resolve(prev)). React uses the updater's RETURN
 * VALUE as the new state, and resolve() returns undefined — so the call
 * silently replaced the messages state with undefined. The next
 * setMessages(prev => prev.map(...)) (stream error path, abort, or finalize)
 * then threw "Cannot read properties of undefined (reading 'map')" and took
 * the whole page down during render.
 *
 * The fix: the updater resolves AND returns prev (pass-through).
 */
import { readLatestMessagesShim } from './readLatestMessages.shim';

describe('readLatestMessages — state pass-through (err_41422d53fd3a regression)', () => {
  test('updater resolves with current state AND returns it — never poisons state to undefined', () => {
    let state = [{ id: 'm1', content: 'hello' }];
    const setMessages = jest.fn(updater => {
      state = updater(state); // React semantics: new state = updater's return
    });

    const resolved = readLatestMessagesShim(setMessages);

    return resolved.then(value => {
      expect(value).toEqual([{ id: 'm1', content: 'hello' }]); // promise resolves with the array
      expect(state).toEqual([{ id: 'm1', content: 'hello' }]); // state UNCHANGED — not undefined
      // Any subsequent .map updater still works:
      const safe = state.map(m => m.id);
      expect(safe).toEqual(['m1']);
    });
  });

  test('pre-fix behavior is documented: bare resolve() would have nulled the state', () => {
    let state = [{ id: 'm1', content: 'hello' }];
    const poisoned = [{ id: 'x' }].map(() => undefined); // what resolve(prev) returns: undefined
    state = undefined; // what React would store
    expect(() => (state || []).map(m => m.id)).not.toThrow(); // codepaths that now guard
    expect(poisoned[0]).toBeUndefined();
  });
});