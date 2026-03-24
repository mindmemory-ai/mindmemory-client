# Agent 工作目录与记忆同步扩展：workspace + `mmem-workspace.json`

本文档约定：**每个 Agent** 在本地除 **`pnms/`**（神经记忆 checkpoint）与 **`repo/`**（记忆 Git 仓库）外，增加同级 **`workspace/`**（工作目录），用于存放 **Claw / CLI** 侧源文件；并通过 **`workspace/mmem-workspace.json`** 描述 **同步进密文仓的子集** 与 **（可选）LLM 提示上下文要读的文件**，使 **mindmemory-client** 在**不按 Claw 实例分子目录**的前提下统一处理。

**读者**：实现 Claw 记忆插件、`openclaw-mmem` 类集成、或扩展 **`mmem`** / **mindmemory-client** 的维护者。  
**状态**：**部分已落地**（**`pnms_bundle.enc`** 与 **`mmem/bundles/extras.enc`** 均由 **`K_seed`** 加密；清单与打包见 **`mindmemory_client.sync_manifest`** / **`workspace_extras`**；CLI **`mmem sync push --sync-extras`**、**`memory merge --import-extras`** 等；宿主侧 LLM 拼装等仍为可选后续）。

---

## 1. 问题与动机

### 1.1 现状

- **记忆 Git 仓库**（`repo/`）里主要同步 **`pnms_bundle.enc`**：对应 **PNMS** 数据目录经 tar + AES-GCM（`K_seed`）。
- **mindmemory-client** 已封装解密、合并与 CLI 路径；**自有 CLI** 场景通常够用。

### 1.2 缺口

1. **Claw 运行时**会在 Agent 侧产生大量文件，但**并非每个文件**都需要进入「可同步的记忆载荷」；若全部打进一个 bundle，会臃肿且难审计。
2. **不同 Claw 实例**（同一 Agent、不同会话/网关）若用路径硬编码区分，会增加目录爆炸；我们希望在**同一 Agent 工作区**内**不按实例分子目录**，由**插件在启动时**决定本次要同步的子集。
3. **固定记忆**（身份、原则、人格片段）与 **PNMS 槽记忆** 性质不同，不宜全部塞进 PNMS；但仍希望与 **同一 Git 密文仓库** 一并版本化。
4. **自有 CLI** 也需要能附带 **Agent 配置、人格文件** 等做实验，并与上述模型一致：**调用方**（CLI 或 Claw 插件）在**本机**调用 **mindmemory-client** 完成「选文件 → 打包 → 加密 → 写入 `repo/` → push」。

因此需要两层约定：

| 层级 | 作用 |
|------|------|
| **Agent 本地目录** | `pnms/`、`repo/`、**`workspace/`** 三者**同级**；`workspace` 放「候选源文件」，**不**等同于 Git 工作副本。 |
| **Workspace 配置文件** | **`workspace/mmem-workspace.json`**（**不入记忆 Git**）：见 **§3**。 |

---

## 2. Agent 本地目录布局（与 `pnms`、`repo` 同级）

路径相对于 **`accounts/<user_uuid>/agents/<agent>/`**（与 `agent_workspace_dir` 一致）。

```text
<agent>/
  agent.json                 # Agent 元数据（已有）
  pnms/                      # PNMS checkpoint（神经记忆引擎落盘）
  repo/                      # 记忆 Git 仓库 clone 根（含 .git；远端密文与 pnms_bundle.enc 等）
  workspace/                 # 工作目录：Claw 运行时与 CLI 的「源文件池」
    mmem-workspace.json      # workspace 描述与配置（见 §3）；默认不提交、不随 repo 走
    ...                      # 人格、配置片段、导出文本等
```

说明：

- **`workspace/` 不按 Claw 实例分子目录**：同一 Agent 共用一个 `workspace`；**同步子集与（可选）提示路径**由 **§3 `mmem-workspace.json`** 表达，而不是路径分段。
- **`repo/`** 仍是唯一「与 MindMemory 远端同步」的 Git 树；**清单文件放在 `workspace/`**，故天然**不会**被 `repo` 的 commit 纳入（除非误拷，应避免）。

---

## 3. 配置文件：`mmem-workspace.json`（不纳入记忆 Git）

### 3.1 定位

- **路径**：`<agent>/workspace/mmem-workspace.json`。
- **性质**：**仅本机**；由 **Claw 插件** 或 **开发者** 维护；**`mmem sync push --sync-extras`** 读取 **`sync.bundles`** 生成 **`mmem/bundles/extras.enc`**。
- **不入 `repo/`**：与 **`repo/`** 并列，见 **§5.1** 防误拷说明。

### 3.2 语义（`schema_version` 仅 `"2"`）

| 字段 | 作用 |
|------|------|
| **`sync.bundles`** | 打进 **`extras.enc`** 的路径（相对 `workspace/`）；语义与实现见 **`mindmemory_client.sync_manifest`**。 |
| **`prompt`**（可选） | 供宿主拼接 **LLM 上下文**时读取的文件（可与 `sync` 不同，例如仅本机、不同步的文件）；**不**参与 tar 加密，除非路径也出现在 `sync` 中。 |
| **`prompt.include`** | glob 或字面路径；**`prompt.optional`** 控制缺文件时跳过或告警。 |

**未列入 `sync` 的路径**不会进入密文仓库；仍可留在 `workspace/` 供运行。

### 3.2a `sync` 与 `prompt` 易混点（必读）

| 问题 | 说明 |
|------|------|
| **进不进 Git 密文？** | 仅 **`sync.bundles`** 中匹配的文件会进入 **`extras.enc`**；**`prompt`** 段**仅**声明本机读哪些文件给 LLM，**不**参与 tar 加密。 |
| **二者能否不同？** | 可以。例如：`prompt` 含本机草稿 **`local/hints.md`**，但不希望上云，则**不要**把它写进 **`sync`**；或 **`sync`** 含大资源而 **`prompt`** 只引用摘要文件。 |
| **CLI `mmem chat`** | 使用 **`prompt`**（经 **`read_workspace_prompt_block`**）拼系统提示；**不**自动把 `sync` 独有文件读入对话，除非它们也出现在 **`prompt.include`** 中。 |

示例：

```json
{
  "schema_version": "2",
  "updated_at": "2026-03-24T12:00:00Z",
  "note": "paths relative to workspace/",
  "sync": {
    "bundles": [
      {
        "id": "extras",
        "include": ["persona/core.md", "config/agent_style.toml"],
        "optional": true
      }
    ]
  },
  "prompt": {
    "include": ["persona/core.md", "local/hints.md"],
    "optional": true
  }
}
```

- **`include`**（sync / prompt）：实现方 **sanitize** 路径，禁止 `..` 越界。
- **PNMS**：仍由 **`pnms/` → `pnms_bundle.enc`**，**不**写入本文件。

### 3.3 谁写入

| 调用方 | 行为 |
|--------|------|
| **Claw 记忆插件** | 实例启动或进入可同步状态前，按策略 **生成/覆盖** `mmem-workspace.json`。 |
| **自有 CLI（`mmem`）** | 实验时可手写或借助 **`mmem sync extras-dry-run`** 校验路径。 |

**加密**在**本机**通过 **mindmemory-client** 完成，**不**在服务端解析明文。

---

## 4. 记忆 Git 仓库（`repo/`）内：密文产物布局

与 **`workspace`** 的衔接关系为：

1. 读取 **`workspace/mmem-workspace.json`**（`schema_version` 为 **`"2"`**）。
2. 将 **`sync.bundles`** 中 **`include`** 所指文件打成 **tar.gz**（根路径为 `workspace/`）。
3. 使用与 **`pnms_bundle.enc`** 相同的 **`encrypt_memory_base64`（K_seed）**，写入 **`mmem/bundles/extras.enc`**（相对记忆 Git 根；与实现 **`sync_manifest.EXTRAS_BUNDLE_REPO_RELPATH`** 一致）。
4. **`git add` / `commit` / `push`** 仍走现有 MMEM sync 锁流程。

**拉取侧**：`mmem memory merge` 后解密各 **`*.enc`**；**extras** 解压回 **`workspace/`** 相对路径；**默认不覆盖** **`mmem-workspace.json`**（见 `decrypt_extras_bundle_*` 参数）。

---

## 5. `repo/` 内可选布局（与 §4 配套，向后兼容）

以下相对于 **`repo/`** 的 Git 根：

```text
<git-root>/
  pnms_bundle.enc              # PNMS 主 bundle
  mmem/
    bundles/
      extras.enc               # 来自 workspace 清单的加密包（固定相对路径）
  ...
```

密文路径以 **`mindmemory_client.sync_manifest.EXTRAS_BUNDLE_REPO_RELPATH`** 为准；**不设**单独的仓内 JSON 描述文件。

### 5.1 记忆仓库 `repo/.gitignore` 建议片段（可选）

**目的**：记忆 Git 工作副本的根目录即 **`<agent>/repo/`**（clone 下来的目录）。其中**只应**跟踪 **`pnms_bundle.enc`**、**`mmem/bundles/*.enc`** 等**密文**及必要元数据；**不应**把 **Agent 侧 `../workspace/`** 下的明文（人格、草稿、运行时清单）通过**符号链接、子模块或误拷贝**纳入同一 Git 树。

以下片段可放在 **`<agent>/repo/.gitignore`**（若文件已存在则**追加**相关规则；与团队既有规则冲突时以「不提交明文 workspace」为准则合并）：

```gitignore
# --- MMEM / mindmemory-client：避免将 Agent workspace 明文纳入记忆仓 ---
# 若误在仓库内创建指向 ../workspace 的符号链接或同名目录，勿提交
workspace
workspace/

# 本地解密/实验产生的明文副本（命名约定可按项目调整）
*.plain.txt
*.decrypted
.mmem-local/

# 常见本机杂文件（可选）
.DS_Store
Thumbs.db
```

说明：

- **`workspace` / `workspace/`**：针对「在 **`repo/` 根下** 出现名为 `workspace` 的链接或目录」的情况；正常布局下 **`workspace/` 与 `repo/` 并列**，本规则**不会**影响 **`accounts/.../agents/<agent>/workspace`**（该路径在 Git 仓**外**）。
- Git **不会**跟踪仓库目录之外的文件；本片段防的是 **把明文放进 `repo/` 树内**（含 `git add` 符号链接导致把敏感路径纳入版本对象的风险）。
- 若使用 **Git LFS** 或其它大文件机制，可在同一 `.gitignore` 中另行约定，但**仍不应**用 LFS 存 workspace 明文；应继续只提交 **`*.enc`** 密文。

---

## 6. LLM 上下文拼装顺序（建议）

| 顺序 | 来源 | 说明 |
|------|------|------|
| 1 | **`mmem-workspace.json`** 中 **`prompt.include`** 指向的明文（若配置） | 可与 `sync` 子集不同；库提供 **`prompt_context_paths_for_workspace`** |
| 2 | 解密 **`extras.enc`** 得到的人格/配置片段 | 与 **`sync.bundles`** 一致 |
| 3 | PNMS `get_context` | 神经记忆 |
| 4 | 用户消息 | — |

具体字段映射（system / developer）由 **Claw 插件** 或 **CLI** 决定。

---

## 7. 加密与密钥（与现网一致）

- **算法**：与 **`pnms_bundle.enc`** 相同 —— **tar.gz → AES-256-GCM → Base64 单行**；密钥 **`K_seed`**。
- **多类密文**：**`pnms_bundle.enc`** 与 **`mmem/bundles/extras.enc`** 等各为独立 tar 密文；均为 **`K_seed`**，无额外仓内元数据文件。

---

## 8. mindmemory-client / CLI 演进建议

| 阶段 | 内容 |
|------|------|
| 当前 | **`pnms_bundle.enc`** + **`mmem/bundles/extras.enc`**（**`workspace/mmem-workspace.json`**，`schema_version: 2`）；库 **`load_workspace_config`** / **`pack_workspace_extras_to_enc`** / **`prompt_context_paths_for_workspace`**；CLI **`--sync-extras`** / **`extras-dry-run`** / **`--import-extras`** |
| 中期 | 干跑列表、更丰富的 glob 与冲突策略；**仍不**在库内绑定 Claw |
| 长期 | 可选 CI / 约定校验密文路径；宿主与 LLM 集成 |

---

## 9. 集成检查清单

**Claw 记忆插件**

1. 在 Agent 下确保存在 **`workspace/`**，维护 **`mmem-workspace.json`**（**`sync`** 与可选 **`prompt`**）。
2. 调用 **mindmemory-client** 打包 + 加密 + 将产物路径写入 **`repo/`**，再走已有 **sync** / **git push**。
3. **PNMS** 仍经 **`PnmsMemoryBridge`**，不在插件内直接 `import pnms`。

**自有 CLI**

1. 在 **`workspace/`** 放入实验用人格、配置等。
2. 手写或生成同一清单后执行 **`mmem sync push --sync-extras`**（或先调库 API 再 push）。

**安全**

1. 清单仅描述**相对路径**；实现必须 **防路径穿越**。
2. **`workspace`** 中可能含敏感草稿；**只有写入 `sync.bundles` 的 `include`** 才进入密文仓。

---

## 10. 相关文档

| 文档 | 关系 |
|------|------|
| [mmem-使用说明.md](./mmem-使用说明.md) | 当前 CLI 与目录习惯 |
| [mindmemory-client-设计.md](./mindmemory-client-设计.md) | 库边界与 sync |
| `pnms/docs/pnms_api.md` | PNMS 语义 |

---

## 11. 修订记录

| 说明 |
|------|
| v1：多 bundle、`mmem/` 布局 |
| v2：**Agent 下 `workspace/` 与 `pnms`/`repo` 同级**；**`.mmem-sync-manifest.json` 为运行时、不入 Git**；Claw 与 CLI 共用 mindmemory-client 打包加密流程 |
| v2.1：**§5.1** 增加 **`repo/.gitignore` 建议片段**（防误将 `repo/` 内指向 workspace 的链接/拷贝纳入版本库） |
| v2.2：移除 **`mmem/repo.schema.json`** 设计；extras 路径固定为 **`mmem/bundles/extras.enc`**（与代码一致） |
| v3：**`mmem-workspace.json`** 取代旧清单；仅 **`schema_version: 2`**；含 **`sync`** 与可选 **`prompt`** |
