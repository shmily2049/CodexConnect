#!/bin/sh
set -eu
contents_dir="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
resources_dir="$contents_dir/Resources"
runtime_python="$resources_dir/runtime/python/bin/python3.12"
hardware="$(/usr/bin/uname -m)"
if [ "$hardware" != "x86_64" ]; then
  /usr/bin/osascript -e 'display alert "版本与芯片不匹配" message "请从关于本机确认芯片类型，并下载 Apple 芯片版或 Intel 版。无需安装 Python。" as critical'
  exit 1
fi
if [ ! -x "$runtime_python" ]; then
  /usr/bin/osascript -e 'display alert "应用不完整" message "请使用 macOS 自带的归档实用工具完整解压 ZIP，再打开应用。" as critical'
  exit 1
fi
exec "$runtime_python" -I -B "$resources_dir/bootstrap.py" "$@"
