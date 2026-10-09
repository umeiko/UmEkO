export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {}
  const focused = document.activeElement;
  const input = document.createElement('textarea');
  input.value = text;
  input.style.cssText = 'position:fixed;left:-9999px;top:0';
  document.body.append(input);
  input.select();
  let copied;
  try {
    copied = document.execCommand('copy');
  } finally {
    input.remove();
    focused?.focus({ preventScroll: true });
  }
  if (!copied) throw new Error('Clipboard unavailable');
}
