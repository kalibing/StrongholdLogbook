"""把前端构建产物（frontend/dist）通过 FTP 发布到虚拟主机。

凭据只从本地文件 deploy/ftp.env 或同名环境变量读取，deploy/ftp.env 已在 .gitignore 中，不会提交。
默认使用 FTPS（显式 TLS）；只有主机确实不支持时才在 ftp.env 里设 FTP_TLS=0（明文 FTP 会把密码明文传输）。

用法：
    copy deploy\\ftp.env.example deploy\\ftp.env   # 然后自己填写主机、账号、密码、远程目录
    cd frontend && npm run build && cd ..
    python scripts/deploy_ftp.py --dry-run          # 只列出要上传的文件
    python scripts/deploy_ftp.py                    # 上传

注意：网站需要同域的 /api 后端。只发布前端时页面能打开，但登录和数据请求会失败。
"""

import argparse
from ftplib import FTP, FTP_TLS, error_perm
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
CONFIG = ROOT / "deploy" / "ftp.env"
HTACCESS = ROOT / "deploy" / "htaccess"
KEYS = ("FTP_HOST", "FTP_PORT", "FTP_USER", "FTP_PASSWORD", "FTP_REMOTE_DIR", "FTP_TLS")


def load_config() -> dict:
    values = {}
    if CONFIG.is_file():
        for line in CONFIG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in KEYS:
        if os.getenv(key):
            values[key] = os.environ[key]
    missing = [key for key in ("FTP_HOST", "FTP_USER", "FTP_PASSWORD") if not values.get(key)]
    if missing:
        sys.exit(f"缺少配置：{', '.join(missing)}。请在 {CONFIG.relative_to(ROOT)} 中填写（参考 ftp.env.example）。")
    values.setdefault("FTP_PORT", "21")
    values.setdefault("FTP_REMOTE_DIR", "/")
    values.setdefault("FTP_TLS", "1")
    return values


def files_to_upload() -> list[tuple[Path, str]]:
    if not (DIST / "index.html").is_file():
        sys.exit("没有找到 frontend/dist/index.html，请先在 frontend 目录执行 npm run build。")
    files = [(path, path.relative_to(DIST).as_posix()) for path in sorted(DIST.rglob("*")) if path.is_file()]
    if HTACCESS.is_file():
        files.append((HTACCESS, ".htaccess"))
    # index.html 最后上传：新版本的 assets 都到位之后才切换入口，访问者不会拿到引用缺失文件的页面。
    files.sort(key=lambda item: item[1] == "index.html")
    return files


def ensure_dir(ftp: FTP, remote: str, known: set[str]) -> None:
    parts = [part for part in remote.split("/") if part]
    current = ""
    for part in parts:
        current += "/" + part
        if current in known:
            continue
        try:
            ftp.mkd(current)
        except error_perm:
            pass  # 已存在
        known.add(current)


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 FTP 发布 frontend/dist")
    parser.add_argument("--dry-run", action="store_true", help="只列出将要上传的文件，不连接服务器")
    args = parser.parse_args()

    files = files_to_upload()
    if args.dry_run:
        for _, remote in files:
            print(remote)
        print(f"共 {len(files)} 个文件")
        return

    config = load_config()
    base = "/" + config["FTP_REMOTE_DIR"].strip("/")
    use_tls = config["FTP_TLS"] not in {"0", "false", "no"}
    ftp = FTP_TLS() if use_tls else FTP()
    ftp.connect(config["FTP_HOST"], int(config["FTP_PORT"]), timeout=30)
    ftp.login(config["FTP_USER"], config["FTP_PASSWORD"])
    if use_tls:
        ftp.prot_p()  # 数据通道也加密
    else:
        print("警告：FTP_TLS=0，账号密码与文件将以明文传输。", file=sys.stderr)
    known: set[str] = set()
    try:
        for index, (local, remote) in enumerate(files, 1):
            target = f"{base.rstrip('/')}/{remote}"
            ensure_dir(ftp, target.rsplit("/", 1)[0], known)
            with local.open("rb") as handle:
                ftp.storbinary(f"STOR {target}", handle)
            print(f"[{index}/{len(files)}] {remote}")
    finally:
        ftp.quit()
    print("发布完成。旧版本 assets 里的过期文件不会自动删除，可以定期手动清理。")


if __name__ == "__main__":
    main()
