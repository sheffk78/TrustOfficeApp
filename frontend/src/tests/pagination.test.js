import { getPaginationPages } from '../pages/admin/pagination';

// Helper layout: always [1, …, window around current, …, last] once the list
// is long enough to collapse; all pages shown when ≤ 6 total.
describe('getPaginationPages', () => {
  it('shows all pages when totalPages <= 6', () => {
    expect(getPaginationPages(1, 1)).toEqual([1]);
    expect(getPaginationPages(2, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(getPaginationPages(6, 6)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('shows window around current page with edges collapsed when totalPages > 6', () => {
    // 10 pages, on page 1: window widened to 3 (2,3,4), right edge collapsed
    expect(getPaginationPages(1, 10)).toEqual([1, 2, 3, 4, 'ellipsis-right', 10]);
    // middle page: 1, window (n-1, n, n+1), last
    expect(getPaginationPages(5, 10)).toEqual([1, 'ellipsis-left', 4, 5, 6, 'ellipsis-right', 10]);
    // near the end: window (8,9), left edge collapsed
    expect(getPaginationPages(9, 10)).toEqual([1, 'ellipsis-left', 8, 9, 10]);
    // page 7 of 10: window (6,7,8)
    expect(getPaginationPages(7, 10)).toEqual([1, 'ellipsis-left', 6, 7, 8, 'ellipsis-right', 10]);
  });

  it('never omits page 1 or the last page', () => {
    for (let total = 7; total <= 12; total++) {
      for (let cur = 1; cur <= total; cur++) {
        const pages = getPaginationPages(cur, total);
        expect(pages[0]).toBe(1);
        expect(pages[pages.length - 1]).toBe(total);
        expect(pages).toContain(cur);
      }
    }
  });

  it('current page always renders as a clickable number (never an ellipsis)', () => {
    for (let total = 7; total <= 12; total++) {
      for (let cur = 1; cur <= total; cur++) {
        const pages = getPaginationPages(cur, total);
        expect(typeof pages.find((p) => p === cur)).toBe('number');
      }
    }
  });
});