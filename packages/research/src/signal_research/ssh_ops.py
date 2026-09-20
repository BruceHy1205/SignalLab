"""SSH/rsync 底层操作(供 RemoteSSHProvisioner 使用;可注入假实现做单测)。"""

from __future__ import annotations

import io
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class SshError(RuntimeError):
    pass


@dataclass(frozen=True)
class SshExecResult:
    exit_code: int
    stdout: str
    stderr: str


class SshTransport(Protocol):
    def run(self, command: str, *, env: dict[str, str] | None = None) -> SshExecResult: ...

    def write_text(self, remote_path: str, content: str) -> None: ...

    def read_text(self, remote_path: str) -> str: ...

    def close(self) -> None: ...


def resolve_ssh_key(ssh_key_ref: str | None) -> str | None:
    """解析 env:VAR → 私钥内容或路径。空引用返回 None(走默认 agent/~/.ssh)。"""
    if not ssh_key_ref:
        return None
    if not ssh_key_ref.startswith("env:"):
        raise SshError(f"非法 ssh_key_ref: {ssh_key_ref!r}")
    var = ssh_key_ref.removeprefix("env:")
    value = os.environ.get(var)
    if not value:
        raise SshError(f"环境变量 {var} 未设置或为空")
    return value


def _load_pkey(key_material_or_path: str):
    import paramiko

    path = Path(key_material_or_path)
    if path.is_file():
        return None, str(path)
    buf = io.StringIO(key_material_or_path)
    for loader in (
        paramiko.Ed25519Key.from_private_key,
        paramiko.RSAKey.from_private_key,
        paramiko.ECDSAKey.from_private_key,
    ):
        try:
            buf.seek(0)
            return loader(buf), None
        except Exception:
            continue
    raise SshError("无法解析 SSH 私钥(支持 Ed25519/RSA/ECDSA 或文件路径)")


class ParamikoSshTransport:
    """基于 paramiko 的真实 SSH 传输。"""

    def __init__(
        self,
        host: str,
        user: str,
        *,
        port: int = 22,
        key_material_or_path: str | None = None,
        connect_timeout: float = 30.0,
    ) -> None:
        import paramiko

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": host,
            "username": user,
            "port": port,
            "timeout": connect_timeout,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if key_material_or_path:
            pkey, key_filename = _load_pkey(key_material_or_path)
            if key_filename:
                kwargs["key_filename"] = key_filename
            else:
                kwargs["pkey"] = pkey
        self._client.connect(**kwargs)
        self._sftp = self._client.open_sftp()

    def run(self, command: str, *, env: dict[str, str] | None = None) -> SshExecResult:
        if env:
            exports = " ".join(
                f"export {k}={shlex.quote(v)};" for k, v in env.items() if v is not None
            )
            command = f"{exports} {command}"
        _stdin, stdout, stderr = self._client.exec_command(command, timeout=600)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return SshExecResult(exit_code=code, stdout=out, stderr=err)

    def write_text(self, remote_path: str, content: str) -> None:
        parent = str(Path(remote_path).parent)
        self.run(f"mkdir -p {shlex.quote(parent)}")
        with self._sftp.file(remote_path, "w") as f:
            f.write(content)

    def read_text(self, remote_path: str) -> str:
        with self._sftp.file(remote_path, "r") as f:
            data = f.read()
            return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._client.close()


def rsync_to_remote(
    local_path: Path,
    *,
    user: str,
    host: str,
    remote_path: str,
    ssh_key_path: str | None = None,
    port: int = 22,
) -> None:
    """增量 rsync 本地目录到远端。需要本机 rsync 与 ssh。"""
    if not local_path.exists():
        raise SshError(f"本地快照不存在: {local_path}")
    ssh_parts = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-p", str(port)]
    if ssh_key_path and Path(ssh_key_path).is_file():
        ssh_parts.extend(["-i", ssh_key_path])
    cmd = [
        "rsync",
        "-az",
        "--delete",
        "-e",
        " ".join(ssh_parts),
        f"{local_path}/",
        f"{user}@{host}:{remote_path.rstrip('/')}/",
    ]
    logger.info("rsync %s -> %s@%s:%s", local_path, user, host, remote_path)
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=3600)
    except FileNotFoundError as e:
        raise SshError("本机未找到 rsync") from e
    except subprocess.CalledProcessError as e:
        raise SshError(f"rsync 失败: {e.output}") from e
