// Placeholder for a pattern that has not been built yet (status "todo" in patterns/index.js).
// The shell never starts a timed trial on a stub: it shows the block's "not implemented" screen
// with a Skip block button instead, and skipped blocks are written to session_info.csv.
// This file only exists so the registry has something to point at; it is not mounted.

export function makeStub(id) {
  return {
    id,
    mount() { throw new Error(`Pattern ${id} is not implemented yet (see prototype/PATTERN_API.md)`); },
  };
}
