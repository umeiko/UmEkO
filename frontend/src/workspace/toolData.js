// Tool history wraps text in JSON; live events may already contain decoded values.
// Unwrap strings without interpreting literal escape sequences in ordinary text.
export function prettyToolData(value, emptyText) {
  if (value === null || value === undefined || value === '') return emptyText;
  let decoded = value;
  if (typeof decoded === 'string') {
    try {
      decoded = JSON.parse(decoded);
    } catch {
      return decoded;
    }
    if (typeof decoded === 'string') {
      // Persisted parameters can contain a JSON string wrapping a JSON object.
      // Other decoded text stays text, including directory trees and Markdown.
      if (/^\s*[\[{]/.test(decoded)) {
        try {
          const structured = JSON.parse(decoded);
          if (structured !== null && typeof structured === 'object')
            return JSON.stringify(structured, null, 2);
        } catch {
          // An ordinary text result may start with a bracket.
        }
      }
      return decoded;
    }
  }
  return JSON.stringify(decoded, null, 2);
}
