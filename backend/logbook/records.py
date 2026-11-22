from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, TypeAdapter, field_validator, model_validator

CHINA = timezone(timedelta(hours=8))
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
Stat = Annotated[int, Field(ge=0, le=2_147_483_647)]
SignedStat = Annotated[int, Field(ge=-2_147_483_648, le=2_147_483_647)]


class Bond(BaseModel):
    name: Label
    layers: Stat


class Operator(BaseModel):
    id: Label
    name: Label


class Unit(Operator):
    items: list[Label] = Field(default_factory=list, max_length=40)


class MatchInput(BaseModel):
    external_id: Label
    played_at: datetime
    protocol: Label = "V3_1"
    play: Label
    difficulty: Label
    result: Literal["win", "loss"]
    strategy: Label | None = None
    initiator: Label | None = None
    scenario: Label | None = None
    rounds: Stat | None = None
    kills: Stat | None = None
    coins: Stat | None = None
    sync_count: Stat | None = None
    trophies: SignedStat | None = None
    duration_seconds: Stat | None = None
    suspected_exit: bool | None = None
    bonds: list[Bond] = Field(default_factory=list, max_length=100)
    operators: list[Operator] = Field(default_factory=list, max_length=150)
    squad: list[Unit] = Field(default_factory=list, max_length=150)
    bosses: list[Label] = Field(default_factory=list, max_length=50)

    @field_validator("played_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("played_at 必须包含时区")
        return value

    @model_validator(mode="after")
    def defaults_from_match(self):
        if self.suspected_exit is None:
            self.suspected_exit = self.rounds == self.kills == self.coins == 0
        if not self.operators:
            self.operators = [Operator(id=unit.id, name=unit.name) for unit in self.squad]
        self.operators = list({operator.id: operator for operator in self.operators}.values())
        return self


MatchList = TypeAdapter(Annotated[list[MatchInput], Field(min_length=1, max_length=5000)])


def read_snapshot(payload: object) -> list[MatchInput]:
    operators, equipment = {}, {}
    if isinstance(payload, dict):
        operators = payload.get("operators", {})
        equipment = payload.get("equipment", {})
        payload = payload.get("matches")
    if not isinstance(payload, list) or not 1 <= len(payload) <= 5000:
        raise ValueError("请选择包含 1–5000 局战绩的 JSON")
    if not isinstance(operators, dict) or not isinstance(equipment, dict):
        raise ValueError("干员和装备字典格式无效")

    def dictionary_name(dictionary, key, fallback):
        entry = dictionary.get(key)
        return (entry.get("name") or fallback) if isinstance(entry, dict) else fallback

    def legacy(row):
        played_at = datetime.fromisoformat(row["时间"]).replace(tzinfo=CHINA)
        keys = (played_at.isoformat(), row["方式"], row["模式"])
        external_id = "archive-" + sha256("|".join(keys).encode()).hexdigest()
        squad = [
            {"id": unit_id, "name": name, "items": [
                dictionary_name(equipment, item, item) for item in items
            ]}
            for unit_id, name, items in row.get("阵容", [])
        ]
        known_names = {unit["id"]: unit["name"] for unit in squad}
        return {
            "external_id": external_id, "played_at": played_at,
            "play": row["方式"], "difficulty": row["模式"],
            "result": {"胜": "win", "负": "loss"}[row["结果"]],
            "scenario": row.get("分队") or None, "strategy": row.get("策略") or None,
            "initiator": row.get("发起者") or None,
            "rounds": row.get("回合"), "kills": row.get("击杀"), "coins": row.get("金币"),
            "sync_count": row.get("同步"), "trophies": row.get("奖杯增益"),
            "duration_seconds": row.get("时长"), "suspected_exit": row.get("疑似退出"),
            "bonds": [{"name": bond[0], "layers": bond[1]} for bond in row.get("盟约", [])],
            "operators": [
                {"id": item, "name": dictionary_name(operators, item, known_names.get(item, item))}
                for item in row.get("干员", [])
            ],
            "squad": squad, "bosses": row.get("首领", []),
        }

    try:
        rows = MatchList.validate_python([
            legacy(row) if isinstance(row, dict) and "时间" in row else row for row in payload
        ])
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ValueError("战绩 JSON 的字段格式无效，请检查导入格式") from error
    if len({(record.protocol, record.external_id) for record in rows}) != len(rows):
        raise ValueError("同一个协议内存在重复的对局 ID")
    return rows


class Filters(BaseModel):
    protocol: str | None = Field(default=None, max_length=180)
    play: str | None = Field(default=None, max_length=180)
    difficulty: str | None = Field(default=None, max_length=180)
    start: date | None = None
    end: date | None = None
    include_exits: bool = False

    def sql(self, role_id):
        conditions, values = ["role_id = %s"], [role_id]
        for column in ("protocol", "play", "difficulty"):
            if value := getattr(self, column):
                conditions.append(column + " = %s")
                values.append(value)
        if self.start:
            conditions.append("played_at >= %s")
            values.append(datetime.combine(self.start, time.min, CHINA))
        if self.end:
            conditions.append("played_at <= %s")
            values.append(datetime.combine(self.end, time.max, CHINA))
        if not self.include_exits:
            conditions.append("NOT suspected_exit")
        return " AND ".join(conditions), values
