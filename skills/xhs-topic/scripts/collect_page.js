/** Read-only DOM collector. Invoke through the supported browser tool's evaluate.
 * No fetch, API replay, cookies, storage, request headers, or page mutations.
 * Returned dates are display text only, never verified publication timestamps.
 */
function collectXhsPage(options = {}) {
  if (!/(^|\.)xiaohongshu\.com$/.test(location.hostname)) throw new Error('仅支持小红书网页');
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const now = new Date().toISOString();
  const limit = Math.max(1, Math.min(Number(options.limit) || 60, 200));
  const query = document.querySelector('#search-input')?.value || '';
  const seen = new Set();
  let discarded = 0;
  const notes = [];
  for (const el of document.querySelectorAll('section.note-item')) {
    const id = el.getAttribute('data-note-id') || el.querySelector('a[href*="/explore/"]')?.getAttribute('href')?.match(/\/explore\/([a-f0-9]{24})/)?.[1];
    const title = clean(el.querySelector('.title')?.textContent);
    if (!/^[a-f0-9]{24}$/.test(id || '') || !title) { discarded++; continue; }
    if (seen.has(id)) continue;
    seen.add(id);
    const authorPath = el.querySelector('a.author')?.getAttribute('href') || '';
    notes.push({note_id:id, title, author:clean(el.querySelector('.author .name')?.textContent), author_id:authorPath.match(/\/user\/profile\/([a-f0-9]{24})/)?.[1] || null,
      date_raw:clean(el.querySelector('.time')?.textContent), likes_raw:clean(el.querySelector('.like-wrapper .count')?.textContent),
      source:'https://www.xiaohongshu.com/explore/'+id, collected_at:now, created_at:null, created_at_verified:false,
      query:clean(query), sort:options.sort || '未核验排序', collection:'browser DOM'});
    if (notes.length >= limit) break;
  }
  const heading = document.querySelector('#detail-title');
  const detail = heading ? {title:clean(heading.textContent), visible_content:clean(document.querySelector('#detail-desc')?.textContent),
    visible_date:clean(document.querySelector('.note-content .date')?.textContent), created_at_verified:false,
    collected_at:now, note_id:location.pathname.match(/\/(?:explore|search_result)\/([a-f0-9]{24})/)?.[1] || null} : null;
  return {run_at:now, timezone:'Asia/Shanghai', window_hours:72, page_kind:detail?'note-detail':notes.length?'note-list':'unknown',
    page_path:location.origin+location.pathname, query:clean(query), notes, detail, discarded_non_note_cards:discarded,
    coverage:'仅当前DOM已加载卡片；不等于全站、搜索全量或已核实近三天发布时间'};
}
if (typeof module !== 'undefined') module.exports = {collectXhsPage};
