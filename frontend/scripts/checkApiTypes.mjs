import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(frontend, '..');
const scratch = mkdtempSync(join(tmpdir(), 'huginn-openapi-'));
function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (result.error || result.status !== 0)
    throw new Error(`${command} failed. Install the locked prerequisites.`);
}
try {
  const schema = join(scratch, 'openapi.json');
  const types = join(scratch, 'schema.d.ts');
  run(
    'uv',
    ['run', '--frozen', 'python', 'scripts/export-management-openapi.py', '--output', schema],
    root,
  );
  run(
    process.execPath,
    [join(frontend, 'node_modules/openapi-typescript/bin/cli.js'), schema, '-o', types],
    frontend,
  );
  for (const [actual, committed] of [
    [schema, join(frontend, 'src/api/generated/openapi.json')],
    [types, join(frontend, 'src/api/generated/schema.d.ts')],
  ]) {
    if (!readFileSync(actual).equals(readFileSync(committed)))
      throw new Error(
        'API schema/types drifted. Run npm run api:generate and review both outputs.',
      );
  }
  console.log('API schema and transport types match.');
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
