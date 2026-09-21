import { runLocalStack } from '../run-local-stack.mjs';

// Проверяем владение деревом даже для потомка, не реагирующего на выход CLI.
const probe = new URL('./lifecycle-owned-descendant.mjs', import.meta.url).href;
process.env.NODE_OPTIONS = `${process.env.NODE_OPTIONS ?? ''} --import=${probe}`;
const { api, next } = runLocalStack([]);
process.send({ api: api.pid, next: next.pid });
process.once('message', () => {
  process.disconnect();
  process.emit('SIGTERM');
});
