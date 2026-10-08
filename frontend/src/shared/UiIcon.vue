<script setup>
defineProps({ name: String, size: { default: 18 } });
const paths = {
  users:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  sessions:
    'M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z',
  providers:
    'M6 3v4 M18 3v4 M6 17v4 M18 17v4 M3 6h4 M17 6h4 M3 18h4 M17 18h4 M7 7h10v10H7Z M10 10h4v4h-4Z',
  skills: 'M4 3h6l2 2h8v16H4Z M8 10h8 M8 14h8 M8 18h4',
  resources: 'M3 12h4l3-8 4 16 3-8h4',
  access: 'M3 8h18 M7 4h10a4 4 0 0 1 4 4v12H3V8a4 4 0 0 1 4-4Z M8 12h8 M12 12v4',
  plus: 'M12 5v14 M5 12h14',
  close: 'M6 6l12 12 M6 18 18 6',
  chevron: 'm9 5 7 7-7 7',
  down: 'm6 9 6 6 6-6',
  logout: 'M9 21H4V3h5 M9 12h12 m-4-4 4 4-4 4',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 3 M18 18A8 8 0 0 1 5 15',
  save: 'M4 3h13l4 4v14H3V3Z M7 3v6h10V3 M7 21v-8h10v8',
  trash: 'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  edit: 'm16 3 5 5-13 13H3v-5Z M13 6l5 5',
  copy: 'M9 9h12v12H9Z M15 5V3H3v12h2',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  check: 'm5 12 4 4L19 6',
  warning: 'm12 3 10 18H2Z M12 9v5 M12 17h.01',
  folder: 'M3 5h6l2 2h10v13H3Z',
  file: 'M14 2H4v20h16V8Z M14 2v6h6',
  code: 'm8 6-6 6 6 6 M16 6l6 6-6 6',
  terminal: 'm4 5 7 7-7 7 M13 19h7',
  upload: 'M12 16V3 m-5 5 5-5 5 5 M3 16v5h18v-5',
  link: 'm10 13 4-4 M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0 M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
  shield: 'M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7Z m-4 9 3 3 5-5',
  menu: 'M3 6h18 M3 12h18 M3 18h18',
};
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.file" />
  </svg>
</template>
