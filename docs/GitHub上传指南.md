# 萌新向 GitHub 上传指南（超详细版）

> 面向第一次上传项目的人。每一步都写了「你会看到什么」和「该确认什么」。
> **总耗时**：约 25 分钟（含 10 分钟等 Git 安装、3 分钟等打包）。

**全程路线**（照着顺序做，中途不要跳）：

| 步骤 | 做什么 | 耗时 |
|---|---|---|
| 第 0 步 | 搞清楚数据隐私问题 | 2 分钟 |
| 第 1 步 | 装 Git | 10 分钟 |
| 第 2 步 | GitHub 建空仓库 | 2 分钟 |
| 第 3 步 | 上传前体检（防隐私泄露） | 1 分钟 |
| 第 4 步 | 首次推送代码 | 3 分钟 |
| 第 5 步 | 认证（填 Token） | 2 分钟 |
| 第 6 步 | 验证代码传上去了 | 1 分钟 |
| **第 7 步** | **打包 exe 并发布，让别人能直接下载** | **5 分钟** |
| 第 8 步 | 以后怎么更新 | — |
| 第 9 步 | 报错了查这里 | — |

---

# 第 0 步：先搞清楚三个问题

## Q1：能不能直接把手上的文件夹传上去？

**能。** 你现在运行的文件夹就是完整项目，直接传即可。

但有两点必须先确认：

**① `data/` 文件夹绝对不能传**

这个文件夹里是**你自己的真实数据**：

```
data/tasks.json      ← 你每天记的任务、和助手的每句对话
data/history.json    ← 你过去所有日期的任务归档
data/settings.json   ← 你的昵称、助手名字、主题设置
```

传上去 = 把这些全部公开。所以：

- 项目里已有 `.gitignore`，里面写了 `data/`，Git 会自动跳过
- **但你必须自己验证一次**（第 3 步有专门的检查脚本）

**② 建议先关闭程序再上传**

程序运行时 `data/` 里的文件正被读写。虽然 `.gitignore` 已排除它、理论上不影响，但关掉更稳妥，也能避免"文件被占用"的奇怪报错。

## Q2：程序正在运行，会影响上传吗？

**不影响代码文件。** 只影响 `data/`（已排除）。关掉程序纯粹是图个心安。

## Q3：我本地文件夹里有些东西是后来改的，会有问题吗？

**没问题。** Git 不关心"你什么时候改的"，它只把当前状态打包上传。你改过的代码、加的注释、换的图标，都会原样传上去。

---

# 第 1 步：安装 Git（约 10 分钟）

## 1.1 下载

打开 https://git-scm.com/download/win

浏览器会自动开始下载 64 位安装包（文件名类似 `Git-2.47.1-64-bit.exe`）。

> 如果没自动下载，页面上的 **Click here to download manually** 可以手动选。

## 1.2 安装

双击安装包，**一路点 Next**，中途全部保持默认：

| 安装页面 | 保持默认即可 |
|---|---|
| Select Components | 默认 |
| Default editor | 默认 |
| Initial branch name | 默认 |
| PATH environment | ⚠️ **必须保持 `Git from the command line and also from 3rd-party software`**（默认就是这个） |
| HTTPS transport | 默认 |
| Line ending | 默认 |

最后点 **Install**，等进度条走完，点 **Finish**。

## 1.3 验证安装成功

按键盘 **Win + R**，输入 `cmd`，回车，出现黑色窗口。

输入这一行，回车：

```bash
git --version
```

**你该看到**：

```
git version 2.47.1.windows.1
```

（版本号可能不同，只要有 `git version` 开头就算成功）

**如果看到** `'git' 不是内部或外部命令`：说明安装时 PATH 选项被改了。重新运行安装包，到 **PATH environment** 那页选第一项。

**这个黑窗口别关**，后面全程要用。

---

# 第 2 步：在 GitHub 创建空仓库（约 2 分钟）

## 2.1 登录

打开 https://github.com ，用你的账号登录。没账号先注册（用户名建议用英文，会出现在主页地址里，简历上就写这个）。

## 2.2 新建仓库

点右上角 **+** 号 → **New repository**。

**你该看到**：一个叫 "Create a new repository" 的页面。

依次填写：

| 字段 | 填什么 |
|---|---|
| **Repository name** | `daily-notebook`（建议英文；中文也行但网址会变成编码乱码） |
| **Description** | `聊天式待办管理 · Python + Tkinter 桌面记事本`（可留空） |
| **Public / Private** | 选 **Public**（作品集必须公开才能被看到） |

⚠️ **往下看，找到三个复选框，全部不要勾**：

```
☐ Add a README file
☐ Add .gitignore
☐ Choose a license
```

> **为什么要留空**：你本地已经有一个带提交历史的仓库。如果这里勾了 README，GitHub 会先往仓库塞一个文件，你推送时就会报 `rejected / fetch first` 冲突。萌新最容易卡在这里。

点绿色按钮 **Create repository**。

## 2.3 复制仓库地址

创建后页面跳到仓库主页，地址栏显示：

```
https://github.com/你的用户名/daily-notebook
```

页面中间偏上有个 **Quick setup** 区域，下面有 HTTPS 地址，形如：

```
https://github.com/你的用户名/daily-notebook.git
```

**点右边的小复制图标**，粘贴到记事本存着。第 4.8 步要用。

---

# 第 3 步：上传前体检（重要，别跳）

这一步是防止你把隐私数据传上去。项目里提供了一个检查脚本。

## 3.1 打开项目文件夹

在文件资源管理器里进入项目文件夹（就是有 `main.py` 的那个）。

**确认一下里面有这些**：

```
main.py            ← 主程序
parser.py          ← 解析器
README.md          ← 项目说明
.gitignore         ← 排除规则（关键！）
assets\            ← 图标
启动.bat
上传前体检.bat      ← 体检脚本
```

**如果 `.gitignore` 看不见**（系统隐藏了点开头的文件）：资源管理器顶部 **查看** → 勾选 **隐藏的项目**。

## 3.2 运行体检

双击 **`上传前体检.bat`**。

**正常情况你该看到**：

```
============================================
  上传 GitHub 前的体检
============================================

[检查 1] 隐私文件是否被正确排除...
  [通过] data/ 已被排除（不会上传你的真实任务数据）

[检查 2] dist / build / 缓存 是否被排除...
  [通过]

[检查 3] 关键文件是否齐全...
  [有] main.py
  [有] parser.py
  [有] i18n.py
  [有] README.md
  [有] .gitignore

[检查 4] 本次将上传的文件数量...
  待提交变更：236 项

============================================
  体检完成。全部 [通过] 即可继续上传。
```

## 3.3 如果报「危险」

你会看到：

```
[检查 1] 隐私文件是否被正确排除...
  [危险] data/ 出现在待上传列表里！
```

**立刻停下，不要上传。** 处理方法：

1. 用记事本打开 `.gitignore`，确认里面有单独一行 `data/`
2. 如果没有，手动加上，保存
3. 重新双击 `上传前体检.bat`

---

# 第 4 步：首次推送（核心，约 3 分钟）

回到第 1.3 步那个黑色 cmd 窗口。以下每条命令，**输入后按回车**，等执行完再输下一条。

## 4.1 进入项目文件夹

```bash
cd /d "D:\你的路径\每日记事本"
```

> **把路径换成你自己的。** 怎么找路径：在资源管理器地址栏点一下，路径会变成可复制的文字，复制过来。
>
> ⚠️ 必须带 `/d`，否则跨盘符（比如从 C 盘到 D 盘）切换不过去。

**你该看到**：

```
D:\你的路径\每日记事本>
```

提示符前面变成你的项目路径，说明进对了。

## 4.2 确认文件夹内容

```bash
dir
```

**你该看到**：列出 `main.py`、`parser.py`、`.gitignore`、`assets` 等。

**如果看到** `系统找不到指定的路径`：路径拼错了，重新执行 4.1。

## 4.3 初始化仓库

```bash
git init
git branch -M main
```

**你该看到**：

```
Initialized empty Git repository in D:/你的路径/每日记事本/.git/
```

第二条命令没有输出，是正常的。

> **如果提示** `Reinitialized existing Git repository`：说明之前初始化过，没问题，继续往下。

## 4.4 设置身份（只需一次）

```bash
git config --global user.name "你的名字"
git config --global user.email "你注册GitHub用的邮箱"
```

把引号里换成你自己的。**这两条没有输出，是正常的**。

> 这些信息会写进每条提交记录，是别人看你项目时认识你的方式。

**验证一下**：

```bash
git config --global user.name
```

**你该看到**：你刚才填的名字。

## 4.5 把文件加入待提交清单

```bash
git add .
```

**没有任何输出，就是成功。**（没消息就是好消息）

## 4.6 检查清单（关键一步，别跳）

```bash
git status
```

**你该看到**：

```
On branch main

No commits yet

Changes to be committed:
  (use "git rm --cached <file>..." to unstage)
        new file:   .gitignore
        new file:   README.md
        new file:   main.py
        new file:   parser.py
        ...
        new file:   assets/icon.ico
```

**现在做一件事：在这个列表里找 `data/`。**

- ✅ **找不到 `data/`** → 正常，继续
- ❌ **看到 `data/tasks.json` 之类** → 立刻停下，按 3.3 处理

**列表太长看不完？** 用这条命令只看有没有 data：

```bash
git status --porcelain | findstr "data/"
```

- 没有输出 = 安全
- 有输出 = 危险，停下

## 4.7 提交

```bash
git commit -m "feat: 每日记事本首个版本"
```

**你该看到**：

```
[main (root-commit) a1b2c3d] feat: 每日记事本首个版本
 236 files changed, 25000 insertions(+)
 create mode 100644 main.py
 ...
```

> **如果提示** `Author identity unknown`：说明 4.4 没做成功，回去重做。

## 4.8 关联远程仓库

```bash
git remote add origin https://github.com/你的用户名/daily-notebook.git
```

**把地址换成你在 2.3 复制的那个。** 没有输出 = 成功。

**如果提示** `remote origin already exists`：之前加过，用这条覆盖：

```bash
git remote set-url origin https://github.com/你的用户名/daily-notebook.git
```

## 4.9 推送（这一步会要求登录）

```bash
git push -u origin main
```

接下来会要求认证，见第 5 步。

---

# 第 5 步：登录认证（最容易卡住，务必看完）

GitHub 从 2021 年起**不再接受账号密码**，必须用 **Personal Access Token**（个人访问令牌），相当于一串临时密码。

## 5.1 生成 Token

1. 浏览器打开 https://github.com/settings/tokens
2. 点右上 **Generate new token** → 选 **Generate new token (classic)**
   （如果弹二次验证，按提示输入验证码）
3. 填写：

| 字段 | 填什么 |
|---|---|
| **Note** | `我的电脑` 或任意说明 |
| **Expiration** | 选 `90 days`（安全）或 `No expiration`（省心） |
| **Select scopes** | 勾选第一项 **`repo`**（勾大框即可，子项自动全选） |

4. 拉到页面最底部，点绿色 **Generate token**

## 5.2 复制 Token（只有这一次机会）

页面顶部出现一串字符：

```
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**立刻点右边的复制图标**，粘贴到记事本保存。

> ⚠️ 这个页面**一旦刷新或关闭就再也看不到了**。没存就得重新生成。

## 5.3 回到命令行填写

`git push` 会依次问你：

```
Username for 'https://github.com': 
```

→ 输入你的 **GitHub 用户名**，回车。

```
Password for 'https://你的用户名@github.com': 
```

→ **粘贴 Token**（不是账号密码！），回车。

> **粘贴时屏幕上什么都不会显示**——没有星号、光标也不动。这是正常的，Token 已经粘进去了。直接回车即可。

## 5.4 两种情况

**情况 A：看到推送进度**

```
Enumerating objects: 236, done.
Counting objects: 100% (236/236), done.
Compressing objects: 100% (180/180), done.
Writing objects: 100% (236/236), 3.2 MiB | 1.5 MiB/s, done.
To https://github.com/你的用户名/daily-notebook.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

🎉 **成功！跳到第 6 步。**

**情况 B：弹出了浏览器窗口**

说 "Sign in to GitHub"，这是 Git Credential Manager 在工作。直接在网页上点 **Authorize** 授权，回到命令行会继续推送。**以后推送再也不用输 Token 了**。

---

# 第 6 步：验证上传成功

1. 浏览器打开 `https://github.com/你的用户名/daily-notebook`，刷新

**你该看到**：

- 顶部是 **README 渲染出来的介绍页**，有标题、功能列表、截图
- 文件列表里有 `main.py`、`parser.py`、`assets`、`tests` 等
- **没有 `data` 文件夹**（有的话见第 9 章 Q5）

2. **滚动 README 检查图片**：主界面截图应能正常显示。

3. **加分操作**：点右侧 **About** 旁的 ⚙️ 齿轮，在 **Topics** 里加：

```
python  tkinter  todo  chinese-nlp  desktop-app
```

加了之后别人搜这些词能找到你的项目。

---

# 第 7 步：发布 exe 让别人直接下载（约 5 分钟）

> 做完第 6 步，代码已经在 GitHub 上了。但访客点进来看到的是**源码**，
> 想用得先装 Python、开命令行——这门槛劝退 90% 的人。
> 这一步把打包好的 `每日记事本.exe` 挂到 **Releases**，别人点两下就能用。

## 7.1 先搞清楚：为什么 exe 不进仓库

`每日记事本.exe` 大约 **15–20 MB**，直接提交进仓库有三个问题：

| 问题 | 说明 |
|---|---|
| 仓库暴涨 | 每次打包生成新 exe，Git 会把**每一版**都存下来，几百 MB 很快就堆满 |
| 克隆变慢 | 别人 `git clone` 要下整个历史，包括所有旧 exe |
| 硬性限制 | 单文件超 100 MB，GitHub 直接拒收 |

所以标准做法是——**代码进仓库，成品进 Releases**。Releases 的附件单个最大支持 2 GB，永久保存，还能写更新说明。

> ⚠️ **exe 必须在 Windows 上打包**。Mac / Linux 打不出 Windows 的 exe。
> 手上没有 Windows 电脑？看 7.7 的「自动打包」方案，让 GitHub 的服务器替你打。

## 7.2 在 Windows 上打包

### 前置检查

在项目文件夹里打开 cmd：

```bash
python --version
python -c "import tkinter; print('tkinter ok')"
```

**你该看到**：

```
Python 3.12.1
tkinter ok
```

**报错的话**：去 https://www.python.org/downloads/windows/ 重装，安装时勾选 **Add python.exe to PATH**。别用 Microsoft Store 版本的 Python（缺 tkinter）。

### 执行打包

双击 **`打包.bat`**。它会自动：检查环境 → 安装 PyInstaller（首次需联网，约 1 分钟）→ 打包（1–3 分钟）。

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

最后自动弹出 `dist` 文件夹。

### 打包后必须验一次

双击 `dist\每日记事本.exe`，确认三件事：

- ✅ 能正常启动，界面完整，**图标是新版**
- ✅ 输入一句话能创建任务
- ✅ 关掉程序再打开，**刚才的任务还在**（说明数据能正常存）

**启动就闪退？** 临时把 `每日记事本.spec` 里的 `console=False` 改成 `True`，重新打包，就能在命令行里看到报错了。

## 7.3 创建 Release

### 打开页面

浏览器访问：

```
https://github.com/你的用户名/daily-notebook/releases
```

或者在仓库主页右侧边栏找 **Releases**。

点 **Draft a new release**。

### 填写区 1：Choose a tag

点 **Choose a tag** 下拉框，输入：

```
v1.9.9.15
```

下拉框里会出现 **Create new tag: v1.9.9.15 on publish**，点它。

> **命名规则**：前面带 `v`，数字和 `main.py` 里的 `VERSION` 保持一致，方便对照。
> 以后每次发新版递增：v1.9.9.16、v1.9.9.17……

### 填写区 2：Target

保持默认 `main`。

### 填写区 3：Release title

```
每日记事本 v1.9.9.15
```

或者带上亮点：

```
v1.9.9.15 · 气泡任务条统一宽度
```

### 填写区 4：Describe this release

这是访客最先读的文字。直接复制这个模板改：

```markdown
## 下载

点下方 **Assets** 里的 `每日记事本.exe` 下载，双击即用。

- 免安装、无需 Python、完全离线、无广告
- 系统要求：Windows 10 / 11（64 位）

## 本次更新

- 气泡任务条改为统一宽度，长任务名自动加宽，左右边缘对齐
- 压缩任务名与截止时间之间的空隙
- 新增上传前体检脚本

## 关于杀毒软件误报

本程序用 PyInstaller 打包，可能被个别杀软标记。源码完全公开可查，
如遇误报请添加信任，或直接下载源码自行运行。
```

支持 Markdown（`##` 标题、`-` 列表、`**粗体**`）。

### 填写区 5：Attach binaries（关键一步）

页面底部有个虚线框写着：

```
Attach binaries by dropping them here or selecting them.
```

**两种方式任选**：

- 用鼠标把 `dist\每日记事本.exe` **拖进**那个框
- 或点框里的 **selecting them**，在文件对话框里选中它

**你该看到**：进度条走完，框里显示文件名和大小（约 15–20 MB）。

> ⚠️ **上传期间别关页面**。传完刷新发现附件没了，说明没传成功，重来一次。

### 发布

确认下面几项，然后点页面底部绿色按钮 **Publish release**：

- [ ] tag 是 `v1.9.9.15`（带 v）
- [ ] 标题填了
- [ ] 说明填了，且写清了「下载哪个文件」
- [ ] 虚线框里能看到 exe，大小正常

没准备好可以先点 **Save draft** 存草稿，之后再回来发。

## 7.4 验证发布成功

发布后跳到 Release 详情页，检查：

- 顶部显示 `v1.9.9.15`，旁边有绿色 `Latest` 标签
- 中间是你写的说明（已渲染成排版）
- 底部 **Assets** 区域列出：

```
Source code (zip)
Source code (tar.gz)
每日记事本.exe        18.2 MB
```

**用无痕窗口**（Ctrl+Shift+N）打开这个页面，点一下 exe 下载，确认能下、能跑。这一步是为了确认「陌生人」也能拿到文件。

## 7.5 把下载链接写进 README（必做）

不做这步，访客根本找不到 Releases。在 `README.md` **最顶部**加一段：

```markdown
## 下载

**[⬇ 下载 Windows 免安装版](../../releases/latest)**

解压后双击 `每日记事本.exe` 即可，无需安装 Python。
```

> 注意用的是**相对路径** `../../releases/latest`，它永远指向最新版本，
> 以后发新版**完全不用改 README**。

改完推送：

```bash
git add README.md
git commit -m "docs: 添加下载链接"
git push
```

刷新仓库首页，顶部应该出现一个可点击的下载链接。

## 7.6 以后发新版的流程

每次改完代码，重复这四步（约 5 分钟）：

```bash
# ① 推代码
git add .
git commit -m "feat: 新功能说明"
git push
```

```bash
# ② 改版本号
#   main.py 里          VERSION = "1.9.9.16"
#   version_info.txt 里 1, 9, 9, 16
```

```
③ 双击 打包.bat，重新打包
```

```
④ 打开 releases/new，tag 填 v1.9.9.16，拖入新 exe，Publish
```

> **省事技巧**：在旧 Release 页点 **Edit**，改版本号和说明，重新传文件也行；但从新建页面走更规范。

## 7.7 没有 Windows 电脑怎么办

### 方案 A：GitHub Actions 自动打包（推荐，已配好）

项目里已经有 `.github/workflows/build-windows.yml`，推到 GitHub 后自动生效：

**触发方式一：打 tag**
```bash
git tag v1.9.9.16
git push --tags
```
GitHub 会用 Windows 服务器自动打包，并**自动创建 Release、自动上传 exe**。你什么都不用做。

**触发方式二：手动**
仓库 **Actions** 标签页 → 左侧选「打包 Windows EXE」→ 右侧 **Run workflow** → 跑完在页面底部 Artifacts 里下载 exe。

> 首次运行如果报权限错误，去仓库 **Settings** → **Actions** → **General** → 底部 **Workflow permissions** 选 **Read and write permissions**，保存后重跑。

### 方案 B：找朋友代打

把项目 zip 发给有 Windows 的朋友，让他双击 `打包.bat`，把 `dist\每日记事本.exe` 发回给你。

### 方案 C：先只发源码

README 里写清「需要 Python 3.10+，双击 `启动.bat`」。门槛高些，但完全合法，很多 Python 项目都这样。

## 7.8 常见问题

**Q：Release 页面找不到 Attach binaries 那个框**

页面往下滚到底。或者换 Chrome / Edge 浏览器（有些老浏览器拖拽上传不工作）。

**Q：exe 传上去下载后文件名变成 `%E6%AF%8F...`**

GitHub 对中文附件名的处理问题。介意的话，打包后把 exe 改名为 `DailyNotebook.exe` 再上传，或者打个 zip 一起传。

**Q：杀毒软件报毒 / Windows Defender 拦截**

PyInstaller 打包程序的常见现象（未签名 + 自解压特征）。`每日记事本.spec` 里已设 `upx=False`，能显著降低误报。在 Release 说明里加一句解释（模板里已写）即可。彻底解决要买代码签名证书（一年几百上千元），个人项目没必要。

**Q：想更新已发布的 Release 里的 exe**

进 Release 页点 **Edit release**，在 Attach binaries 区域删除旧文件、拖入新的，点 **Update release**。

**Q：不小心发错版本号了**

Release 页点 **Edit** → 改 tag（会同步改 tag 名）→ Update release。或者删掉这个 Release 和对应 tag 重来。

---

# 第 8 步：以后改了代码怎么更新

## 8.1 三条命令的节奏

在项目文件夹里打开 cmd（地址栏输入 `cmd` 回车），执行：

```bash
git add .
git commit -m "fix: 修复了xxx问题"
git push
```

就这么简单。**改代码 → add → commit → push**。

> 不需要再写 `-u origin main`，第一次已建立关联。

## 8.2 写提交说明的建议

`-m` 后面的文字会永久留在项目历史里，别写 "1"、"update"、"修改"。

| 类型 | 示例 |
|---|---|
| 新功能 | `feat: 添加任务搜索功能` |
| 修 bug | `fix: 修复气泡任务条宽度不一致` |
| 文档 | `docs: 更新使用说明` |
| 样式 | `style: 调整按钮间距` |

## 8.3 提交节奏

**每完成一个小功能或修完一个 bug 就提交一次**。这样提交历史就是一份开发日记，看的人能理解你每一步在做什么。

## 8.4 发布可下载的 exe

exe 有几十 MB，不适合直接进仓库。用 **Releases** 发布：

1. Windows 上运行 `打包.bat`，得到 `dist\每日记事本.exe`
2. 仓库页右侧 → **Releases** → **Draft a new release**
3. **Choose a tag** 输入 `v1.9.9.13` → 点 **Create new tag**
4. 填标题，把 exe（或整个 zip）拖到 **Attach binaries** 区域
5. 点 **Publish release**

用户就能在 Releases 页面直接下载，不用装 Python。

---

# 第 9 步：常见问题排错

## 认证类

**Q1：`Authentication failed` / `Invalid username or password`**

Token 错了或过期了。两个办法：

- 重新生成 Token（5.1 步），再推送
- 或先清旧凭据：控制面板 → 凭据管理器 → Windows 凭据 → 找到 `git:https://github.com` → 删除，再 `git push`

**Q2：`Support for password authentication was removed`**

你输的是账号密码，不是 Token。回到第 5 步，用 `ghp_` 开头的 Token。

## 推送冲突类

**Q3：`! [rejected] main -> main (fetch first)`**

远程已有不属于你的文件（通常是建仓库时勾了 README）。执行：

```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```

> 中间如果弹出编辑器（黑屏带波浪号），是让你写合并说明。按 `Esc`，输入 `:wq`，回车即可退出。

**Q4：`failed to push some refs` / `remote contains work you do not have`**

同 Q3。

## 隐私类

**Q5：我不小心把 `data/` 推上去了，里面有我的真实任务！**

立刻执行：

```bash
git rm -r --cached data
git commit -m "chore: 移除 data 目录"
git push
```

仓库里不再显示它，**但历史版本里仍然存在**（别人翻旧提交还能看到）。

如果已经公开且很在意：最干净的做法是仓库 **Settings** → 拉到最底 **Delete this repository** 删掉整个仓库，确认 `.gitignore` 有 `data/` 后重新走第 4 步。

## 环境类

**Q6：`'git' 不是内部或外部命令`**

Git 没装或没加进 PATH。重装 Git，PATH 那页保持默认第一项。

**Q7：`git commit` 报 `Author identity unknown`**

没配置身份。执行 4.4 步的两条 `git config` 命令。

**Q8：`cd` 之后说 `系统找不到指定的路径`**

路径有误。用资源管理器地址栏复制完整路径，记得加 `/d`：

```bash
cd /d "D:\项目\每日记事本"
```

**Q9：中文文件名显示成 `\346\257\217...` 乱码**

执行一次即可修复：

```bash
git config --global core.quotepath false
```

**Q10：推送很慢 / 卡住 / `Connection timed out`**

国内访问 GitHub 不稳定。有代理软件的话给 Git 挂上：

```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

把 `7890` 换成你代理软件的端口（Clash 一般 7890，v2ray 一般 10809）。

取消代理：

```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

## 显示类

**Q11：README 里的图片显示成裂图**

路径大小写必须和实际文件名完全一致（GitHub 区分大小写）。本项目图片在 `screenshots/` 下，README 里写的是 `screenshots/xxx.png`。重命名了图片就要同步改 README。

**Q12：`warning: LF will be replaced by CRLF`**

只是换行符格式提醒，**无害，忽略即可**。

---

# 第 10 步：推送前最后检查清单

全部打勾再按 `git push`：

- [ ] Git 装好了，`git --version` 有输出
- [ ] GitHub 建好了空仓库，**三个初始化选项都没勾**
- [ ] 项目文件夹里有 `.gitignore`，且里面有 `data/`
- [ ] `上传前体检.bat` 全部显示 `[通过]`
- [ ] `git status` 的列表里**没有** `data/`
- [ ] `git config user.name` 和 `user.email` 都填了
- [ ] Token 已生成并存进记事本
- [ ] 程序已关闭（可选，但推荐）

**第 7 步（发布 exe）发布前：**

- [ ] 代码已经 `git push` 上去了（tag 要从提交上打）
- [ ] `dist\每日记事本.exe` 已生成，双击能正常运行
- [ ] exe 图标是新版、任务能存住（关掉重开还在）
- [ ] Release 的 tag 写成 `v版本号`（带 v，与 VERSION 一致）
- [ ] 说明里写清了「下载哪个文件、怎么用」
- [ ] exe 已拖进 Attach binaries 且大小正常（15–20 MB）
- [ ] 点了 **Publish release**（不是草稿）
- [ ] 用无痕窗口试下载，确认陌生人也能拿到
- [ ] README 顶部有 `../../releases/latest` 下载链接

---

# 附：全部命令速查表

```bash
# —— 首次上传 ——
cd /d "D:\你的路径\每日记事本"        # 进入项目
git init                              # 初始化
git branch -M main                    # 主分支命名
git config --global user.name "名字"   # 设置身份（一次）
git config --global user.email "邮箱"  # 设置邮箱（一次）
git add .                             # 加入清单
git status                            # 检查（确认无 data/）
git commit -m "feat: 首次提交"        # 提交
git remote add origin <仓库地址>       # 关联远程
git push -u origin main               # 推送

# —— 日常更新 ——
git add .
git commit -m "fix: 说明"
git push

# —— 查看状态 ——
git status                            # 当前有哪些改动
git log --oneline                     # 提交历史
git remote -v                         # 远程地址

# —— 打包与发布 ——
python --version                      # 确认 Python 可用
python -c "import tkinter; print('ok')"   # 确认 tkinter 可用
（双击 打包.bat）                      # 生成 dist\每日记事本.exe
git tag v1.9.9.16                     # 打版本标签
git push --tags                       # 推标签（触发 Actions 自动出包）

# —— 常用修复 ——
git config --global core.quotepath false   # 中文不乱码
git rm -r --cached data                    # 误提交 data 后移除
```
