#!/usr/bin/env python3
import subprocess
import time
import os
import signal

app_path = "/Users/lee/content-agent/dist/ContentAgent.app/Contents/MacOS/ContentAgent"
log_file = "/tmp/ca_launch_test.log"

with open(log_file, "wb") as log:
    proc = subprocess.Popen([app_path], stdout=log, stderr=subprocess.STDOUT)

print(f"启动 PID: {proc.pid}")
print("等待 10 秒...")
time.sleep(10)

if proc.poll() is not None:
    print(f"❌ 进程已退出，返回码: {proc.returncode}")
else:
    print("✅ 进程还在运行")

# 检查端口
result = subprocess.run(
    ["lsof", "-a", "-p", str(proc.pid), "-i", "TCP"],
    capture_output=True, text=True
)
listen_port = None
if result.stdout:
    for line in result.stdout.strip().split("\n")[1:]:
        if "LISTEN" in line:
            parts = line.split()
            addr = parts[-2]
            listen_port = addr.split(":")[-1]
            print(f"✅ 监听端口: {listen_port}")

# HTTP 测试
if listen_port:
    url = f"http://127.0.0.1:{listen_port}"
    print("测试 " + url)
    curl = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True, text=True, timeout=5
    )
    print(f"HTTP 状态码: {curl.stdout.strip()}")
    if curl.stdout.strip() == "200":
        print("服务正常响应！")
    else:
        print("HTTP 非 200")

# 日志
print("\n--- 日志内容 ---")
if os.path.exists(log_file):
    with open(log_file, "r", errors="replace") as f:
        print(f.read()[:3000])

proc.send_signal(signal.SIGTERM)
try:
    proc.wait(timeout=3)
except:
    proc.kill()
    proc.wait()
os.remove(log_file)
print("\n测试结束")
