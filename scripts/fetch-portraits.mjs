// 补齐干员头像：从公开的明日方舟资源镜像下载 180×180 头像到 frontend/public/portraits。
// 用法：
//   node scripts/fetch-portraits.mjs char_002_amiya
//   node scripts/fetch-portraits.mjs --from online/dist/operators.json
//   node scripts/fetch-portraits.mjs --force char_002_amiya
// 可用 PORTRAIT_SOURCE 覆盖模板（默认 Aceship 的 Arknight-Images 镜像）。
import { mkdir, readFile, writeFile, access } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SOURCE = process.env.PORTRAIT_SOURCE
  ?? 'https://raw.githubusercontent.com/Aceship/Arknight-Images/main/avatars/{id}.png'
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const target = join(root, 'frontend/public/portraits')

const argv = process.argv.slice(2)
const force = argv.includes('--force')
const fromIndex = argv.indexOf('--from')
const fromFile = fromIndex >= 0 ? argv[fromIndex + 1] : null
const ids = new Set(argv.filter((arg, index) => {
  if (arg.startsWith('--')) return false
  return !(fromIndex >= 0 && index === fromIndex + 1)
}))

if (fromFile) {
  const data = JSON.parse(await readFile(join(root, fromFile), 'utf8'))
  const list = Array.isArray(data) ? data : Object.keys(data)
  for (const id of list) ids.add(typeof id === 'string' ? id : id.id)
}

if (!ids.size) {
  console.error('没有指定干员 ID。示例：node scripts/fetch-portraits.mjs char_002_amiya')
  process.exit(1)
}

const exists = async path => access(path).then(() => true, () => false)
await mkdir(target, { recursive: true })

let saved = 0
let skipped = 0
const failed = []
for (const id of ids) {
  const file = join(target, `${id}.png`)
  if (!force && await exists(file)) { skipped++; continue }
  const url = SOURCE.replace('{id}', id)
  const response = await fetch(url)
  if (!response.ok) { failed.push(`${id} (${response.status})`); continue }
  const buffer = Buffer.from(await response.arrayBuffer())
  if (buffer.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') { failed.push(`${id} (not png)`); continue }
  await writeFile(file, buffer)
  saved++
}

console.log(`新增 ${saved} 张，跳过 ${skipped} 张${failed.length ? `，失败 ${failed.length} 张：${failed.join('、')}` : ''}`)
if (failed.length) process.exitCode = 1
