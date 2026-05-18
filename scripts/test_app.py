#!/usr/bin/env python3
"""测试打包后的 .app 是否能正常启动"""
import subprocess
import time
import os
import signal

app_path = "/Users/lee/content-agent/dist/ContentAgent.app/Contents/MacOS/ContentAgent"
log_file = "/tmp/ca_launch_test.log"

# 启动应用，重定向输出到文件
with open(log_file, "wb") as log:
    proc = subprocess.Popen([app_path], stdout=log, stderr=subprocess.STDOUT)

print(f"启动 PID: {proc.pid}")
print("等待 12 秒...")
time.sleep(12)

# 检查进程是否还在
if proc.poll() is not None:
    print(f"❌ 进程已退出，返回码: {proc.returncode}")
else:
    print("✅ 进程还在运行")

# 检查端口
result = subprocess.run(
    ["lsof", "-a", "-p", str(proc.pid), "-i", "TCP"],
    capture_output=True, text=True
)
if result.stdout:
    print("✅ 该进程已监听端口:")
    for line in result.stdout.strip().split("\n")[1:]:
        print(f"   {line}")
else:
    print("⚠️ 未检测到端口监听")

# 查看日志
print("\n--- 日志内容 ---")
if os.path.exists(log_file):
    with open(log_file, "r", errors="replace") as f:
        print(f.read()[:3000])

# 清理
proc.send_signal(signal.SIGTERM)
try:
    proc.wait(timeout=3)
except:
    proc.kill()
    proc.wait()

os.remove(log_file)
print("\n测试结束")
