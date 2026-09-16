import { describe, expect, it } from 'vitest';
import { historyFromUnknown, searchFlagsFromUnknown } from './api';

describe('searchFlagsFromUnknown', () => {
  it('reads camelCase and snake_case flags', () => {
    expect(searchFlagsFromUnknown({ regex: true, match_case: true, wholeWord: true })).toEqual({
      regex: true,
      matchCase: true,
      wholeWord: true,
    });
  });

  it('treats a boolean second arg as the regex flag', () => {
    expect(searchFlagsFromUnknown(true)).toEqual({ regex: true, matchCase: false, wholeWord: false });
    expect(searchFlagsFromUnknown(false)).toEqual({ regex: false, matchCase: false, wholeWord: false });
  });
});

describe('historyFromUnknown', () => {
  it('keeps flags from objects', () => {
    expect(
      historyFromUnknown([{ term: 'foo.*', regex: true, match_case: false, whole_word: true }]),
    ).toEqual([{ term: 'foo.*', regex: true, matchCase: false, wholeWord: true }]);
  });

  it('preserves previous flags when the server still returns strings', () => {
    const previous = [{ term: 'foo.*', regex: true, matchCase: false, wholeWord: false }];
    expect(historyFromUnknown(['foo.*', 'bar'], previous)).toEqual([
      { term: 'foo.*', regex: true, matchCase: false, wholeWord: false },
      { term: 'bar', regex: false, matchCase: false, wholeWord: false },
    ]);
  });
});
