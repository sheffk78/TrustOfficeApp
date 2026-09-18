// Shared pagination helper for admin list tabs.
// Extracted from LeadsTab so the windowing logic is unit-testable.

// Returns the list of page entries to render: numbers plus 'ellipsis-left' /
// 'ellipsis-right' markers where the page range is collapsed.
// Windowed layout: always show page 1 and the last page; center a window of
// up to 3 pages around the current page, widened to 3 when near either edge.
export function getPaginationPages(currentPage, totalPages) {
  if (totalPages <= 0) return [];
  if (totalPages <= 6) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages = [];
  const push = (p) => { if (!pages.includes(p)) pages.push(p); };
  push(1);
  const winStart = Math.max(2, Math.min(currentPage - 1, totalPages - 2));
  const winEnd = Math.min(totalPages - 1, Math.max(currentPage + 1, 4));
  if (winStart > 2) pages.push('ellipsis-left');
  for (let p = winStart; p <= winEnd; p++) push(p);
  if (winEnd < totalPages - 1) pages.push('ellipsis-right');
  push(totalPages);
  return pages;
}