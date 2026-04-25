# Image Lab

第三方 API 使用的生图网页组件。

![第三方 API 使用的生图网页组件](assets/third-party-api-image-lab.png)

## 功能

- 单页出图工作台，支持文生图、图生图、历史记录、下载和浏览器图片缓存。
- 首次进入时设置访问密码、出图 URL、出图 Key、图像模型。
- 进入后点击工具栏的“设置”按钮，可修改 URL、Key、模型、Provider 和访问密码。
- 生成时显示约 60 秒的细进度条，用作伪倒计时。
- 支持常用比例，包括 `9:21` 手机长屏。

## 本地启动

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

## 可选环境变量

```powershell
$env:IMAGE_LAB_BASE_URL="https://api.jucode.cn/v1"
$env:OPENAI_API_KEY="你的 key"
$env:IMAGE_LAB_PROVIDER="jucode"
$env:IMAGE_LAB_IMAGE_MODEL="gpt-image-2"
```

环境变量只是默认值。页面首次设置或“设置”弹窗中填写的 URL、Key、模型会保存到当前浏览器缓存，并优先生效。

## 目录

- `image-lab.html`：前端单页。
- `image_lab_server.py`：独立 Python 服务，提供页面、API 转发和本地文件下载。
- `assets/third-party-api-image-lab.png`：说明图。
- `output/`：运行后生成的图片目录，已被 `.gitignore` 忽略。
