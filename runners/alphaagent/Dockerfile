# AlphaAgent runner 镜像
# stub(默认):
#   docker build -t signal-alphaagent:stub -f runners/alphaagent/Dockerfile .
# real(需在构建机预装/缓存 AlphaAgent 依赖,见 runners/README.md):
#   docker build --build-arg BACKEND=real -t signal-alphaagent:real -f runners/alphaagent/Dockerfile .
ARG BACKEND=stub
FROM python:3.12-slim
ARG BACKEND
WORKDIR /opt/runner
COPY runners/common /opt/runner/common
COPY runners/alphaagent/to_package.py /opt/runner/to_package.py
COPY runners/alphaagent/real_backend.py /opt/runner/real_backend.py
COPY runners/alphaagent/runner.py /opt/runner/runner.py
COPY runners/alphaagent/stub_runner.py /opt/runner/stub_runner.py
ENV PYTHONUNBUFFERED=1
ENV SIGNAL_STUB_LOOP_SLEEP=0.5
ENV SIGNAL_RUNNER_BACKEND=${BACKEND}
# real 镜像可在此层 pip install alphaagent / qlib(保持与主平台隔离)
CMD ["python", "/opt/runner/runner.py"]
