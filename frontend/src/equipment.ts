import { EQUIPMENT_ICONS } from './assets'

// 规程 V3_1 原始棋子 ID 来自国服 activity_table (6f63c14e) 的 trapChessDataDict。
// 中文名核对自 Stronghold-Protocol 的 data/versions/act3autochess-v3_1/items.json。
// 同一装备的普通、进阶条目共享名称和图标。
const REGULATION_NAMES: Record<string, string> = {
  chess_item_1_01_e: "维式重锤",
  chess_item_1_02_e: "坚守盾牌",
  chess_item_1_03_e: "盟约之币",
  chess_item_1_04_e: "随身身份牌",
  chess_item_1_05_e: "源石溶剂",
  chess_item_1_06_e: "虹彩活血饮料",
  chess_item_1_07_e: "雪祀之衣",
  chess_item_2_01_e: "不屈弹射器",
  chess_item_2_02_e: "紧急调度券",
  chess_item_2_03_e: "战栗维式重锤",
  chess_item_2_04_e: "萨尔贡浓茶",
  chess_item_2_05_e: "精打细算玩偶",
  chess_item_2_06_e: "简易通讯机",
  chess_item_2_07_e: "见钱眼开玩偶",
  chess_item_2_08_e: "卫戍推荐信",
  chess_item_2_09_e: "聚合急救箱",
  chess_item_2_10_e: "灵巧涡轮手套",
  chess_item_3_01_e: "叙拉古正装",
  chess_item_3_02_e: "精准狙击镜",
  chess_item_3_03_e: "炎国短刀",
  chess_item_3_04_e: "迅捷作战粮",
  chess_item_3_05_e: "歌利亚头盔",
  chess_item_3_06_e: "阿戈尔重刃",
  chess_item_3_07_e: "奥术法阵",
  chess_item_3_08_e: "坚固维式重锤",
  chess_item_3_09_e: "加速维式重锤",
  chess_item_3_10_e: "突袭手雷",
  chess_item_3_11_e: "驮兽储蓄罐",
  chess_item_3_12_e: "乌萨斯呼吸器",
  chess_item_3_13_e: "多功能补剂",
  chess_item_3_14_e: "伊比利亚骨刺刀",
  chess_item_3_15_e: "定期存折",
  chess_item_3_16_e: "不退者之盾",
  chess_item_4_01_e: "寻呼模块",
  chess_item_4_02_e: "蜂鸣器",
  chess_item_4_03_e: "伪装服",
  chess_item_4_04_e: "卡西米尔竞技旗",
  chess_item_4_05_e: "灼燃维式重锤",
  chess_item_4_07_e: "护盾无人机",
  chess_item_4_08_e: "M3茧甲",
  chess_item_4_09_e: "莱塔尼亚小鼓",
  chess_item_4_10_e: "谢拉格不融冰",
  chess_item_4_11_e: "可靠怀表",
  chess_item_4_12_e: "驱逐者警棍",
  chess_item_4_13_e: "动能单手弩",
  chess_item_4_14_e: "汲取者之喙",
  chess_item_4_15_e: "一次性促销券",
  chess_item_5_01_e: "双模机械臂",
  chess_item_5_02_e: "信标",
  chess_item_5_03_e: "拟态物质",
  chess_item_5_04_e: "博士投影",
  chess_item_5_05_e: "天马之盔",
  chess_item_5_06_e: "投机骰子",
  chess_item_5_07_e: "电流维式重锤",
  chess_item_5_08_e: "佣兵名牌",
  chess_item_5_09_e: "人事部记录",
  chess_item_5_10_e: "瓶装烈性反应",
  chess_item_5_11_e: "不退者力场",
  chess_item_5_12_e: "驱逐者瓦斯",
  chess_item_6_01_e: "天马之枪",
  chess_item_6_02_e: "人事部文档",
  chess_item_6_03_e: "变形同构体",
  chess_item_6_05_e: "驱逐者防暴装备",
  chess_item_6_06_e: "不退者卫护系统",
  chess_item_6_07_e: "动能加速器",
  chess_item_6_08_e: "动能轰击弩",
  chess_item_6_09_e: "汲取者之心",
  chess_item_6_10_e: "汲取者之镰",
  chess_item_6_11_e: "终极维式重锤",
  chess_item_6_12_e: "天马之耀",
}

const equipmentAssets = new Map(Object.entries(EQUIPMENT_ICONS))
const equipmentId = /^(chess_item_\d+_\d+_e)_([ab])$/

export function resolveEquipment(value: string) {
  const match = equipmentId.exec(value)
  const mappedName = match && REGULATION_NAMES[match[1]]
  const name = mappedName || value
  return { name, icon: equipmentAssets.get(name), advanced: Boolean(mappedName && match?.[2] === 'b') }
}
