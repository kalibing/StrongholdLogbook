"""开局策略（band）对照表：band id → (分队干员, 策略名)。

由 frontend/src/bands.ts 生成，两边需同步修改。森空岛导入的记录里 strategy 字段存的是分队干员名，
生成战报图片时要换回策略名。
"""

BANDS = {
    "band_amedic": ("Touch", "外勤医疗"),
    "band_amiya": ("阿米娅", "众志合一"),
    "band_bond": ("贾维", "团伙行动"),
    "band_bonus": ("复奏", "二重奏"),
    "band_breakaway": ("Misery", "消解空间"),
    "band_cannot": ("坎诺特", "利滚利"),
    "band_clementia": ("克莱门莎", "崇高牺牲"),
    "band_closeout": ("拜松", "打包速递"),
    "band_copy": ("夕", "幻画为真"),
    "band_damaztic": ("“变形者集群”", "变形同构"),
    "band_dance": ("妮芙", "溃心领域"),
    "band_ducklord": ("鸭爵", "“神秘顾客”"),
    "band_egir": ("歌蕾蒂娅", "猎人战法"),
    "band_emperor": ("大帝", "加急调派"),
    "band_equipment": ("Mechanist", "精巧设计"),
    "band_evolve": ("大嘴莫布", "全场聚焦"),
    "band_fang": ("芬", "协力共进"),
    "band_fund": ("小贾斯汀", "私募基金"),
    "band_gain": ("铃兰", "御守之力"),
    "band_harold": ("哈洛德", "人才盲盒"),
    "band_high": ("渡桥", "专享情报"),
    "band_iberia": ("引星棘刺", "出航时刻"),
    "band_ioleta": ("伊奥莱塔·罗素", "统御号令"),
    "band_jenga": ("但书", "条文修正"),
    "band_jesica": ("杰西卡", "集结指示"),
    "band_kazimier": ("焰尾", "骑士团长"),
    "band_kjerag": ("休露丝", "雪域礼赠"),
    "band_kjerag2": ("耶拉", "不融信念"),
    "band_lethania": ("车尔尼", "流动乐章"),
    "band_limit": ("坚雷", "正直教官"),
    "band_lmlee": ("老鲤", "得闲饮茶"),
    "band_mech": ("森蚺", "暴躁铁皮"),
    "band_mess": ("昆图斯", "不稳定要素"),
    "band_mlynar": ("玛恩纳", "业务指标"),
    "band_pepe": ("佩佩", "博学多通"),
    "band_pith": ("Pith", "优等生"),
    "band_prepfin": ("苏苏洛", "强制休整"),
    "band_price": ("天空盒", "内部货源"),
    "band_protect": ("信仰搅拌机", "献身护卫"),
    "band_pudd": ("布丁", "电气化！"),
    "band_qalaisa": ("卡莱莎", "食腐之蝶"),
    "band_random": ("“追随者们”", "好多委托！"),
    "band_rich": ("琳琅诗怀雅", "最佳品味"),
    "band_sargon": ("娜仁图亚", "沙洲梦魇"),
    "band_sarkazb": ("歌利亚", "坚不可摧"),
    "band_sell": ("三船光平", "东之极道"),
    "band_shield": ("桑葚", "药枚实验"),
    "band_siracusa": ("裁度", "量体裁衣"),
    "band_smith": ("奥达", "全力熔铸"),
    "band_substitute": ("巫恋", "替身娃娃"),
    "band_support": ("雅拉", "人才锁定"),
    "band_survive": ("百炼嘉维尔", "意志鼓舞"),
    "band_takecare": ("华法琳", "重点监护"),
    "band_transfer": ("风丸", "纸片替身"),
    "band_treasure": ("寻宝人", "宝藏探机"),
    "band_upgrade": ("缪尔赛思", "至纯凝结"),
    "band_ursus": ("怒潮凛冬", "无惧风雪"),
    "band_victoria": ("洛洛", "自发制造"),
    "band_weakness": ("陈", "以己之长"),
    "band_yan": ("杜遥夜", "广交豪杰"),
    "band_yan2": ("望", "黑白相易"),
}

_BY_NAME = {}
for _band, (_unit, _strategy) in BANDS.items():
    _BY_NAME.setdefault(_strategy, _band)
    _BY_NAME.setdefault(_unit, _band)


def band_id(value):
    text = (value or "").strip()
    return text if text in BANDS else _BY_NAME.get(text)


def resolve(value):
    """记录里的 band id / 分队干员名 / 策略名 → (分队干员, 策略名)；对不上时原样返回。"""
    text = (value or "").strip()
    return BANDS.get(band_id(text), ("", text))
