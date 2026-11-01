#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$BASE"
PUBLIC_URL="https://syl0425.github.io/pregnancy-countdown"
KEY="$BASE/.deploy/github_pages_ed25519"

if [ ! -f "$KEY" ]; then
  echo "缺少本仓库专用发布密钥：$KEY" >&2
  exit 1
fi

python build_ics.py
node validate-ui.cjs

git add -- .
if git diff --cached --quiet; then
  echo "没有需要发布的新变更。"
else
  git commit -m "Update pregnancy timeline $(date +%F)"
  GIT_SSH_COMMAND="ssh -i '$KEY' -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15" git push origin main
fi

python -c 'import json,time,urllib.request
public="https://syl0425.github.io/pregnancy-countdown"
local=json.load(open("data.json",encoding="utf-8"))
last=None
for attempt in range(18):
    try:
        with urllib.request.urlopen(public+"/data.json?check="+str(time.time()),timeout=20) as r:
            remote=json.load(r)
        with urllib.request.urlopen(public+"/calendar.ics?check="+str(time.time()),timeout=20) as r:
            cal=r.read().decode("utf-8")
        if remote==local and "BEGIN:VCALENDAR" in cal:
            print("公开页面、主数据和日历文件已更新："+public+"/")
            break
    except Exception as e:
        last=e
    if attempt==17:
        raise SystemExit("公开版本尚未更新，请稍后检查："+str(last))
    time.sleep(5)
'
