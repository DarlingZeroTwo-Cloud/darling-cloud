#!/usr/bin/env bash
# Darling Cloud M1 冒烟测试：一条命令验证用户系统全链路
# 用法: bash scripts/smoke.sh [port]
set -e
PORT="${1:-18081}"
BASE="http://127.0.0.1:$PORT"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="$ROOT/server/data/darling.db"
PASS=0; FAIL=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "== Darling Cloud M1 冒烟测试 (port $PORT) =="

# 1. ping
[ "$(curl -s --noproxy '*' $BASE/api/ping | grep -c '"ok":true')" = "1" ] && ok "ping" || bad "ping"

# 2. 验证码
curl -s --noproxy '*' -D /tmp/smoke.h -o /tmp/smoke.png $BASE/api/auth/captcha
CID=$(grep -i x-captcha-id /tmp/smoke.h | tr -d '\r' | awk '{print $2}')
[ -n "$CID" ] && ok "验证码生成 (id=$CID)" || bad "验证码生成"

# 3. 验证码从 DB 读答案（模拟前端看图）
ANS=$(python3 -c "
import sqlite3
c=sqlite3.connect('$DB')
print(c.execute('SELECT answer FROM captchas WHERE id=?',('$CID',)).fetchone()[0])
")
[ -n "$ANS" ] && ok "验证码答案可读" || bad "验证码答案"

# 4. 注册测试账号（存在则跳过）
REG=$(curl -s --noproxy '*' -X POST $BASE/api/auth/register -H "Content-Type: application/json" \
  -d "{\"username\":\"smoketest\",\"password\":\"smoke123456\",\"email\":\"smoke@darling.cloud\",\"captcha_id\":\"$CID\",\"captcha_answer\":\"$ANS\"}")
echo "$REG" | grep -q '"token"' && ok "注册 smoketest" || echo "  ℹ️  smoketest 可能已存在: $(echo $REG | head -c 80)"

# 5. 验证码重用被拒
REUSE=$(curl -s --noproxy '*' -X POST $BASE/api/auth/register -H "Content-Type: application/json" \
  -d "{\"username\":\"smoketest2\",\"password\":\"smoke123456\",\"email\":\"s2@darling.cloud\",\"captcha_id\":\"$CID\",\"captcha_answer\":\"$ANS\"}")
echo "$REUSE" | grep -q '验证码错误' && ok "验证码单次消费（重用被拒）" || bad "验证码单次消费"

# 6. 登录
TOK=$(curl -s --noproxy '*' -X POST $BASE/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"smoketest","password":"smoke123456"}' | python3 -c "import json,sys;print(json.load(sys.stdin).get('token',''))" 2>/dev/null || true)
[ -n "$TOK" ] && ok "登录成功" || bad "登录"

# 7. /me
curl -s --noproxy '*' $BASE/api/auth/me -H "Authorization: Bearer $TOK" | grep -q smoketest && ok "/me" || bad "/me"

# 8. 未登录访问管理端 → 401
[ "$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' $BASE/api/admin/dashboard)" = "401" ] && ok "未登录管理端 401" || bad "未登录管理端 401"

echo ""
echo "== 结果: $PASS 通过, $FAIL 失败 =="
[ "$FAIL" = "0" ]
