/** A source being pasted is local work even before it joins the collection. */
export function hasPendingSource(source = {}) {
  return ['title', 'content', 'date', 'url'].some(key => Boolean(source[key]));
}

export const PENDING_SOURCE_MESSAGE = 'You have a source that has not been added. Choose Add this source, or Clear pending source, before saving, preparing or exporting the project. Your pasted text is still here.';
