import { reactive } from 'vue';
import { errorMessage } from '../shared/api.js';
import { useAdminI18n } from '../shared/adminI18n.js';
const { tr } = useAdminI18n();
export const admin = reactive({
  user: null,
  ready: false,
  tab: 'access',
  toasts: [],
  confirm: null,
  fields: null,
  sessionUser: null,
});
let confirmation,
  fieldRequest,
  nextToast = 0;
export function notify(message, bad = false) {
  const id = ++nextToast;
  admin.toasts.push({ id, message, bad });
  admin.toasts = admin.toasts.slice(-3);
  setTimeout(() => {
    admin.toasts = admin.toasts.filter((t) => t.id !== id);
  }, 4500);
}
export async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    admin.user = null;
    settleConfirm(false);
    settleFields(null);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(errorMessage(data.detail, response.status, tr));
  }
  return response.status === 204 ? null : response.json();
}
export async function run(action) {
  try {
    return await action();
  } catch (error) {
    notify(error.message, true);
    return false;
  }
}
export function confirm(title, text) {
  settleConfirm(false);
  admin.confirm = { title, text };
  return new Promise((resolve) => {
    confirmation = resolve;
  });
}
export function settleConfirm(value) {
  const resolve = confirmation;
  confirmation = null;
  admin.confirm = null;
  resolve?.(value);
}
export function ask(title, fields) {
  settleFields(null);
  admin.fields = {
    title,
    fields,
    value: Object.fromEntries(fields.map((f) => [f.name, f.value ?? ''])),
  };
  return new Promise((resolve) => {
    fieldRequest = resolve;
  });
}
export function settleFields(value) {
  const resolve = fieldRequest;
  fieldRequest = null;
  admin.fields = null;
  resolve?.(value);
}
export function sessionsFor(user) {
  admin.sessionUser = user;
  admin.tab = 'sessions';
}
