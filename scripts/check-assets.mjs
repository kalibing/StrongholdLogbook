// 校验 assets.ts 里的每个图标路径都在 public 下真实存在，避免部署后出现空图标。
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const source = readFileSync(join(root, 'frontend/src/assets.ts'), 'utf8')
const paths = [...source.matchAll(/"(\/art\/[^"]+)"/g)].map(match => match[1])
const missing = paths.filter(path => !existsSync(join(root, 'frontend/public', path)))

if (missing.length) {
  console.error('缺少图标文件：\n' + missing.join('\n'))
  process.exit(1)
}

console.log(`assets.ts 校验通过：${paths.length} 个图标路径全部存在`)
