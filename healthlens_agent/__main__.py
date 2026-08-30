"""
__main__.py — healthlens_agent 统一命令行入口

用法：
  python -m healthlens_agent                 # 运行全部演示
  python -m healthlens_agent pipeline         # 融合安全管线
  python -m healthlens_agent team             # 四角色 Agent 团队
  python -m healthlens_agent bench            # GOAI 七维评测 + launch-risk
  python -m healthlens_agent safety           # 安全闸门
  python -m healthlens_agent audit            # 运行时审计
  python -m healthlens_agent flow --input "最近疲劳怕冷" --gene mitochondrial:0.32
  python -m healthlens_agent probe --image-desc "舌淡红、苔薄白、面色萎黄"
"""

from __future__ import annotations

import sys

from . import audit, benchmark, flow, multimodal, pipeline, safety, team


def _run_all():
    safety.demo()
    print("\n" + "=" * 70 + "\n")
    audit.demo()
    print("\n" + "=" * 70 + "\n")
    pipeline.demo()
    print("\n" + "=" * 70 + "\n")
    team.demo()
    print("\n" + "=" * 70 + "\n")
    benchmark.main()
    print("\n" + "=" * 70 + "\n")
    flow.demo()
    print("\n" + "=" * 70 + "\n")
    multimodal.demo()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "all"

    if cmd == "pipeline":
        pipeline.demo()
    elif cmd == "team":
        team.demo()
    elif cmd == "bench":
        benchmark.main()
    elif cmd == "safety":
        safety.demo()
    elif cmd == "audit":
        audit.demo()
    elif cmd == "flow":
        # flow.main 内部用 argparse 读取 sys.argv，去掉子命令 token 后转发
        sys.argv = ["healthlens_agent-flow"] + argv[1:]
        flow.main()
    elif cmd == "probe":
        sys.argv = ["healthlens_agent-probe"] + argv[1:]
        multimodal.main()
    elif cmd == "mcp":
        from . import mcp_server
        mcp_server.demo()
    elif cmd in ("all", "help", "-h", "--help"):
        if cmd != "all":
            print(__doc__)
        _run_all()
    else:
        print(f"未知子命令: {cmd}\n")
        print(__doc__)


if __name__ == "__main__":
    main()
