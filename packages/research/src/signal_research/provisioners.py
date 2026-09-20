"""供给器:把 job 拉起到可运行状态。

M4:
- LocalProcessProvisioner:子进程跑 stub runner(单测/无 Docker)
- LocalDockerProvisioner:docker run(本机冒烟)
M5:
- RemoteSSHProvisioner:paramiko + rsync + 远端 docker run
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from signal_research.ssh_ops import (
    ParamikoSshTransport,
    SshError,
    SshTransport,
    resolve_ssh_key,
    rsync_to_remote,
)

logger = logging.getLogger(__name__)

TransportFactory = Callable[[str, str, str | None, int], SshTransport]


class ProvisionError(RuntimeError):
    pass


class Provisioner(ABC):
    @abstractmethod
    def start(self, job_id: str, spec: dict, *, work_root: Path | None = None) -> dict:
        """启动 runner,返回 runtime 信息(container_id / pid / work_dir)。"""

    @abstractmethod
    def is_alive(self, runtime: dict) -> bool:
        """探测 runner 是否仍在运行。"""

    @abstractmethod
    def stop(self, runtime: dict) -> None:
        """停止 runner。"""

    def cleanup(self, runtime: dict) -> None:
        """任务结束后清理(默认等同 stop)。"""
        self.stop(runtime)

    def fetch_events_jsonl(self, runtime: dict) -> str | None:
        """拉回 runner 本地 events.jsonl(webhook 丢失时补账)。默认无。"""
        return None


class LocalProcessProvisioner(Provisioner):
    """用本机 Python 跑 runners/*/runner.py(不依赖 Docker)。"""

    def __init__(
        self,
        runner_script: Path,
        python_exe: str | None = None,
        *,
        runner_backend: str = "stub",
    ) -> None:
        self._script = runner_script
        self._python = python_exe or os.environ.get("SIGNAL_RUNNER_PYTHON") or "python3"
        self._runner_backend = runner_backend

    def start(self, job_id: str, spec: dict, *, work_root: Path | None = None) -> dict:
        if not self._script.exists():
            raise ProvisionError(f"runner 脚本不存在: {self._script}")
        root = Path(work_root or tempfile.mkdtemp(prefix=f"signal-job-{job_id[:8]}-"))
        root.mkdir(parents=True, exist_ok=True)
        spec_path = root / "job_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        env = os.environ.copy()
        env["SIGNAL_JOB_SPEC"] = str(spec_path)
        env["SIGNAL_JOB_WORKDIR"] = str(root)
        env["SIGNAL_RUNNER_BACKEND"] = self._runner_backend
        llm = spec.get("llm") or {}
        cb = spec.get("callback") or {}
        for ref_key, env_name in (
            (llm.get("api_key_ref"), "LLM_API_KEY"),
            (cb.get("hmac_key_ref"), "CALLBACK_HMAC_SECRET"),
        ):
            if isinstance(ref_key, str) and ref_key.startswith("env:"):
                var = ref_key.removeprefix("env:")
                if var in os.environ:
                    env[env_name] = os.environ[var]
                    env[var] = os.environ[var]
        log_path = root / "runner.log"
        log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
        try:
            proc = subprocess.Popen(
                [self._python, str(self._script)],
                cwd=str(root),
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as e:
            log_f.close()
            raise ProvisionError(f"启动 runner 失败: {e}") from e
        return {
            "type": "local_process",
            "pid": proc.pid,
            "work_dir": str(root),
            "log_path": str(log_path),
            "spec_path": str(spec_path),
        }

    def is_alive(self, runtime: dict) -> bool:
        pid = runtime.get("pid")
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False

    def stop(self, runtime: dict) -> None:
        import contextlib

        pid = runtime.get("pid")
        if not pid:
            return
        with contextlib.suppress(OSError):
            os.kill(int(pid), 15)


class LocalDockerProvisioner(Provisioner):
    """docker run 拉起 runner 镜像。"""

    def __init__(
        self,
        image: str = "signal-alphaagent:stub",
        docker_bin: str = "docker",
        *,
        alphaagent_image: str | None = None,
        rdagent_image: str | None = None,
        runner_backend: str = "stub",
    ) -> None:
        self._image = image
        self._docker = docker_bin
        self._alphaagent_image = alphaagent_image or "signal-alphaagent:stub"
        self._rdagent_image = rdagent_image or image or "signal-rdagent:stub"
        self._runner_backend = runner_backend

    def _image_for_producer(self, producer: str) -> str:
        p = (producer or "").lower()
        if p.startswith("rdagent"):
            return self._rdagent_image
        if p.startswith("alphaagent"):
            return self._alphaagent_image
        return self._image

    def start(self, job_id: str, spec: dict, *, work_root: Path | None = None) -> dict:
        if not shutil.which(self._docker):
            raise ProvisionError("本机未找到 docker")
        root = Path(work_root or tempfile.mkdtemp(prefix=f"signal-job-{job_id[:8]}-"))
        root.mkdir(parents=True, exist_ok=True)
        spec_path = root / "job_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        image = self._image_for_producer(str(spec.get("producer") or ""))
        env_args: list[str] = [
            "-e",
            "SIGNAL_JOB_SPEC=/work/job_spec.json",
            "-e",
            "SIGNAL_JOB_WORKDIR=/work",
            "-e",
            f"SIGNAL_RUNNER_BACKEND={self._runner_backend}",
        ]
        llm = spec.get("llm") or {}
        cb = spec.get("callback") or {}
        for ref in (llm.get("api_key_ref"), cb.get("hmac_key_ref")):
            if isinstance(ref, str) and ref.startswith("env:"):
                var = ref.removeprefix("env:")
                if var in os.environ:
                    env_args.extend(["-e", f"{var}={os.environ[var]}"])
        name = f"signal-job-{job_id[:8]}"
        cmd = [
            self._docker,
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-v",
            f"{root}:/work",
            *env_args,
            image,
        ]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
        except subprocess.CalledProcessError as e:
            raise ProvisionError(f"docker run 失败: {e.output}") from e
        return {
            "type": "local_docker",
            "container_id": out,
            "container_name": name,
            "work_dir": str(root),
            "spec_path": str(spec_path),
            "image": image,
        }

    def is_alive(self, runtime: dict) -> bool:
        cid = runtime.get("container_id") or runtime.get("container_name")
        if not cid:
            return False
        try:
            out = subprocess.check_output(
                [self._docker, "inspect", "-f", "{{.State.Running}}", str(cid)],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            return out == "true"
        except subprocess.CalledProcessError:
            return False

    def stop(self, runtime: dict) -> None:
        cid = runtime.get("container_id") or runtime.get("container_name")
        if not cid:
            return
        subprocess.run([self._docker, "rm", "-f", str(cid)], check=False, capture_output=True)


def _secret_env_from_spec(spec: dict) -> dict[str, str]:
    """从本机环境解析 spec 中的 env:VAR 引用,供会话注入(不落远端盘)。"""
    env: dict[str, str] = {}
    llm = spec.get("llm") or {}
    cb = spec.get("callback") or {}
    for ref in (llm.get("api_key_ref"), cb.get("hmac_key_ref")):
        if isinstance(ref, str) and ref.startswith("env:"):
            var = ref.removeprefix("env:")
            val = os.environ.get(var)
            if val:
                env[var] = val
    # runner 侧常用别名
    llm_key = os.environ.get("LLM_API_KEY")
    if llm_key:
        env.setdefault("LLM_API_KEY", llm_key)
    cb_secret = os.environ.get("RUNNER_CALLBACK_SECRET")
    if cb_secret:
        env.setdefault("RUNNER_CALLBACK_SECRET", cb_secret)
        env.setdefault("CALLBACK_HMAC_SECRET", cb_secret)
    return env


def _default_transport_factory(host: str, user: str, key: str | None, port: int) -> SshTransport:
    return ParamikoSshTransport(host, user, port=port, key_material_or_path=key)


class RemoteSSHProvisioner(Provisioner):
    """经 SSH 在远端拉起 Docker runner;secrets 仅会话环境变量注入。"""

    def __init__(
        self,
        *,
        image: str = "signal-rdagent:stub",
        alphaagent_image: str = "signal-alphaagent:stub",
        rdagent_image: str | None = None,
        remote_work_root: str = "/tmp/signal-jobs",
        provision_script: Path | None = None,
        data_snapshots_dir: Path | None = None,
        ssh_port: int = 22,
        run_host_provision: bool = True,
        reverse_tunnel: bool = False,
        reverse_tunnel_remote_port: int = 18000,
        reverse_tunnel_local_port: int = 8000,
        runner_backend: str = "stub",
        transport_factory: TransportFactory | None = None,
        rsync_fn: Callable[..., None] | None = None,
    ) -> None:
        self._image = image
        self._alphaagent_image = alphaagent_image
        self._rdagent_image = rdagent_image or image
        self._remote_work_root = remote_work_root.rstrip("/")
        self._provision_script = provision_script
        self._data_snapshots_dir = data_snapshots_dir
        self._ssh_port = ssh_port
        self._run_host_provision = run_host_provision
        self._reverse_tunnel = reverse_tunnel
        self._reverse_tunnel_remote_port = reverse_tunnel_remote_port
        self._reverse_tunnel_local_port = reverse_tunnel_local_port
        self._runner_backend = runner_backend
        self._transport_factory = transport_factory or _default_transport_factory
        self._rsync_fn = rsync_fn or rsync_to_remote

    def _open(self, spec: dict) -> tuple[SshTransport, dict]:
        target = spec.get("runner_target") or {}
        host = target.get("host")
        user = target.get("user")
        if not host or not user:
            raise ProvisionError("remote_ssh 需要 runner_target.host 与 user")
        key = resolve_ssh_key(target.get("ssh_key_ref"))
        try:
            transport = self._transport_factory(host, user, key, self._ssh_port)
        except SshError as e:
            raise ProvisionError(str(e)) from e
        except Exception as e:
            raise ProvisionError(f"SSH 连接失败: {e}") from e
        meta = {
            "host": host,
            "user": user,
            "ssh_key_ref": target.get("ssh_key_ref"),
            "ssh_port": self._ssh_port,
            "key_path": key if key and Path(key).is_file() else None,
        }
        return transport, meta

    def start(self, job_id: str, spec: dict, *, work_root: Path | None = None) -> dict:
        transport, meta = self._open(spec)
        remote_dir = f"{self._remote_work_root}/{job_id}"
        container_name = f"signal-job-{job_id[:8]}"
        try:
            if self._run_host_provision:
                self._ensure_host_ready(transport)

            transport.run(f"mkdir -p {shlex.quote(remote_dir)}")
            # job_spec 无 secrets,可落盘
            spec_json = json.dumps(spec, ensure_ascii=False, indent=2)
            transport.write_text(f"{remote_dir}/job_spec.json", spec_json)

            # 数据快照增量下发(可选)
            snapshot = spec.get("data_snapshot") or ""
            if self._data_snapshots_dir and snapshot:
                local_snap = Path(self._data_snapshots_dir) / snapshot
                if local_snap.exists():
                    remote_data = f"{remote_dir}/data"
                    transport.run(f"mkdir -p {shlex.quote(remote_data)}")
                    self._rsync_fn(
                        local_snap,
                        user=meta["user"],
                        host=meta["host"],
                        remote_path=remote_data,
                        ssh_key_path=meta.get("key_path"),
                        port=meta["ssh_port"],
                    )

            secret_env = _secret_env_from_spec(spec)
            # secrets 只出现在 SSH 会话 export + docker -e 传递,不写远端文件
            env_docker_args = " ".join(f"-e {shlex.quote(k)}" for k in secret_env)
            image = self._image_for_producer(spec.get("producer") or "")
            run_cmd = (
                f"docker rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true; "
                f"docker run -d --rm --name {shlex.quote(container_name)} "
                f"-v {shlex.quote(remote_dir)}:/work "
                f"-e SIGNAL_JOB_SPEC=/work/job_spec.json "
                f"-e SIGNAL_JOB_WORKDIR=/work "
                f"-e SIGNAL_RUNNER_BACKEND={shlex.quote(self._runner_backend)} "
                f"{env_docker_args} "
                f"{shlex.quote(image)}"
            )
            result = transport.run(run_cmd, env=secret_env or None)
            if result.exit_code != 0:
                raise ProvisionError(
                    f"远端 docker run 失败: {result.stderr or result.stdout}".strip()
                )
            container_id = result.stdout.strip().splitlines()[-1].strip()
            return {
                "type": "remote_ssh",
                "host": meta["host"],
                "user": meta["user"],
                "ssh_key_ref": meta.get("ssh_key_ref"),
                "ssh_port": meta["ssh_port"],
                "container_id": container_id,
                "container_name": container_name,
                "remote_work_dir": remote_dir,
                "image": image,
                "reverse_tunnel": self._reverse_tunnel,
            }
        except SshError as e:
            raise ProvisionError(str(e)) from e
        finally:
            transport.close()

    def _image_for_producer(self, producer: str) -> str:
        p = producer.lower()
        if p.startswith("rdagent"):
            return self._rdagent_image
        if p.startswith("alphaagent"):
            return self._alphaagent_image
        return self._image

    def _ensure_host_ready(self, transport: SshTransport) -> None:
        check = transport.run("command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1")
        if check.exit_code == 0:
            # 确保镜像可用(本地已有则跳过 pull)
            pull = transport.run(
                f"docker image inspect {shlex.quote(self._image)} >/dev/null 2>&1 "
                f"|| docker pull {shlex.quote(self._image)} >/dev/null 2>&1 || true"
            )
            logger.debug("image ensure: %s", pull.exit_code)
            return
        script = self._provision_script
        if script is None:
            root = Path(__file__).resolve().parents[4]
            script = root / "deploy" / "provision" / "setup_runner_host.sh"
        if not script.exists():
            raise ProvisionError(
                f"远端未就绪且找不到 provision 脚本: {script}。"
                "请先在主机执行 deploy/provision/setup_runner_host.sh"
            )
        content = script.read_text(encoding="utf-8")
        remote_script = "/tmp/signal-setup_runner_host.sh"
        transport.write_text(remote_script, content)
        # 脚本本身不写入任何 secret
        result = transport.run(
            f"bash {shlex.quote(remote_script)} --image {shlex.quote(self._image)}"
        )
        if result.exit_code != 0:
            raise ProvisionError(f"远端 provision 失败: {(result.stderr or result.stdout)[:800]}")

    def _reconnect(self, runtime: dict) -> SshTransport:
        host = runtime.get("host")
        user = runtime.get("user")
        if not host or not user:
            raise ProvisionError("runtime 缺少 host/user")
        key = resolve_ssh_key(runtime.get("ssh_key_ref"))
        port = int(runtime.get("ssh_port") or self._ssh_port)
        return self._transport_factory(host, user, key, port)

    def is_alive(self, runtime: dict) -> bool:
        if runtime.get("type") != "remote_ssh":
            return False
        cid = runtime.get("container_id") or runtime.get("container_name")
        if not cid:
            return False
        try:
            transport = self._reconnect(runtime)
        except Exception:
            return False
        try:
            result = transport.run(
                f"docker inspect -f '{{{{.State.Running}}}}' {shlex.quote(str(cid))} 2>/dev/null"
            )
            return result.exit_code == 0 and result.stdout.strip() == "true"
        finally:
            transport.close()

    def stop(self, runtime: dict) -> None:
        if runtime.get("type") != "remote_ssh":
            return
        cid = runtime.get("container_id") or runtime.get("container_name")
        try:
            transport = self._reconnect(runtime)
        except Exception as e:
            logger.warning("stop: SSH 失败 %s", e)
            return
        try:
            if cid:
                transport.run(f"docker rm -f {shlex.quote(str(cid))} >/dev/null 2>&1 || true")
        finally:
            transport.close()

    def cleanup(self, runtime: dict) -> None:
        """停容器并删除远端工作目录(含 events/产物临时文件;secrets 本就不落盘)。"""
        if runtime.get("type") != "remote_ssh":
            self.stop(runtime)
            return
        try:
            transport = self._reconnect(runtime)
        except Exception as e:
            logger.warning("cleanup: SSH 失败 %s", e)
            return
        try:
            cid = runtime.get("container_id") or runtime.get("container_name")
            if cid:
                transport.run(f"docker rm -f {shlex.quote(str(cid))} >/dev/null 2>&1 || true")
            remote_dir = runtime.get("remote_work_dir")
            if remote_dir and str(remote_dir).startswith(self._remote_work_root):
                transport.run(f"rm -rf {shlex.quote(str(remote_dir))}")
        finally:
            transport.close()

    def fetch_events_jsonl(self, runtime: dict) -> str | None:
        if runtime.get("type") != "remote_ssh":
            return None
        remote_dir = runtime.get("remote_work_dir")
        if not remote_dir:
            return None
        path = f"{remote_dir}/events.jsonl"
        try:
            transport = self._reconnect(runtime)
        except Exception as e:
            logger.warning("fetch_events: SSH 失败 %s", e)
            return None
        try:
            result = transport.run(f"test -f {shlex.quote(path)} && cat {shlex.quote(path)}")
            if result.exit_code != 0:
                return None
            return result.stdout
        finally:
            transport.close()
