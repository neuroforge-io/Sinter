/** Local counts only; a portal may segment words or count characters differently. */
export function campaignAnswerCounts(text = '') {
  // Count code points, including whitespace, without normalising the saved text.
  // A word here is a nonempty run between Unicode whitespace separators. This
  // deliberately does not attempt language-specific segmentation or validation.
  return {
    characters: [...text].length,
    words: (text.match(/[^\p{White_Space}\uFEFF]+/gu) || []).length,
  };
}
