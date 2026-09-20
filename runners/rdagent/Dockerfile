# RD-Agent runner 镜像(建议在 Linux x86 上构建)
# stub:
#   docker build -t signal-rdagent:stub -f runners/rdagent/Dockerfile .
# real:
#   docker build --build-arg BACKEND=real -t signal-rdagent:real -f runners/rdagent/Dockerfile .
ARG BACKEND=stub
FROM python:3.12-slim
ARG BACKEND
WORKDIR /opt/runner
COPY runners/common /opt/runner/common
COPY runners/rdagent/to_package.py /opt/runner/to_package.py
COPY runners/rdagent/real_backend.py /opt/runner/real_backend.py
COPY runners/rdagent/runner.py /opt/runner/runner.py
COPY runners/rdagent/stub_runner.py /opt/runner/stub_runner.py
ENV PYTHONUNBUFFERED=1
ENV SIGNAL_STUB_LOOP_SLEEP=0.5
ENV SIGNAL_RUNNER_BACKEND=${BACKEND}
# real 镜像可在此层 pip install rdagent(保持与主平台隔离)
CMD ["python", "/opt/runner/runner.py"]
