import DOMPurify from "isomorphic-dompurify";

/** Strip HTML tags and return plain text safe for display. */
export function sanitizeToPlainText(html: string | null | undefined): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: [] });
}

/** Sanitize HTML for safe rendering (limited tags only). */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["p", "br", "b", "i", "em", "strong", "ul", "ol", "li"],
    ALLOWED_ATTR: [],
  });
}
