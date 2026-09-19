#!/bin/bash
# DZE.apk 手工构建：aapt2 → javac → d8 → 打包 dex/so → zipalign → apksigner
set -e
cd "$(dirname "$0")"
BUILD=.build
JDK=$(ls -d $BUILD/jdk-17* | head -1)
export JAVA_HOME="$(cygpath -w "$JDK")"
export PATH="$JDK/bin:$PATH"
BT=$BUILD/sdk/build-tools/34.0.0
AJ=$BUILD/sdk/platforms/android-34/android.jar

echo "== 1/7 安装 SDK 组件（如已装则跳过） =="
yes | "$BUILD/sdk/cmdline-tools/latest/bin/sdkmanager.bat" --licenses >/dev/null 2>&1 || true
"$BUILD/sdk/cmdline-tools/latest/bin/sdkmanager.bat" "platforms;android-34" "build-tools;34.0.0" 2>&1 | tail -1

echo "== 2/7 aapt2 编译资源 =="
rm -rf apk_work && mkdir -p apk_work/gen
"$BT/aapt2.exe" compile --dir android/res -o apk_work/res.zip
"$BT/aapt2.exe" link -o apk_work/base.apk -I "$AJ" \
    --manifest android/AndroidManifest.xml --java apk_work/gen \
    -A android/assets --min-sdk-version 24 --target-sdk-version 34 apk_work/res.zip

echo "== 3/7 javac 编译 =="
find apk_work/gen android/java -name "*.java" > apk_work/sources.txt
mkdir -p apk_work/classes
"$JDK/bin/javac" -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath "$AJ" \
    -d apk_work/classes @apk_work/sources.txt

echo "== 4/7 d8 转 dex =="
mkdir -p apk_work/dex
"$BT/d8.bat" --release --lib "$AJ" --output apk_work/dex $(find apk_work/classes -name "*.class")

echo "== 5/7 打包 dex 与 native lib =="
mkdir -p apk_work/lib/arm64-v8a apk_work/dexroot
cp android/jniLibs/arm64-v8a/libaria2c.so apk_work/lib/arm64-v8a/
cp apk_work/dex/classes.dex apk_work/dexroot/
cp apk_work/base.apk apk_work/unsigned.apk
"$LOCALAPPDATA/Programs/Python/Python314/python.exe" - <<'PYEOF'
import zipfile, os
os.chdir("apk_work")
with zipfile.ZipFile("unsigned.apk", "a", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join("dexroot", "classes.dex"), "classes.dex")
    z.write(os.path.join("lib", "arm64-v8a", "libaria2c.so"), "lib/arm64-v8a/libaria2c.so")
print("dex + lib 已写入 APK")
PYEOF

echo "== 6/7 zipalign =="
"$BT/zipalign.exe" -f 4 apk_work/unsigned.apk apk_work/aligned.apk

echo "== 7/7 签名 =="
if [ ! -f dze.keystore ]; then
  "$JDK/bin/keytool" -genkeypair -keystore dze.keystore -alias dze \
    -storepass dze12345 -keypass dze12345 -dname "CN=DZE,O=DZE,C=CN" \
    -keyalg RSA -keysize 2048 -validity 10000
fi
"$BT/apksigner.bat" sign --ks dze.keystore --ks-pass pass:dze12345 \
    --key-pass pass:dze12345 --out DZE.apk apk_work/aligned.apk
"$BT/apksigner.bat" verify --print-certs DZE.apk | head -3
ls -la DZE.apk
echo "== DZE.apk 构建完成 =="