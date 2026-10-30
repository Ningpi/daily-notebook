# 萌新向 GitHub 上传指南

> 目标读者：第一次把项目上传到 GitHub 的人。
> 按顺序做完第一~五章，项目就上线了；第六章是以后改代码后的日常操作；第七章收集了所有常见报错的解决办法。

---

## 一、上传前要准备什么

### 1.1 这个项目会上传哪些文件

上传时**整个项目文件夹**都会进仓库，除了被 `.gitignore` 排除的内容。最终仓库内容：

| 内容 | 是否上传 | 说明 |
|---|---|---|
| `main.py`、`parser.py`、`parser_en.py`、`i18n.py`、`themes.py`、`quotes.py`、`holidays.py` | ✅ | 源代码，项目核心 |
| `assets/`（图标） | ✅ | 程序运行需要 |
| `screenshots/`（15 张精选截图） | ✅ | README 展示用，已裁掉黑边 |
| `tests/`、`docs/` | ✅ | 自动化测试与设计文档 |
| `README.md`、`使用说明.md`、`Windows使用指南.md` | ✅ | 说明文档 |
| `打包.bat`、`每日记事本.spec` | ✅ | Windows 打包脚本与配置 |
| `.gitignore` | ✅ | 告诉 Git 哪些文件不要上传 |
| ~~`data/`~~ | ❌ | **你的真实任务和个人数据，绝不上传** |
| ~~`build/`、`dist/`、`__pycache__/`~~ | ❌ | 打包产物和缓存，几 MB 且随时可重新生成 |
| ~~`*.zip`~~ | ❌ | 发布压缩包，改用 GitHub Releases 发布 |

> ⚠️ **最重要的一条**：`data/` 文件夹里是你自己每天记的任务、聊的每一句话、你的昵称。上传 = 公开个人隐私。本项目的 `.gitignore` 已把它排除，但你如果日后改过 `.gitignore`，推送前务必用 `git status` 确认它没出现在待上传列表里。

### 1.2 需要安装的软件

只需一个：**Git**。

1. 到 https://git-scm.com/download/win 下载安装包
2. 一路点 Next 默认安装即可（默认选项都合理）
3. 验证：按 `Win + R`，输入 `cmd` 回车，在黑窗口里输入：

```bash
git --version
```

显示 `git version 2.x.x` 即安装成功。

**GitHub 账号**：没有的话去 https://github.com 注册，用户名建议用英文（会出现在你的主页地址 `github.com/用户名` 里，以后简历上就写这个）。

---

## 二、在 GitHub 网站上创建空仓库

1. 登录 GitHub，点右上角 **+** → **New repository**
2. 填写：
   - **Repository name**：`daily-notebook`（建议英文；想用中文也可以，但网址会变成 `每日记事本` 的编码形式，不美观）
   - **Description**：`聊天式待办管理 · Python + Tkinter 桌面记事本`（一句话简介，会显示在仓库标题下）
   - 选择 **Public**（公开——作品集必须公开才能被看到；之后随时可在 Settings 里改）
3. ⚠️ **三个选项全都不要勾**：
   - ❌ Add a README file
   - ❌ Add .gitignore
   - ❌ Choose a license

   （本地项目里已经有了，勾了会跟本地冲突，推送时报错，萌新最容易被这一步卡住）
4. 点绿色按钮 **Create repository**
5. 创建后页面会显示一个地址，复制下来，形如：

```
https://github.com/你的用户名/daily-notebook.git
```

---

## 三、首次推送（核心步骤，共 5 条命令）

打开命令行（`Win + R` → `cmd`），逐条执行。

### 3.1 进入项目文件夹

```bash
cd C:\你的路径\每日记事本
```

> 小技巧：在文件夹里按住 `Shift` 点鼠标右键，选「在此处打开 PowerShell 窗口」，就不用手动 cd 了。

### 3.2 初始化本地仓库

```bash
git init
git branch -M main
```

- `git init`：把这个文件夹变成 Git 仓库（会生成一个隐藏的 `.git` 文件夹，别删它）
- `git branch -M main`：把主分支命名为 `main`（GitHub 的默认叫法）

### 3.3 告诉 Git 你是谁（只需要做一次）

```bash
git config --global user.name "你的名字"
git config --global user.email "你注册GitHub用的邮箱"
```

> 名字和邮箱会写进每条提交记录里，是别人看你项目时认识你的方式。邮箱建议用 GitHub 注册邮箱。

### 3.4 打包快照

```bash
git add .
git status
```

- `git add .`：把当前目录所有文件（`.gitignore` 排除的除外）放进"待上传清单"
- `git status`：**查看清单**。执行后仔细看输出——确认 `data/` 文件夹**没有**出现在列表里。出现了就说明 `.gitignore` 有问题，先别往下走

### 3.5 提交

```bash
git commit -m "feat: 每日记事本首个版本"
```

- 这一步是存进**本地**的版本库，还没传上网
- `-m` 后面是提交说明，写清楚这次干了什么，别偷懒写 "1" 或 "update"

### 3.6 关联远程仓库并推送

```bash
git remote add origin https://github.com/你的用户名/daily-notebook.git
git push -u origin main
```

- 第一条：告诉本地仓库"要传到 GitHub 的这个地址"，**只需执行一次**
- 第二条：真正上传。`-u` 是建立关联，以后再推送只需 `git push`

执行 `git push` 后会弹出认证窗口（见下一章）。

---

## 四、登录认证（最容易卡住的一步）

GitHub 从 2021 年起**不再接受账号密码**，必须用 **Personal Access Token（个人访问令牌）**，相当于一串临时密码。

### 4.1 生成 Token

1. GitHub 右上角点头像 → **Settings**
2. 左侧栏拉到最底 → **Developer settings**
3. **Personal access tokens** → **Tokens (classic)** → 右上 **Generate new token** → 选 **Generate new token (classic)**
4. 填写：
   - **Note**：随便写，如 `我的电脑`
   - **Expiration**：选 `90 days` 或 `No expiration`（不过期，省心；缺点是泄露后要手动作废）
   - **Select scopes**：勾选第一项 **repo**（整个大项勾上）
5. 点底部绿色 **Generate token**
6. **立刻复制**页面显示的 `ghp_xxxxxxxx` 字符串——**这个页面只显示这一次**，关掉就再也看不到了，务必存到记事本里

### 4.2 推送时怎么填

`git push` 后命令行会依次询问：

```
Username for 'https://github.com': 你的GitHub用户名
Password for 'https://...': ghp_xxxxxxxx        ← 粘贴 Token，不是账号密码！
```

> 粘贴 Token 时终端**不会显示任何字符**（连星号都没有），这是正常的，粘完直接回车。

### 4.3 偷懒替代方案（可选）

怕 Token 麻烦，可以装 **Git Credential Manager**（装 Git 时默认自带）：第一次推送会弹一个浏览器窗口让你登录 GitHub，授权后以后永远不用再输。如果推送时弹出了浏览器窗口，直接在网页上点授权即可。

---

## 五、验证上传成功

1. 刷新你的仓库页面 `https://github.com/你的用户名/daily-notebook`
2. 应该能看到：README 渲染成的漂亮首页（带截图和功能列表）、200 个左右的文件、绿色的提交记录
3. 点开 `README.md` 顶部的截图应该能正常显示

**加分项——给仓库加"门面"：**

- 点仓库右上角 ⭐ 旁边的 **About 齿轮**，把 Topics 加上：`python` `tkinter` `todo` `chinese-nlp` `desktop-app`，别人搜这些词能找到你
- 点 README 里的图片确认都能加载；挂了的图说明路径错了（见第七章 Q7）

---

## 六、以后改了代码怎么更新（日常三条命令）

```bash
git add .
git commit -m "fix: 修复了xxx"
git push
```

记住这个节奏：**改代码 → add → commit → push**。之后每次推送不会再问 Token（Credential Manager 已记住）。

**推荐的习惯**：

- 每完成一个小功能或修完一个 bug 就提交一次，说明写具体——提交历史会变成这个项目的开发日记，看的人（包括未来的你）能看懂每一步
- 版本稳定时打标签发版：`git tag v1.9.9.10` → `git push --tags`；想发布 exe 给人下载，去 GitHub 仓库页 **Releases** → **Draft a new release**，把打包好的 zip 拖上去

---

## 七、常见问题排错（Q&A）

**Q1：`git push` 报 `Authentication failed`**
Token 错了或过期。重新生成一个（见 4.1），或者在 Windows「控制面板 → 凭据管理器」里删掉 `git:https://github.com` 那条凭据，再推送重来一次。

**Q2：`git push` 报 `! [rejected] main -> main (fetch first)`**
远程有你本地没有的东西（多半是建仓库时不小心勾了 README）。执行：

```bash
git pull origin main --allow-unrelated-histories
git push -u origin main
```

如果弹出编辑器让你写合并说明，直接关掉窗口即可。

**Q3：`git push` 报 `failed to push some refs` / `remote contains work you do not have`**
同 Q2，先 `git pull` 再 `git push`。

**Q4：`git commit` 报 `Author identity unknown`**
没告诉 Git 你是谁，执行 3.3 节那两条 `git config` 命令后重试。

**Q5：`git: 'xxx' is not a git command` 或 `'git' 不是内部或外部命令`**
Git 没装好或没加进 PATH，重装 Git，安装时保持默认（默认会加 PATH）。

**Q6：手滑把 `data/` 推上去了，里面有我的隐私！**
立刻执行：

```bash
git rm -r --cached data
git commit -m "chore: 移除 data 目录"
git push
```

这会让仓库里不再显示它，但**历史版本里仍有**。如果已经公开且在意，最干净的做法：去 GitHub 仓库 Settings 拉到最底 **Delete this repository** 删掉重来，改好 `.gitignore` 后重新走一遍第三章。

**Q7：README 里的图片显示不出来（裂图）**
图片路径大小写必须和文件名完全一致（GitHub 服务器区分大小写）。本项目图片都在 `screenshots/` 下，README 里写的就是 `screenshots/xxx.png`；如果你重命名了文件，README 里的路径要同步改。

**Q8：`git add .` 报 `warning: LF will be replaced by CRLF`**
只是换行符格式提醒，无害，忽略即可。

**Q9：想删掉 GitHub 上传错的东西 / 整个仓库**
删文件：本地删掉后 `git add .` → `git commit` → `git push`。
删整个仓库：仓库页 **Settings** → 拉到最底 **Delete this repository**（输入仓库名确认）。

**Q10：推送很慢 / 超时**
国内访问 GitHub 不稳定。可以给 Git 挂代理（如果你有）：

```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

（`7890` 换成你自己代理软件的端口；取消代理用 `git config --global --unset http.proxy`）

**Q11：命令行里 中文文件名 显示成转义数字**
执行 `git config --global core.quotepath false` 即可正常显示。

---

## 八、检查清单（推送前最后过一遍）

- [ ] Git 安装成功，`git --version` 有输出
- [ ] GitHub 建好了空仓库，**没勾**任何初始化选项
- [ ] `.gitignore` 存在且包含 `data/`
- [ ] `git status` 的列表里没有 `data/`、`dist/`、`__pycache__`
- [ ] Token 已生成并保存（或用 Credential Manager 浏览器授权）
- [ ] `git commit -m` 写了人话说明
- [ ] 推送后刷新仓库页，README 图片全部能显示

全部打勾，你的第一个开源项目就正式上线了 🎉
