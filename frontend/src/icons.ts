import { ref } from 'vue'
import { BOND_ICONS } from './assets'

/** 图标加载完成时自增，图表据此重绘。 */
export const iconVersion = ref(0)
const cache = new Map<string, HTMLImageElement | null>()

export function bondIcon(name: string): HTMLImageElement | null {
  if (cache.has(name)) return cache.get(name) ?? null
  const path = BOND_ICONS[name]
  if (!path) {
    cache.set(name, null)
    return null
  }
  const image = new Image()
  image.src = path
  image.onload = () => { iconVersion.value++ }
  cache.set(name, image)
  return image
}

export const portrait = (id: string) => '/portraits/' + id + '.png'
