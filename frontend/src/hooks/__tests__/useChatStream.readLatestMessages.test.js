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
 * The fix: the updater resolves AND returns prev (pass-through). The production
 * function is module-scope in useChatStream.js and exported for this test.
 */
import { readLatestMessages } from '../useChatStream';

describe('readLatestMessages — state pass-through (err_41422d53fd3a regression)', () => {
  test('updater resolves with current state AND returns it — never poisons state to undefined', async () => {
    let state = [{ id: 'm1', content: 'hello' }];
    const setMessages = jest.fn(updater => {
      state = updater(state); // React semantics: new state = updater's return value
    });

    const resolved = await readLatestMessages(setMessages);

    expect(resolved).toEqual([{ id: 'm1', content: 'hello' }]); // promise resolves with the array
    expect(state).toEqual([{ id: 'm1', content: 'hello' }]);    // state UNCHANGED — not undefined
    // Any subsequent .map updater still works — the crash that hit prod cannot recur:
    expect(state.map(m => m.id)).toEqual(['m1']);
  });

  test('documents pre-fix behavior: bare resolve() would replace state with undefined', () => {
    // Pre-fix updater shape: prev => resolve(prev) — resolve() returns undefined,
    // so React stored undefined as the messages state.
    const resolve = jest.fn();
    const poisonedState = resolve(); // undefined
    expect(poisonedState).toBeUndefined();
  });
});