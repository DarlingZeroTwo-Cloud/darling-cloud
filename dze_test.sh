export DZE_INSECURE_TLS=1
cd /mnt/c/Users/Administrator/Documents/下载器/darling-cloud
pkill -f "dist/DZE" 2>/dev/null; sleep 1
(./dist/DZE > /tmp/dze.log 2>&1 &)
export DZE_INSECURE_TLS=1
sleep 4
echo "=== 启动日志 ==="; cat /tmp/dze.log
URL=$(grep -o 'http://127.0.0.1:[0-9]*' /tmp/dze.log | head -1)
echo "=== 页面状态码 ==="; curl -s -o /dev/null -w "%{http_code}\n" $URL/
echo "=== aria2c 检测 ==="; curl -s $URL/api/status | head -c 200; echo
echo "=== 下真实任务 ==="
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"url":"https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0.tar.gz"}' \
  $URL/api/start; echo
for i in 1 2 3 4 5 6; do
  sleep 6
  curl -s $URL/api/status | python3 -c 'import json,sys; s=json.load(sys.stdin); t=s["tasks"][0]; print(t["state"], str(round(t["pct"],1))+"%", t["size_text"], t["speed_text"], t["note"])'
done
pkill -f "dist/DZE"; echo "=== 测试结束 ==="
