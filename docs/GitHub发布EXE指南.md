# 发布 EXE 让别人直接下载（不用装 Python）

> 目标：让访客在 GitHub 上点两下就能拿到能用的 `每日记事本.exe`，不需要装 Python、不需要看命令行。
>
> **前提**：exe 只能在 **Windows** 上打包。如果你手上没有 Windows 电脑，跳到最后一节「替代方案」。

---

# 一、先理解两件事

## 1.1 为什么 exe 不能放进仓库

`每日记事本.exe` 大概 **15–20 MB**，问题有三个：

| 问题 | 说明 |
|---|---|
| 仓库变大 | 每次打包都生成新的 exe，Git 会存下**每一版**，几百 MB 很快就堆起来了 |
| 克隆变慢 | 别人 `git clone` 要下整个历史，包括所有旧 exe |
| GitHub 限制 | 单文件超 100 MB 直接拒收 |

所以：**exe 走 Releases，代码走仓库**。这是所有开源项目的标准做法。

## 1.2 Releases 是什么

仓库页右侧的一个专区，可以挂"版本 + 说明 + 附件文件"。访客点进去看到：

- 版本号（v1.9.9.14）
- 更新说明（这次改了什么）
- 下载链接（`每日记事本.exe` 或 `每日记事本-v1.9.9.14.zip`）

GitHub 会永久保存这些附件，且**支持大文件**（单个最大 2 GB）。

---

# 二、在 Windows 上打包 exe（约 3 分钟）

## 2.1 前置检查

需要 Python 3.10 以上，且装了 tkinter。

打开 cmd 执行：

```bash
python --version
python -c "import tkinter; print('tkinter ok')"
```

**你该看到**：

```
Python 3.12.1
tkinter ok
```

**如果报错**：去 https://www.python.org/downloads/windows/ 重装，安装时勾选 **Add python.exe to PATH**，并且不要用 Microsoft Store 版本（那个缺 tkinter）。

## 2.2 打包

在项目文件夹里双击 **`打包.bat`**。

它会自动做三件事：

1. 检查 Python 和 tkinter
2. 安装/更新 PyInstaller（首次需联网，约 1 分钟）
3. 打包（约 1–3 分钟）

**你该看到**：

```
[1/2] 安装 / 更新 PyInstaller（首次需要联网，请稍等）...
[2/2] 正在打包，约需 1~3 分钟...
...
============================================
  打包完成！
  EXE 位置：dist\每日记事本.exe
============================================
```

最后会自动弹出 `dist` 文件夹。

## 2.3 验证 exe 能用

双击 `dist\每日记事本.exe`：

- ✅ 能正常启动、界面完整、图标是新版
- ✅ 新建一个任务，然后关掉再打开，任务还在（说明数据能存）

**如果启动就闪退**：用 cmd 运行它看报错：

```bash
cd /d "你的路径\每日记事本\dist"
每日记事本.exe
```

（注意：因为是窗口程序，报错可能不显示。可以临时把 `每日记事本.spec` 里的 `console=False` 改成 `True` 重新打包，就能看到报错了。）

## 2.4 顺便清理一下

打包会生成：

```
dist\每日记事本.exe     ← 要发布的，留着
build\                  ← 临时文件，可以删
每日记事本.spec          ← 打包配置，仓库里已有，不用动
```

---

# 三、把 exe 传到 GitHub Releases

## 3.1 先确认代码已推送

如果代码还没传上去，先按 `docs/GitHub上传指南.md` 完成首次推送。

**为什么先推代码**：Release 是挂在某个 tag 上的，tag 又是从某次提交打的。代码没推，tag 也发不出去。

## 3.2 进入 Releases 页面

浏览器打开你的仓库，比如：

```
https://github.com/你的用户名/daily-notebook
```

看右侧边栏（About 区域下方），找到 **Releases**，点它。

或者直接访问：

```
https://github.com/你的用户名/daily-notebook/releases
```

## 3.3 创建新 Release

点 **Draft a new release** 按钮。

**你该看到**：一个表单，从上到下有几个填写区。

### 填写区 1：Choose a tag

点 **Choose a tag** 下拉框，输入版本号：

```
v1.9.9.14
```

输入后下拉框里会出现 **Create new tag: v1.9.9.14 on publish**，点它。

> **版本号规则**：前面必须带 `v`，和程序里的 `VERSION` 保持一致，方便对照。以后每次发新版就递增（v1.9.9.15、v1.9.9.16...）。

### 填写区 2：Target

保持默认 `main`。

### 填写区 3：Release title

填一个给人看的标题，比如：

```
每日记事本 v1.9.9.14
```

或者更吸引人的：

```
v1.9.9.14 · 气泡任务条统一宽度
```

### 填写区 4：Describe this release

这是更新说明，访客最先看到的内容。建议模板：

```markdown
## 下载

- **Windows 免安装版**：下载下方的 `每日记事本.exe`，双击即用
- **源码版**：下载 `Source code (zip)`，需自行安装 Python

## 本次更新

- 气泡任务条改为统一宽度，长任务名自动加宽，左右边缘对齐
- 压缩任务名与截止时间之间的空隙
- 新增上传前体检脚本

## 系统要求

- Windows 10 / 11（64 位）
- 免安装、无需 Python、完全离线、无广告
```

支持 Markdown 语法（`##` 标题、`-` 列表、`**粗体**`）。

### 填写区 5：Attach binaries（关键）

页面底部有个虚线框，写着：

```
Attach binaries by dropping them here or selecting them.
```

**两种方式**：

- 用鼠标把 `dist\每日记事本.exe` **拖进**那个框
- 或点框里的 **selecting them**，在文件对话框里选到 `dist\每日记事本.exe`

**你该看到**：一个上传进度条，几秒到几十秒（看网速）。完成后框里显示文件名和大小。

> ⚠️ **上传期间别关页面**。传完后如果刷新页面发现附件没了，说明没传成功，重传一次。

### 3.4 发布

确认以下几点后，点页面底部的绿色按钮 **Publish release**：

- [ ] tag 是 `v1.9.9.14`
- [ ] 标题填了
- [ ] 说明填了（至少写了"下载哪个文件"）
- [ ] exe 已经显示在上传框里，大小约 15–20 MB

> 如果没准备好，可以点 **Save draft** 存草稿，之后再回来发布。

## 3.5 验证

发布后会跳到 Release 详情页。检查：

- 页面顶部显示 `v1.9.9.14` 和 `Latest` 标签
- 中间是你写的更新说明（Markdown 已渲染）
- 底部 **Assets** 区域列着：

```
Source code (zip)
Source code (tar.gz)
每日记事本.exe        18.2 MB
```

**重要**：把 `每日记事本.exe` 的下载链接**复制下来**，形如：

```
https://github.com/你的用户名/daily-notebook/releases/download/v1.9.9.14/每日记事本.exe
```

（中文文件名会被转义，正常现象）

## 3.6 把下载链接写进 README（强烈建议）

访客打开仓库首页，第一眼该看到"怎么下载"。在 `README.md` 顶部加一段：

```markdown
## 下载

**[⬇ 下载 Windows 免安装版](https://github.com/你的用户名/daily-notebook/releases/latest)**

解压后双击 `每日记事本.exe` 即可，无需安装 Python。
```

> 用 `/releases/latest` 这个地址，它永远指向最新版本，以后出新版**不用改 README**。

改完执行：

```bash
git add README.md
git commit -m "docs: 添加下载链接"
git push
```

---

# 四、以后发新版的流程

每次改完代码，重复这套动作（约 5 分钟）：

```bash
# 1. 改完代码，先推代码
git add .
git commit -m "feat: 新功能说明"
git push

# 2. 改版本号（可选但推荐）
#    main.py 里的 VERSION = "1.9.9.15"
#    version_info.txt 里的 1, 9, 9, 15

# 3. 重新打包
#    双击 打包.bat

# 4. 去 GitHub 建新 Release
#    https://github.com/你的用户名/daily-notebook/releases/new
#    tag 填 v1.9.9.15
#    拖入新的 exe
#    点 Publish release
```

> **小技巧**：Releases 页面右上角有个 **Draft a new release**，也可以从上一个 Release 点 **Edit** 复制说明改改，省事。

---

# 五、进阶优化（可选）

## 5.1 让 exe 带上版本号信息

`version_info.txt` 已经配好了。只要打包前把里面的版本号改成和 `main.py` 的 `VERSION` 一致：

```python
filevers=(1, 9, 9, 14),
prodvers=(1, 9, 9, 14),
StringStruct('FileVersion', '1.9.9.14.0'),
StringStruct('ProductVersion', '1.9.9.14.0'),
```

打包后，右键 exe → 属性 → 详细信息，就能看到版本号了。

## 5.2 附带一个说明文件

如果怕用户不知道怎么用，可以打包一个 zip 一起传：

```
每日记事本-v1.9.9.14-win64.zip
├── 每日记事本.exe
├── 使用说明.md
└── assets/icon.ico
```

在 Releases 里**同时传 exe 和 zip**，用户自己选。

## 5.3 杀毒软件误报怎么办

PyInstaller 打包的 exe 偶尔会被某些杀软标记（因为"未签名 + 自解压"的特征）。

应对：

1. **在 Release 说明里写清楚**：本程序由 PyInstaller 打包，开源代码可查，如报毒请加白名单
2. **不要用 UPX 压缩**（`每日记事本.spec` 里已设 `upx=False`，这是对的，能显著降低误报）
3. 真要彻底解决，需要买代码签名证书（一年几百到上千元），个人项目一般没必要

## 5.4 加个绿色"通过"徽章（好看但非必需）

README 顶部加：

```markdown
![version](https://img.shields.io/badge/version-1.9.9.14-yellow)
![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-green)
```

显示成一排小标签，看起来更像正经项目。

---

# 六、没有 Windows 电脑怎么办

如果你只有 Mac 或 Linux，有三个选择：

## 方案 A：用 GitHub Actions 自动打包（免费、推荐）

让 GitHub 的服务器（Windows 环境）替你打包。在项目里建一个文件：

`.github/workflows/build.yml`

```yaml
name: Build Windows EXE

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install PyInstaller
        run: pip install pyinstaller

      - name: Build
        run: pyinstaller --noconfirm --clean 每日记事本.spec

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: 每日记事本-windows
          path: dist/每日记事本.exe
```

推送这个文件后，每次打 tag（`git tag v1.9.9.14 && git push --tags`）GitHub 会自动打包，产物在仓库 **Actions** 页可以下载。

需要的话我可以帮你把这个文件配好，并加上"自动发布到 Release"的步骤。

## 方案 B：找朋友代打

把项目 zip 发给有 Windows 的同事/朋友，让他双击 `打包.bat`，把 `dist\每日记事本.exe` 发回给你。

## 方案 C：先只发源码

在 README 里写清楚"需要 Python 3.10+，双击 `启动.bat`"。虽然门槛高一点，但也是合法做法，很多 Python 项目就是这样。

---

# 七、检查清单

发布前过一遍：

**打包阶段**
- [ ] Windows 上 `python --version` 正常，`tkinter ok`
- [ ] `打包.bat` 跑完，`dist\每日记事本.exe` 存在
- [ ] 双击 exe 能启动，图标是新版
- [ ] 新建任务 → 关闭 → 重开，数据还在

**仓库阶段**
- [ ] 代码已经 `git push` 到 GitHub
- [ ] `data/` 没有被上传（`git status` 确认过）

**Release 阶段**
- [ ] tag 填的是 `v1.9.9.14`（带 v）
- [ ] 标题和更新说明填了
- [ ] 说明里写清了"下载哪个文件、怎么用"
- [ ] exe 已上传并显示大小
- [ ] 点了 Publish release（不是草稿状态）

**发布后**
- [ ] 用无痕窗口打开 Release 页，确认能下载
- [ ] 下载下来能正常运行
- [ ] README 顶部有下载链接（用 `/releases/latest`）
