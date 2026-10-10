// Real HTTP gateway: route public prefixes, strip once, reject unmatched root paths.
// Set UMEKO_TEST_NGINX to use an installed NGINX executable for the same workflows.
import { createServer, request as upstreamRequest } from 'node:http';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const execute = promisify(execFile);
export async function startProxy(directory, port, routes) {
  const nginx = process.env.UMEKO_TEST_NGINX;
  if (!nginx) {
    const server = createServer((request, response) => {
      const route = routes.find((r) => request.url.startsWith(r.prefix + '/'));
      if (!route) {
        response.writeHead(404).end('No public path rule matched');
        return;
      }
      const upstream = upstreamRequest(
        {
          host: '127.0.0.1',
          port: route.port,
          path: request.url.slice(route.prefix.length),
          method: request.method,
          headers: { ...request.headers, connection: 'close' },
        },
        (result) => {
          response.writeHead(result.statusCode, result.headers);
          result.pipe(response);
        },
      );
      upstream.on('error', () => {
        if (!response.headersSent) response.writeHead(502);
        response.end();
      });
      response.on('close', () => upstream.destroy());
      request.pipe(upstream);
    });
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(port, '127.0.0.1', resolve);
    });
    return async () => {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
    };
  }
  const folder = path.join(directory, 'nginx');
  await mkdir(folder);
  await mkdir(path.join(folder, 'logs'));
  await mkdir(path.join(folder, 'temp'));
  const quote = (value) => '"' + value.replaceAll('\\', '/').replaceAll('"', '\\"') + '"';
  const config = `worker_processes 1;
daemon off;
pid ${quote(path.join(folder, 'nginx.pid'))};
error_log ${quote(path.join(folder, 'error.log'))};
events { worker_connections 128; }
http {
  access_log off;
  client_max_body_size 64m;
  client_body_temp_path ${quote(path.join(folder, 'body'))};
  proxy_temp_path ${quote(path.join(folder, 'proxy'))};
  fastcgi_temp_path ${quote(path.join(folder, 'fastcgi'))};
  uwsgi_temp_path ${quote(path.join(folder, 'uwsgi'))};
  scgi_temp_path ${quote(path.join(folder, 'scgi'))};
  server {
    listen 127.0.0.1:${port};
    ${routes
      .map(
        (r) => `location ${r.prefix}/ {
      proxy_pass http://127.0.0.1:${r.port}/;
      proxy_http_version 1.1;
      proxy_set_header Host $http_host;
      proxy_set_header Connection "";
      proxy_buffering off;
      proxy_read_timeout 60s;
    }`,
      )
      .join('\n')}
    location / { return 404; }
  }
}`;
  await writeFile(path.join(folder, 'proxy.conf'), config);
  const args = ['-p', folder.replaceAll('\\', '/') + '/', '-c', 'proxy.conf'];
  await execute(nginx, [...args, '-t'], { windowsHide: true });
  const child = spawn(nginx, args, { windowsHide: true, stdio: 'ignore' });
  const exited = new Promise((resolve) => child.once('exit', resolve));
  return async () => {
    if (child.exitCode !== null) return;
    await execute(nginx, [...args, '-s', 'quit'], { windowsHide: true });
    let timeout;
    try {
      await Promise.race([
        exited,
        new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error('NGINX shutdown timed out')), 5000);
        }),
      ]);
    } finally {
      clearTimeout(timeout);
    }
  };
}
