import os
import requests
import subprocess
from pathlib import Path

# --- 实验室配置 ---
SEAFILE_CONFIG = {
    "server": "https://seafile.compin.net",  # 替换为你的 Seafile 地址
    "token": "e3886bc691b077d5416fab5e546c70fec2f6ce92",                     # 填入你获取的 Token
    "files": {
        "/runner.py": "runner.py",               # Seafile 路径 : 本地保存路径
    }
}

def sync_tools():
    """从 Seafile 同步最新的实验工具。"""
    print(">>> 📥 正在从实验室 Seafile 同步核心工具...")
    headers = {"Authorization": f"Token {SEAFILE_CONFIG['token']}"}
    
    for remote_path, local_name in SEAFILE_CONFIG["files"].items():
        # 1. 获取下载链接 (API v2.1)
        api_url = f"{SEAFILE_CONFIG['server']}/api/v2.1/via-repo-token/download-link/"
        try:
            resp = requests.get(api_url, headers=headers, params={"path": remote_path}, timeout=10)
            resp.raise_for_status()
            download_url = resp.json()
            
            # 2. 下载并保存
            file_data = requests.get(download_url, timeout=30)
            Path(local_name).write_bytes(file_data.content)
            print(f"   [OK] {local_name} 同步成功")
        except Exception as e:
            print(f"   [Error] 同步 {local_name} 失败: {e}")

def init_env():
    """初始化 uv 环境和 Git 规范。"""
    print(">>> 🛠️ 正在初始化实验环境...")
    
    # 初始化 uv (如果不存在 pyproject.toml)
    if not Path("pyproject.toml").exists():
        subprocess.run(["uv", "init"], check=True)
        # 预装 runner.py 依赖的库
        subprocess.run(["uv", "add", "requests", "minio"], check=True)
    
    # 建立标准的实验目录
    for folder in ["scripts", "data", "results"]:
        Path(folder).mkdir(exist_ok=True)
        (Path(folder) / ".gitkeep").touch()
        
    # 初始化 Git
    if not Path(".git").exists():
        subprocess.run(["git", "init"], check=True)
        with open(".gitignore", "a") as f:
            f.write("\n# Lab Automation\nrun_dir/\n__pycache__/\n.venv/\n")

if __name__ == "__main__":
    sync_tools()
    init_env()
    print("\n✅ 初始化完成。请将仿真脚本放入 scripts/ 目录，")
    print("   执行命令: uv run python3 runner.py scripts/your_sim.py")