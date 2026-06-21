"""x-cli plugins package (placeholder).

MVP 阶段（Phase 1）所有 todo action 都直接 inline 在 x.py 里。
Phase 4 会把这个目录拆成独立插件：

    plugins/
    ├── todo.py    # x todo 子命令（list / add / update / archive / stats）
    ├── skill.py   # x skill 子命令（未来）
    └── system.py  # x system 子命令（未来）

主入口届时改用 importlib.import_module("plugins.<name>") 动态加载。
"""

from __future__ import annotations
