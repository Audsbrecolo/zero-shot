# 单张论文图的 CPU 推理环境

## 用实际验证过的量化服务运行

此入口可在 Linux CPU 上运行，也可以连接已有的视觉模型服务。客户端只依赖 Pillow 与 NumPy。以下命令适用于 Linux x86-64，使用两个终端，两者都从仓库根目录开始。在有磁盘空间的位置保存约 6.2 GB 的模型与视觉投影文件。CPU 推理耗时可能达到数分钟一张。

**终端一**下载模型、启动服务，并保持窗口打开。此处使用验证时的 llama.cpp b8219。视觉投影文件负责把图片送入模型，两份 GGUF 文件需要配套使用。

```bash
mkdir -p .local-model
cd .local-model
curl -fL --retry 2 -o llama.tar.gz https://github.com/ggml-org/llama.cpp/releases/download/b8219/llama-b8219-bin-ubuntu-x64.tar.gz
tar -xzf llama.tar.gz
curl -fL --retry 2 -o qwen8.gguf https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/b93a7ee713758252c555be4210c00540df954dc2/Qwen3-VL-8B-Instruct-Q4_K_M.gguf
curl -fL --retry 2 -o mmproj8.gguf https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/b93a7ee713758252c555be4210c00540df954dc2/mmproj-F16.gguf
./llama-b8219/llama-server -m qwen8.gguf --mmproj mmproj8.gguf --alias Qwen/Qwen3-VL-8B-Instruct --ctx-size 4096 --no-repack --cache-ram 0 -ub 128 -np 1 --host 127.0.0.1 --port 8000
```

**终端二**运行检测。若服务使用其他端口或模型别名，用 `--base-url http://127.0.0.1:端口/v1` 和 `--model 服务里的模型别名` 指定。客户端会把全图预览和局部裁剪发到这个地址。默认地址是本机。连接有鉴权的服务时，通过环境变量 `SCI_IMAGE_API_KEY` 设置密钥。

```bash
python -m pip install -r requirements-image.txt
python detect.py "real/experiment figure/2308.14409_fig4.png" --backend api --out results/line-chart.json
```
