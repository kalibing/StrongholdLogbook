// 由 online/dist 的旧版资源生成，改资源请同步此文件。
export const BOND_ICONS: Record<string, string> = {
  "不屈": "/art/bond-indomShip.png",
  "乌萨斯": "/art/bond-ursusShip.png",
  "伊比利亚": "/art/bond-iberiaShip.png",
  "助力": "/art/bond-deputShip.png",
  "协防干员": "/art/bond-emptyShip.png",
  "卡西米尔": "/art/bond-kazimierzShip.png",
  "叙拉古": "/art/bond-siracusaShip.png",
  "坚守": "/art/bond-steadShip.png",
  "奇迹": "/art/bond-miraShip.png",
  "奥术": "/art/bond-arcaneShip.png",
  "投资人": "/art/bond-investShip.png",
  "灵巧": "/art/bond-skillfulShip.png",
  "炎": "/art/bond-yanShip.png",
  "独行": "/art/bond-soloShip.png",
  "突袭": "/art/bond-raidShip.png",
  "精准": "/art/bond-preciShip.png",
  "绝技": "/art/bond-suntShip.png",
  "维多利亚": "/art/bond-victoriaShip.png",
  "聚合": "/art/bond-docShip.png",
  "莱塔尼亚": "/art/bond-lethaniaShip.png",
  "萨尔贡": "/art/bond-sargonShip.png",
  "调和": "/art/bond-maniShip.png",
  "谢拉格": "/art/bond-kjeragShip.png",
  "迅捷": "/art/bond-swiftShip.png",
  "远见": "/art/bond-visiShip.png",
  "阿戈尔": "/art/bond-egirShip.png",
}

export const BOSS_MARKS = {
  normal: "/art/boss-mark.png",
  hidden: "/art/hidden-boss-mark.png",
}

export const TROPHY_ICONS: Record<string, string> = {
  trophy_level1_icon: "/art/trophy_level1_icon.png",
  trophy_level2_icon: "/art/trophy_level2_icon.png",
  trophy_level3_icon: "/art/trophy_level3_icon.png",
  trophy_level4_icon: "/art/trophy_level4_icon.png",
  trophy_level5_icon: "/art/trophy_level5_icon.png",
  trophy_level6_icon: "/art/trophy_level6_icon.png",
  trophy_level7_icon: "/art/trophy_level7_icon.png",
  trophy_level8_icon: "/art/trophy_level8_icon.png",
}

// PRTS 文件「图标 卫戍协议资金.png」。
export const FUNDS_ICON = "/art/metric-funds.png"
// 卫戍协议战斗 HUD 的 icon_battle。
export const ROUND_ICON = "/art/metric-rounds.png"
// 卫戍协议叠加特质与战斗 HUD 的原始标记。
export const BOND_METRIC_ICON = "/art/metric-bond.png"
export const KILLS_ICON = "/art/metric-kills.png"

export const BOSS_ICONS: Record<string, string> = {
  "“萨米的意志”": "/art/boss-boss_7.png",
  "假想敌：械": "/art/boss-boss_11.png",
  "假想敌：械（隐藏）": "/art/boss-boss_14.png",
  "假想敌：管": "/art/boss-boss_3.png",
  "假想敌：管（隐藏）": "/art/boss-boss_10.png",
  "假想敌：胄": "/art/boss-boss_1.png",
  "假想敌：胄（隐藏）": "/art/boss-boss_8.png",
  "假想敌：茧": "/art/boss-boss_12.png",
  "假想敌：茧（隐藏）": "/art/boss-boss_15.png",
  "假想敌：铳": "/art/boss-boss_2.png",
  "假想敌：铳（隐藏）": "/art/boss-boss_9.png",
  "假想敌：鳍": "/art/boss-boss_13.png",
  "假想敌：鳍（隐藏）": "/art/boss-boss_16.png",
  "盐风主教昆图斯": "/art/boss-boss_4.png",
  "矩兽": "/art/boss-boss_17.png",
  "阿利斯泰尔，帝国余晖": "/art/boss-boss_6.png",
}

const bossNamesById = new Map(Object.entries(BOSS_ICONS).map(([name, icon]) => [
  icon.slice('/art/boss-'.length, -'.png'.length), name,
]))
export const bossName = (id: string) => bossNamesById.get(id) ?? id

export const STRATEGY_ICONS: Record<string, string> = {
  "“神秘顾客”": "/art/strategy-band_ducklord.png",
  "不稳定要素": "/art/strategy-band_mess.png",
  "不融信念": "/art/strategy-band_kjerag2.png",
  "二重奏": "/art/strategy-band_bonus.png",
  "人才盲盒": "/art/strategy-band_harold.png",
  "人才锁定": "/art/strategy-band_support.png",
  "众志合一": "/art/strategy-band_amiya.png",
  "优等生": "/art/strategy-band_pith.png",
  "内部货源": "/art/strategy-band_price.png",
  "出航时刻": "/art/strategy-band_iberia.png",
  "利滚利": "/art/strategy-band_cannot.png",
  "加急调派": "/art/strategy-band_emperor.png",
  "协力共进": "/art/strategy-band_fang.png",
  "变形同构": "/art/strategy-band_damaztic.png",
  "坚不可摧": "/art/strategy-band_sarkazb.png",
  "好多委托！": "/art/strategy-band_random.png",
  "崇高牺牲": "/art/strategy-band_clementia.png",
  "幻画为真": "/art/strategy-band_copy.png",
  "广交豪杰": "/art/strategy-band_yan.png",
  "强制休整": "/art/strategy-band_prepfin.png",
  "得闲饮茶": "/art/strategy-band_lmlee.png",
  "御守之力": "/art/strategy-band_gain.png",
  "打包速递": "/art/strategy-band_closeout.png",
  "无惧风雪": "/art/strategy-band_ursus.png",
  "暴躁铁皮": "/art/strategy-band_mech.png",
  "最佳品味": "/art/strategy-band_rich.png",
  "猎人战法": "/art/strategy-band_egir.png",
  "献身护卫": "/art/strategy-band_protect.png",
  "私募基金": "/art/strategy-band_fund.png",
  "精巧设计": "/art/strategy-band_equipment.png",
  "纸片替身": "/art/strategy-band_transfer.png",
  "统御号令": "/art/strategy-band_ioleta.png",
  "量体裁衣": "/art/strategy-band_siracusa.png",
  "集结指示": "/art/strategy-band_jesica.png",
  "黑白相易": "/art/strategy-band_yan2.png",
}

export const EQUIPMENT_ICONS: Record<string, string> = {
  "M3茧甲": "/art/equip-trap_1068_acarm068.png",
  "一次性促销券": "/art/equip-trap_1130_acarm130.png",
  "不屈弹射器": "/art/equip-trap_1056_acarm056.png",
  "不退者之盾": "/art/equip-trap_1146_acarm146.png",
  "不退者力场": "/art/equip-trap_1147_acarm147.png",
  "不退者卫护系统": "/art/equip-trap_1148_acarm148.png",
  "乌萨斯呼吸器": "/art/equip-trap_1138_acarm138.png",
  "人事部文档": "/art/equip-trap_1070_acarm070.png",
  "人事部记录": "/art/equip-trap_1142_acarm142.png",
  "伊比利亚骨刺刀": "/art/equip-trap_1133_acarm133.png",
  "伪装服": "/art/equip-trap_1055_acarm055.png",
  "佣兵名牌": "/art/equip-trap_1141_acarm141.png",
  "信标": "/art/equip-trap_1109_acarm109.png",
  "加速维式重锤": "/art/equip-trap_1044_acarm044.png",
  "动能加速器": "/art/equip-trap_1149_acarm149.png",
  "动能单手弩": "/art/equip-trap_1150_acarm150.png",
  "动能轰击弩": "/art/equip-trap_1151_acarm151.png",
  "博士投影": "/art/equip-trap_1071_acarm071.png",
  "卡西米尔竞技旗": "/art/equip-trap_1119_acarm119.png",
  "卫戍推荐信": "/art/equip-trap_1128_acarm128.png",
  "双模机械臂": "/art/equip-trap_1067_acarm067.png",
  "变形同构体": "/art/equip-trap_1073_acarm073.png",
  "叙拉古正装": "/art/equip-trap_1121_acarm121.png",
  "可靠怀表": "/art/equip-trap_1137_acarm137.png",
  "坚固维式重锤": "/art/equip-trap_1043_acarm043.png",
  "坚守盾牌": "/art/equip-trap_1047_acarm047.png",
  "多功能补剂": "/art/equip-trap_1131_acarm131.png",
  "天马之枪": "/art/equip-trap_1117_acarm117.png",
  "天马之盔": "/art/equip-trap_1118_acarm118.png",
  "天马之耀": "/art/equip-trap_1156_acarm156.png",
  "奥术法阵": "/art/equip-trap_1048_acarm048.png",
  "定期存折": "/art/equip-trap_1129_acarm129.png",
  "寻呼模块": "/art/equip-trap_1075_acarm075.png",
  "战栗维式重锤": "/art/equip-trap_1045_acarm045.png",
  "投机骰子": "/art/equip-trap_1139_acarm139.png",
  "护盾无人机": "/art/equip-trap_1061_acarm061.png",
  "拟态物质": "/art/equip-trap_1069_acarm069.png",
  "歌利亚头盔": "/art/equip-trap_1049_acarm049.png",
  "汲取者之喙": "/art/equip-trap_1152_acarm152.png",
  "汲取者之心": "/art/equip-trap_1153_acarm153.png",
  "汲取者之镰": "/art/equip-trap_1154_acarm154.png",
  "源石溶剂": "/art/equip-trap_1125_acarm125.png",
  "灵巧涡轮手套": "/art/equip-trap_1132_acarm132.png",
  "灼燃维式重锤": "/art/equip-trap_1042_acarm042.png",
  "炎国短刀": "/art/equip-trap_1040_acarm040.png",
  "瓶装烈性反应": "/art/equip-trap_1158_acarm158.png",
  "电流维式重锤": "/art/equip-trap_1140_acarm140.png",
  "盟约之币": "/art/equip-trap_1066_acarm066.png",
  "突袭手雷": "/art/equip-trap_1064_acarm064.png",
  "简易通讯机": "/art/equip-trap_1114_acarm114.png",
  "精准狙击镜": "/art/equip-trap_1063_acarm063.png",
  "精打细算玩偶": "/art/equip-trap_1113_acarm113.png",
  "紧急调度券": "/art/equip-trap_1115_acarm115.png",
  "终极维式重锤": "/art/equip-trap_1155_acarm155.png",
  "维式重锤": "/art/equip-trap_1041_acarm041.png",
  "聚合急救箱": "/art/equip-trap_1136_acarm136.png",
  "莱塔尼亚小鼓": "/art/equip-trap_1134_acarm134.png",
  "萨尔贡浓茶": "/art/equip-trap_1050_acarm050.png",
  "虹彩活血饮料": "/art/equip-trap_1126_acarm126.png",
  "蜂鸣器": "/art/equip-trap_1054_acarm054.png",
  "见钱眼开玩偶": "/art/equip-trap_1116_acarm116.png",
  "谢拉格不融冰": "/art/equip-trap_1062_acarm062.png",
  "迅捷作战粮": "/art/equip-trap_1051_acarm051.png",
  "阿戈尔重刃": "/art/equip-trap_1046_acarm046.png",
  "随身身份牌": "/art/equip-trap_1124_acarm124.png",
  "雪祀之衣": "/art/equip-trap_1127_acarm127.png",
  "驮兽储蓄罐": "/art/equip-trap_1157_acarm157.png",
  "驱逐者瓦斯": "/art/equip-trap_1143_acarm143.png",
  "驱逐者警棍": "/art/equip-trap_1144_acarm144.png",
  "驱逐者防暴装备": "/art/equip-trap_1145_acarm145.png",
}

export const DIFFICULTY_ICONS: Record<string, string> = {
  "极速模拟": "/art/tier-fast.png",
  "标准模拟": "/art/tier-standard.png",
  "险境模拟": "/art/tier-normal.png",
  "绝境模拟": "/art/tier-hard.png",
  "终极模拟": "/art/tier-abyss.png",
}

/**
 * 难度图标。独立模拟的「规程等级 N」复用联合模拟的档位图标，分档按 PRTS「卫戍协议·规程」的交叉开放规则：
 * 解锁规程等级 9 时开放【险境模拟】，解锁规程等级 15 时开放【绝境模拟】。
 * 所以 1–8 用标准、9–14 用险境、15–20 用绝境；极速模拟单独一个图标。
 */
export function difficultyIcon(label: string): string | undefined {
  if (DIFFICULTY_ICONS[label]) return DIFFICULTY_ICONS[label]
  const level = /^规程等级\s*(\d+)$/.exec(label.trim())
  if (!level) return undefined
  const value = Number(level[1])
  if (value >= 15) return DIFFICULTY_ICONS['绝境模拟']
  if (value >= 9) return DIFFICULTY_ICONS['险境模拟']
  return DIFFICULTY_ICONS['标准模拟']
}

// 从 PC 端 AB 包原生拆出的白色 glyph（ui/autochess/[uc]autochesscommon.ab: mode_*_icon），
// UI 里可用 CSS filter / mask 换色。
export const MODE_ICONS: Record<string, string> = {
  "极速模拟": "/art/mode-fast.png",
  "标准模拟": "/art/mode-fast.png",
  "险境模拟": "/art/mode-normal.png",
  "绝境模拟": "/art/mode-hard.png",
  "终极模拟": "/art/mode-abyss.png",
  "趣味模拟": "/art/mode-funny.png",
  "教学模拟": "/art/mode-training.png",
}

export const ELITE_ICONS = {
  elite2: "/art/elite-2.png",
  elite1: "/art/elite-1.png",
}
