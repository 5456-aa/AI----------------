# 部署到 Streamlit Community Cloud（免费公网地址，不依赖你开机）

> 适合场景：评委想看在线界面，但你的电脑不可能一直开着。
> 部署后得到一个固定地址 `https://xxx.streamlit.app`，任何人都能打开。

---

## 一、先理解一件事

Streamlit Cloud 的本质是：**把你的 GitHub 仓库克隆到云端，用 `streamlit run 入口文件` 跑起来。**

所以能不能跑通，取决于**仓库里有没有运行时需要的东西**：

| 需要 | 本项目情况 |
|---|---|
| 入口文件 | `ui/home.py` ✅ |
| 依赖清单 | `requirements.txt` ✅ |
| 结果数据 | `data/out/*.csv` ✅ 已放行 |
| 批次清单 | `data/tracks/*.json` ✅ 已放行 |
| 看板用的明细 | `data/clean/{ecommerce,education}/*.jsonl` ✅ 已放行 |
| 模型缓存 | `data/cache/llm_calls.jsonl` ✅ 已放行 |
| **不能有** | `.env`（密钥）、`tools/cloudflared.exe`（53MB） |

`.gitignore` 已经配好：默认忽略 `data/`，但逐个放行了上面这些。

---

## 二、本机仓库已经建好了（2026-11-15 完成）

项目根目录已经初始化 git 并完成首次提交：

```
提交号  327352c
文件    255 个
体积    15.75 MiB
自检    26 项全过（含 .env 已忽略、无明文密钥）
```

**所以你不需要「New repository」，只需要「Add Local Repository」。**

### 1. 把本机仓库加入 GitHub Desktop

1. 打开 GitHub Desktop → 菜单 `File` → **`Add local repository…`**
2. Local path 选 **项目文件夹本身**
3. 点 `Add repository`

### 2. 发布到 GitHub

1. 点右上角 **`Publish repository`**
2. Name 保持 `ai-opp-system`
3. **取消勾选** `Keep this code private`（免费账号私有仓库不能用 Streamlit Cloud）
4. 点 `Publish repository`

完成。浏览器打开 `https://github.com/你的用户名/ai-opp-system` 应能看到代码。

### （保留）从零新建仓库的老办法

1. 打开 **GitHub Desktop** → 菜单 `File` → `New repository…`
2. 填写：
   - **Name**：`ai-opp-system`
   - **Local path**：选到项目文件夹的**上一级**（不要选项目文件夹本身）
   - **Initialize with README**：不要勾
3. 点 `Create repository`

> GitHub Desktop 会在上一级目录下建 `.git`，你的项目在其中的 `ai-opp-system` 子目录，
> 这样仓库根目录就是 `ai-opp-system`，符合云端要求。

### 2. 提交文件

1. 左侧会列出成千上万个变更 —— **先别急着提交**
2. 确认 `Changes` 里**没有** `.env`（如果有，说明 `.gitignore` 没生效）
3. 在左下角 Summary 填 `初版：AI 机会评估系统`，点 `Commit to main`
4. 点顶部 `Publish repository`
   - **取消勾选** `Keep this code private`（免费账号的私有仓库不能用 Streamlit Cloud）
   - 点 `Publish repository`

### 3. 确认上传成功

浏览器打开 `https://github.com/你的用户名/ai-opp-system`，应该能看到：
`ui/`、`data/`、`requirements.txt`、`config.yaml` …

---

## 三、在 Streamlit Cloud 部署

1. 打开 **https://share.streamlit.io**，用 GitHub 账号登录
2. 点 `Create app` → `Deploy a public app from GitHub`
3. 填写：

| 字段 | 填什么 |
|---|---|
| Repository | `你的用户名/ai-opp-system` |
| Branch | `main` |
| Main file path | `ui/home.py` |
| App URL | 自定义，例如 `ai-opp-demo` |

4. 点 `Advanced settings…`：
   - **Python version**：选 **3.11**
   - **Secrets**：先留空（本项目无 Key 也能跑，走离线缓存）
5. 点 `Deploy`，等 2~5 分钟

成功后地址是：

```
https://ai-opp-demo.streamlit.app
```

手机 4G 也能打开。

---

## 四、部署后必须做的两件事

### 1. 打开"只读模式"

云端跑的是公网页面，**必须禁止访客采集和改配置**。

Streamlit Cloud → 你的 app → `Settings` → `Secrets`，填入：

```toml
PUBLIC_DEMO = "1"
```

保存后 app 会自动重启，此时：
- 分析看板隐藏「模型设置」（访客改不了你的 Key）
- 首页隐藏「开始采集」按钮（访客不会触发采集）

### 2. （可选）配置 Key

如果希望云端能做新的判别，加一行：

```toml
DEEPSEEK_API_KEY = "sk-你的key"
```

⚠️ 放进去之前想清楚：这是把 Key 交给平台。**建议不配**——演示用缓存足够，
评委看的是结果和分析能力，不是"能不能现采"。

---

## 五、这套方案的限制（写论文/答辩时要说明）

| 限制 | 说明 |
|---|---|
| 只能看，不能采 | 云端是只读演示，发起需求需在本机运行 |
| 首次打开慢 | 免费实例会休眠，冷启动 30~60 秒 |
| 数据是快照 | 云端展示的是上传时的批次结果 |
| 仓库公开 | 代码公开可见；密钥不在仓库里，但请自查 |

---

## 六、提交前自检

在项目根目录运行：

```bash
python scripts/check_cloud_ready.py
```

它会检查：`.env` 是否被忽略、必需数据是否齐全、有没有超大文件、
入口能否 import。**全绿再推。**

---

## 七、和"临时隧道"怎么选

| | Streamlit Cloud | 临时隧道（cloudflared） |
|---|---|---|
| 地址 | 固定 | 每次变 |
| 依赖你开机 | ❌ 不用 | ✅ 必须开着 |
| 部署耗时 | 15 分钟（一次性） | 0（双击即用） |
| 能否采集 | ❌ 只读 | ✅ 能（本机跑） |

**建议**：答辩前用隧道（现场可控、能演示采集）；提交材料里放 Cloud 地址（评委随时能看）。
