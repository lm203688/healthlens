"""conftest for healthlens_agent 测试：确保仓库根目录在 sys.path，便于导入 healthlens_agent。"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
