from pathlib import Path

records = Path("logbook/records.py")
text = records.read_text(encoding="utf-8")
text = text.replace("    def sql(self, role_id):\n        conditions, values = [\"role_id = %s\"], [role_id]",
                    "    def sql(self, user_id):\n        conditions, values = [\"user_id = %s\"], [user_id]")
records.write_text(text, encoding="utf-8")

worker = Path("tests/test_worker.py")
content = worker.read_text(encoding="utf-8")
content = content.replace('"SELECT id, role_id, payload, total"', '"SELECT id, user_id, payload, total"')
content = content.replace('"role_id": uuid4(),', '"user_id": uuid4(),')
content = content.replace('"ON CONFLICT (role_id, protocol, external_id) DO UPDATE"', '"ON CONFLICT (user_id, protocol, external_id) DO UPDATE"')
content = content.replace('assert rows[0][1] == current["role_id"]', 'assert rows[0][1] == current["user_id"]')
content = content.replace('assert "INSERT INTO matches (id, role_id" in UPSERT_MATCH', 'assert "INSERT INTO matches (id, user_id" in UPSERT_MATCH')
worker.write_text(content, encoding="utf-8")
print("patched")
