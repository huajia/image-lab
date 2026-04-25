# Image Lab

Image Lab 是一个独立的第三方 API 生图网页组件。它把一个单页前端和一个轻量 Python 服务打包在一起，可以直接对接 OpenAI 兼容的第三方图片接口，用来做文生图、图生图、批量组图、历史缓存和下载。

## 预览

![第三方 API 使用的生图网页组件](./assets/third-party-api-image-lab.png)

![日本幕府雨中动态示例](./assets/samurai-rain-demo.png)

## 适合什么场景

- 你有一个 OpenAI 兼容的第三方 API URL 和 Key，想快速做一个可用的出图页面。
- 你想把 URL、Key、模型交给浏览器本地保存，而不是写死在后端配置里。
- 你需要一个轻量工具支持文生图、图生图、历史记录、图片下载和服务端保存。
- 你想把它部署成一个单独的小服务，不依赖原项目后端。

## 功能

- 首次进入时设置访问密码、出图 URL、出图 Key、图像模型。
- 第二次进入只需要输入访问密码，不会再次要求填写 Key。
- 登录后工具栏有“设置”按钮，可修改 URL、Key、模型、Provider 和访问密码。
- 设置会保存到当前浏览器的 `localStorage`，刷新页面后仍然保留。
- 登录状态保存到当前浏览器会话的 `sessionStorage`，关闭会话后需要重新输入密码。
- 生成时显示约 60 秒的细进度条。倒计时走完后会保留一小段“收尾中”状态，直到真正出图或失败才消失。
- 支持 `16:9`、`9:21`、`9:16`、`1:1`、`4:3`、`3:4`、`3:2`、`2:3`、`21:9` 等比例。
- 支持服务端保存图片，生成文件默认写入 `output/`。

## 快速启动

在本目录运行：

```powershell
$env:IMAGE_LAB_ROOT=(Get-Location).Path
$env:IMAGE_LAB_HOST="127.0.0.1"
$env:IMAGE_LAB_PORT="28081"
python .\image_lab_server.py
```

打开：

```text
http://127.0.0.1:28081/image-lab.html
```

也可以直接运行：

```powershell
.\start.ps1
```

## 首次配置

第一次打开页面时，需要填写：

- 访问密码
- 出图 URL，例如 `https://api.jucode.cn/v1`
- 出图 Key
- 图像模型，例如 `gpt-image-2`

URL 可以填 `https://api.jucode.cn`，页面会自动补成 `https://api.jucode.cn/v1`。

## 后续修改

进入页面后点击工具栏的“设置”按钮，可以修改：

- 出图 URL
- 出图 Key
- 图像模型
- Provider 名称
- 访问密码

新密码留空表示不修改密码。

## 可选环境变量

环境变量只作为默认值。浏览器里保存的设置优先级更高。

```powershell
$env:IMAGE_LAB_BASE_URL="https://api.jucode.cn/v1"
$env:OPENAI_API_KEY="你的 key"
$env:IMAGE_LAB_PROVIDER="jucode"
$env:IMAGE_LAB_IMAGE_MODEL="gpt-image-2"
$env:IMAGE_LAB_RESPONSE_MODEL="gpt-5.2"
```

## 缓存说明

浏览器会保存：

- `imageLabPasswordHash`：访问密码的哈希，不保存明文密码。
- `imageLabSettings`：URL、Key、模型、Provider 等设置。

图片历史和可选的图片数据会保存到浏览器 IndexedDB。清理浏览器站点数据会清除这些信息。

## 文件结构

- `image-lab.html`：前端单页。
- `image_lab_server.py`：独立 Python 服务，提供页面、API 转发、图片保存和下载。
- `assets/third-party-api-image-lab.png`：说明图。
- `assets/samurai-rain-demo.png`：示例图。
- `start.ps1`：Windows PowerShell 启动脚本。
- `.env.example`：环境变量示例。
- `output/`：生成图片目录，已被 `.gitignore` 忽略。

## 注意

不要把真实 API Key 写进仓库。建议在页面首次配置或“设置”弹窗里填写 Key，或者只在本机运行时通过环境变量注入。
