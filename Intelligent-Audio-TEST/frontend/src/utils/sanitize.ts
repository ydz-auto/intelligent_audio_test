const HTML_ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
  '/': '&#x2F;',
  '`': '&#x60;',
  '=': '&#x3D;'
};

const HTML_ENTITY_REGEX = /[&<>"'`=/]/g;

export function escapeHtml(str: string): string {
  if (!str) return '';
  return String(str).replace(HTML_ENTITY_REGEX, (char) => HTML_ENTITIES[char] || char);
}

export function sanitizeHtml(html: string, allowedTags: string[] = []): string {
  if (!html) return '';
  
  if (allowedTags.length === 0) {
    return escapeHtml(html);
  }
  
  const allowedTagsSet = new Set(allowedTags.map(t => t.toLowerCase()));
  const tagPattern = /<\/?([a-zA-Z][a-zA-Z0-9]*)[^>]*>/g;
  
  let result = html.replace(tagPattern, (match, tagName) => {
    if (allowedTagsSet.has(tagName.toLowerCase())) {
      return match.replace(/on\w+\s*=\s*["'][^"']*["']/gi, '');
    }
    return '';
  });
  
  result = result.replace(/javascript:/gi, '');
  result = result.replace(/data:/gi, '');
  result = result.replace(/vbscript:/gi, '');
  
  return result;
}

export function stripHtml(html: string): string {
  if (!html) return '';
  return html.replace(/<[^>]*>/g, '');
}

export function sanitizeForVHtml(content: string): string {
  if (!content) return '';
  
  const allowedTags = ['b', 'i', 'u', 'strong', 'em', 'br', 'p', 'span', 'div', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'];
  
  let sanitized = sanitizeHtml(content, allowedTags);
  
  sanitized = sanitized.replace(/<(\w+)([^>]*)on\w+=[^>]*>/gi, '<$1$2>');
  
  return sanitized;
}

export function createSafeVHtml(content: string | undefined | null): string {
  if (!content) return '';
  return sanitizeForVHtml(String(content));
}

export function sanitizeConclusion(conclusion: string | undefined | null): string {
  return createSafeVHtml(conclusion);
}
