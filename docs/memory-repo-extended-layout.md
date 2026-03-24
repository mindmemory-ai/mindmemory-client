# Agent 工作目录与记忆同步扩展：workspace + 运行时清单

本文档约定：**每个 Agent** 在本地除 **`pnms/`**（神经记忆 checkpoint）与 **`repo/`**（记忆 Git 仓库）外，增加同级 **`workspace/`**（工作目录），用于存放当前 **Claw 实例运行时**产生的、或 **CLI 实验性**加入的文件；并通过一份**运行时描述文件**声明「本次同步要打包加密哪些路径」，使 **mindmemory-client** 能在**不区分 Claw 实例目录**的前提下，为**各实例的记忆插件**与**自有 CLI** 提供统一的加密同步入口。

**读者**：实现 Claw 记忆插件、`openclaw-mmem` 类集成、或扩展 **`mmem`** / **mindmemory-client** 的维护者。  
**状态**：**设计提案**（当前实现仍以根目录 **`pnms_bundle.enc`** 为主；本文描述目标形态与集成契约，可渐进落地）。

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
| **运行时描述文件** | 位于 **`workspace/`**（或下文约定路径），**不参与 Git 同步**；启动时由插件或 CLI **填写**，列出本次要纳入加密 bundle 的**相对路径**。 |

---

## 2. Agent 本地目录布局（与 `pnms`、`repo` 同级）

路径相对于 **`accounts/<user_uuid>/agents/<agent>/`**（与 `agent_workspace_dir` 一致）。

```text
<agent>/
  agent.json                 # Agent 元数据（已有）
  pnms/                      # PNMS checkpoint（神经记忆引擎落盘）
  repo/                      # 记忆 Git 仓库 clone 根（含 .git；远端密文与 pnms_bundle.enc 等）
  workspace/                 # 【提案】工作目录：Claw 运行时与 CLI 的「源文件池」
    .mmem-sync-manifest.json # 【提案】运行时清单（见 §3）；默认不提交、不随 repo 走
    ...                      # 插件或用户放置的任意子树（人格、配置片段、导出文本等）
```

说明：

- **`workspace/` 不按 Claw 实例分子目录**：同一 Agent 共用一个 `workspace`；**哪次同步带哪些文件**由 **§3 清单** 表达，而不是路径分段。
- **`repo/`** 仍是唯一「与 MindMemory 远端同步」的 Git 树；**清单文件放在 `workspace/`**，故天然**不会**被 `repo` 的 commit 纳入（除非误拷，应避免）。

---

## 3. 运行时描述文件：`.mmem-sync-manifest.json`（不纳入同步管理）

### 3.1 定位

- **文件路径（推荐）**：`<agent>/workspace/.mmem-sync-manifest.json`。
- **性质**：**仅运行时**；由 **Claw 记忆插件在实例启动时** 或 **`mmem` 在 push 前** 写入/更新。
- **不入 Git**：该文件位于 **`repo/` 之外**的 Agent 目录；即使将来工具误操作，也应在 **`repo/.gitignore`** 或文档中明确**勿将 `../workspace` 绑进记忆仓**。当前布局下 **`repo/` 与 `workspace/` 并列**，正常情况下**不会**提交该文件。

### 3.2 语义

清单声明：**从 `workspace/` 根出发**，哪些路径需要被 **mindmemory-client** 打包进**除 PNMS 以外的**加密 bundle（或未来扩展的多 bundle）。**未列入的路径**不同步到密文仓库（仍保留在本地 `workspace` 供运行使用）。

示例（字段名可随实现微调，此处为契约说明）：

```json
{
  "schema_version": "1",
  "updated_at": "2026-03-24T12:00:00Z",
  "bundles": [
    {
      "id": "extras",
      "include": [
        "persona/core.md",
        "config/agent_style.toml"
      ],
      "optional": true
    }
  ],
  "note": "paths relative to workspace/; pnms/ is never listed here — use existing pnms pack pipeline"
}
```

- **`include`**：glob 或显式相对路径列表；实现方应对路径做 **sanitize**，禁止 `..` 越界。
- **PNMS**：仍由现有 **`pnms/` → pnms_bundle.enc** 管道处理，**不必**出现在本清单中（避免重复与混淆）；文档与代码注释中写清即可。

### 3.3 谁写入

| 调用方 | 行为 |
|--------|------|
| **Claw 记忆插件** | 实例启动或进入「可同步」状态前，根据当前策略（用户勾选、团队规范）**生成/覆盖**清单。 |
| **自有 CLI（`mmem`）** | 在实验「人格 / 配置一并推送」时，可提供子命令或编辑向导写入同一清单，再调用库的打包 API。 |

**转换与加密**始终在**调用方进程**内通过 **mindmemory-client** 完成，**不**在服务端解析明文。

---

## 4. 记忆 Git 仓库（`repo/`）内：密文产物布局

`repo/` 内仍可与 §5 所述 **`mmem/bundles/*.enc`** 布局兼容；与 **`workspace`** 的衔接关系为：

1. 读取 **`workspace/.mmem-sync-manifest.json`**（若存在且 `schema_version` 支持）。
2. 将 **`include`** 所指文件打成 **tar.gz**（根路径为 `workspace/` 或约定前缀）。
3. 使用与 **`pnms_bundle.enc`** 相同的 **`encrypt_memory_base64`（K_seed）**，得到例如 **`mmem/bundles/extras.enc`** 或根目录 **`extras_bundle.enc`**（具体文件名由 **`repo.schema.json`** 或后续 CLI 约定）。
4. **`git add` / `commit` / `push`** 仍走现有 MMEM sync 锁流程。

**拉取侧**：`mmem memory merge` 后，对各 **`*.enc`** 解密；**extras** 类 bundle 解压回 **`workspace/`** 的对应相对路径（**merge 策略**可为 replace 或插件自定义），**不得覆盖**运行时清单本身，除非单独约定。

---

## 5. `repo/` 内可选布局（与 §4 配套，向后兼容）

以下相对于 **`repo/`** 的 Git 根：

```text
<git-root>/
  pnms_bundle.enc              # 现有：PNMS 主 bundle
  mmem/
    repo.schema.json           # 可选：声明 bundles 列表与路径
    bundles/
      extras.enc               # 来自 workspace 清单的加密包
  ...
```

**`repo.schema.json`** 可与 **`workspace`** 清单 **互补**：前者描述**仓里有什么密文**；后者描述**本地从 workspace 如何生成下一份 extras**。二者也可在将来合并为单一真相，本文保留分层以降低首轮实现成本。

---

## 6. LLM 上下文拼装顺序（建议）

| 顺序 | 来源 | 说明 |
|------|------|------|
| 1 | `workspace/` 内被插件标记为「仅本地、不同步」的提示文件（若有） | 不入 Git；可选 |
| 2 | 解密 **`extras.enc`** 得到的人格/配置片段 | 与清单一致 |
| 3 | PNMS `get_context` | 神经记忆 |
| 4 | 用户消息 | — |

具体字段映射（system / developer）由 **Claw 插件** 或 **CLI** 决定。

---

## 7. 加密与密钥（与现网一致）

- **算法**：与 **`pnms_bundle.enc`** 相同 —— **tar.gz → AES-256-GCM → Base64 单行**；密钥 **`K_seed`**。
- **多 bundle**：每个 `*.enc` **独立** tar；**可选** HKDF 子密钥（见旧版 §5，需时在 `repo.schema.json` 声明）。

---

## 8. mindmemory-client / CLI 演进建议

| 阶段 | 内容 |
|------|------|
| 当前 | 仅 **`pnms_bundle.enc`** + `import_encrypted_bundle_to_agent_checkpoint` |
| 短期 | 文档化 **`workspace/`** + **`.mmem-sync-manifest.json`**；**`mmem sync push`** 增加读取清单并生成 **`extras.enc`**（可选开关） |
| 中期 | **`pack_workspace_extras_to_enc(manifest, workspace_root, key) -> bytes`** 等 API；**仍不**在库内绑定 Claw |
| 长期 | 与 **`repo.schema.json`** 统一校验、CI 钩子 |

---

## 9. 集成检查清单

**Claw 记忆插件**

1. 在 Agent 下确保存在 **`workspace/`**，启动时写入 **`.mmem-sync-manifest.json`**（含本次要同步的 `include`）。
2. 调用 **mindmemory-client** 打包 + 加密 + 将产物路径写入 **`repo/`**，再走已有 **sync** / **git push**。
3. **PNMS** 仍经 **`PnmsMemoryBridge`**，不在插件内直接 `import pnms`。

**自有 CLI**

1. 在 **`workspace/`** 放入实验用人格、配置等。
2. 手写或生成同一清单后执行 **`mmem sync push`**（待实现清单消费逻辑后）。

**安全**

1. 清单仅描述**相对路径**；实现必须 **防路径穿越**。
2. **`workspace`** 中可能含敏感草稿；**只有写入 `include` 的项**才进入密文仓。

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
