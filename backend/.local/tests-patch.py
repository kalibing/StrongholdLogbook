from pathlib import Path
path = Path("tests/test_api.py")
text = path.read_text(encoding="utf-8")
text = text.replace('        f"/api/roles/{uuid4()}/imports", content=b"{}",\n        headers={"Origin": ORIGIN, "Content-Type": "application/json"},',
                    '        "/api/imports", content=b"{}",\n        headers={"Origin": ORIGIN, "Content-Type": "application/json"},')
text = text.replace('        f"/api/roles/{uuid4()}/imports", content=b"{}",\n        headers={"Origin": ORIGIN, "Content-Type": "text/plain"},',
                    '        "/api/imports", content=b"{}",\n        headers={"Origin": ORIGIN, "Content-Type": "text/plain"},')
text = text.replace('        f"/api/roles/{uuid4()}/imports", content=b"0" * (8 * 1024 * 1024 + 1),',
                    '        "/api/imports", content=b"0" * (8 * 1024 * 1024 + 1),')
text = text.replace('    assert {"/api/health", "/api/roles/{role_id}/overview", "/api/roles/{role_id}/matches",\n            "/api/roles/{role_id}/matches/{match_id}", "/api/roles/{role_id}/operators",\n            "/api/roles/{role_id}/imports"} <= routes',
                    '    assert {"/api/health", "/api/facets", "/api/overview", "/api/matches",\n            "/api/matches/{match_id}", "/api/operators", "/api/imports"} <= routes')
path.write_text(text, encoding="utf-8")

worker = Path("tests/test_worker.py")
content = worker.read_text(encoding="utf-8")
content = content.replace('"role_id": uuid4(),', '"user_id": uuid4(),')
content = content.replace('assert rows[0][1] == current["role_id"]', 'assert rows[0][1] == current["user_id"]')
content = content.replace('"SELECT id, role_id, payload, total"', '"SELECT id, user_id, payload, total"')
worker.write_text(content, encoding="utf-8")
print("patched")
