# -*- coding: utf-8 -*-
"""``rg`` 检索封装（INT-2490，§8.6：关键词检索，无向量 / embedding）。

只用 ripgrep 的 ``--json`` 输出：

- ``--fixed-strings``：用户输入按关键词处理，不当正则（避免 ReDoS 与
  用元字符探测目录内容）；
- 不跟随软链（``rg`` 默认行为），路径根由调用方按身份构造；
- 退出码 1 = 无命中（正常空结果），≥2 = 后端错误（显式失败，不静默返回空，
  否则模型会把「rg 没装」当成「没有记忆」）。
"""
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from agent_service.domain.exceptions import MemoryBackendUnavailable

logger = logging.getLogger(__name__)

_NO_MATCH_EXIT_CODE = 1
# 单文件命中计数上限（评分只需要相对大小，无需精确统计超大文件）
_MAX_COUNTS_PER_FILE = 50


@dataclass
class FileMatch:
    path: str                 # 绝对路径
    matches: int = 0
    snippet: str = ''
    line_number: int = 0
    extra: List[str] = field(default_factory=list)


class RipgrepSearcher:
    def __init__(self, binary: str = 'rg', *, timeout_seconds: float = 5.0,
                 snippet_chars: int = 240,
                 max_file_bytes: int = 1024 * 1024):
        self._binary = (binary or 'rg').strip() or 'rg'
        self._timeout = float(timeout_seconds)
        self._snippet_chars = max(40, int(snippet_chars))
        self._max_file_bytes = max(1024, int(max_file_bytes))

    @property
    def binary(self) -> str:
        return self._binary

    def build_command(self, root: str, pattern: str,
                      *, glob: Optional[str] = None) -> List[str]:
        command = [
            self._binary, '--json', '--fixed-strings', '--no-messages',
            '--max-filesize', str(self._max_file_bytes),
            '--max-count', str(_MAX_COUNTS_PER_FILE),
        ]
        if glob:
            command.extend(['--glob', glob])
        command.extend(['-e', pattern, root])
        return command

    def search(self, root: str, pattern: str,
               *, glob: Optional[str] = None) -> List[FileMatch]:
        command = self.build_command(root, pattern, glob=glob)
        try:
            completed = subprocess.run(
                command, capture_output=True, timeout=self._timeout,
                check=False)
        except FileNotFoundError:
            raise MemoryBackendUnavailable(
                f'检索后端不可用：未找到 {self._binary}（安装 ripgrep 或配置 '
                'AGENT_MEMORY_RG_BIN）')
        except subprocess.TimeoutExpired:
            raise MemoryBackendUnavailable(
                f'检索超时（>{self._timeout:g}s）')
        except OSError as exc:  # pragma: no cover - 平台差异
            raise MemoryBackendUnavailable(f'检索后端不可用：{exc}')

        if completed.returncode not in (0, _NO_MATCH_EXIT_CODE):
            detail = (completed.stderr or b'').decode(
                'utf-8', errors='replace')[:200]
            raise MemoryBackendUnavailable(
                f'检索后端返回 {completed.returncode}：{detail}')
        if completed.returncode == _NO_MATCH_EXIT_CODE:
            return []
        return self._parse(completed.stdout or b'')

    def _parse(self, raw: bytes) -> List[FileMatch]:
        found: Dict[str, FileMatch] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:  # pragma: no cover - rg 输出格式异常
                continue
            if event.get('type') != 'match':
                continue
            data = event.get('data') or {}
            path = ((data.get('path') or {}).get('text')
                    or (data.get('path') or {}).get('bytes'))
            if not path:
                continue
            lines = (data.get('lines') or {}).get('text') or ''
            snippet = ' '.join(lines.strip().split())[:self._snippet_chars]
            match = found.get(path)
            if match is None:
                match = FileMatch(
                    path=path, snippet=snippet,
                    line_number=int(data.get('line_number') or 0))
                found[path] = match
            elif len(match.extra) < 3 and snippet != match.snippet:
                match.extra.append(snippet)
            match.matches += 1
        return list(found.values())


__all__ = ['FileMatch', 'RipgrepSearcher']
