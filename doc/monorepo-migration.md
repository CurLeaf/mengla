# Monorepo 改造方案与建议

## 1. 需求是否合理

**结论：合理。**

- 将前端依赖上提到根目录、用「基础层 + 上层应用」的 monorepo 是常见做法，便于：
  - **依赖统一**：根目录一份 lockfile，版本一致、安装一次。
  - **基础层复用**：TypeScript/React/Vite 等作为基础，后续可扩展多应用（如 admin、mobile）或共享包（types、utils）。
  - **脚本与 CI 统一**：根目录 `pnpm dev` / `pnpm build` 调度各子包。

- 注意：当前仅有一个 frontend 应用，改造收益主要是「为后续扩展打基础」和「依赖/脚本收口到根目录」。若短期不会加新前端应用或共享包，可先做**最小改造**（仅 workspaces + 根依赖），再按需演进。

---

## 2. 目标与范围

| 目标 | 说明 |
|------|------|
| 前端依赖放到根目录 | 通过 pnpm workspaces 在根目录安装依赖，frontend 作为 workspace 子包，可引用根层依赖。 |
| 基础层提供上层服务 | 根目录提供：共享的构建/类型基础（TS、Vite、React 版本）；可选后续增加 `packages/shared`（类型、常量、工具）供 frontend 等消费。 |
| 不改动后端 | backend 保持 Python 独立，不纳入 Node 工作区。 |

**范围**：仅调整仓库内 Node/前端部分（根 + frontend，及可选 shared 包），不涉及后端目录结构。

---

## 3. 改造方案（二选一）

### 方案 A：最小改造（推荐先做）

- **结构**：根目录 + 现有 `frontend/` 作为唯一 workspace 包，依赖在根声明并 hoist。
- **优点**：改动小，frontend 路径不变，Docker/脚本几乎不用改。
- **适合**：先统一依赖与脚本，后续再考虑加 apps/packages。

```
mengla-data-collect/
├── package.json          # 新增：workspaces + 基础脚本 + 可选基础依赖
├── pnpm-workspace.yaml   # 新增：workspaces: ["frontend"]
├── frontend/             # 保持现有，package.json 可精简为只保留业务依赖
├── backend/
└── doc/
```

### 方案 B：完整 Monorepo（后续可选）

- **结构**：根目录 + `apps/frontend`（原 frontend 迁入）+ 可选 `packages/shared`（类型/常量）。
- **优点**：多应用、共享包扩展清晰；基础层（根 + shared）明确。
- **缺点**：需移动 frontend、改 Docker/脚本路径、CI 路径等。

```
mengla-data-collect/
├── package.json
├── pnpm-workspace.yaml   # packages: ["apps/*", "packages/*"]
├── apps/
│   └── frontend/         # 原 frontend 移入
├── packages/
│   └── shared/           # 可选：类型、常量、工具
├── backend/
└── doc/
```

**建议**：先落地**方案 A**，确认习惯后再决定是否迁到方案 B。

---

## 4. 方案 A 具体步骤

### 4.1 根目录新增配置

**pnpm-workspace.yaml**（新建）：

```yaml
packages:
  - "frontend"
```

**package.json**（新建于根目录）：

```json
{
  "name": "mengla-data-collect",
  "private": true,
  "scripts": {
    "dev": "pnpm --filter industry-monitor-frontend dev",
    "build": "pnpm --filter industry-monitor-frontend build",
    "preview": "pnpm --filter industry-monitor-frontend preview"
  },
  "devDependencies": {
    "typescript": "~5.6.3"
  }
}
```

- 根目录「基础层」可只放与多包共享的 dev 依赖（如统一 TypeScript 版本）；业务依赖仍写在 `frontend/package.json`，由 pnpm 在根安装并 hoist。
- 若希望基础层更明显，可把 `react`、`vite` 等也提到根 `devDependencies`，frontend 用 `"react": "workspace:*"` 引用（需 pnpm 支持；或保持 frontend 内声明版本，由 pnpm 提升到根安装）。

### 4.2 前端包保持可独立安装

- `frontend/package.json` 的 `name` 保持为 `industry-monitor-frontend`（与上面 `--filter` 一致）。
- 可不删任何依赖，仅保证在根执行 `pnpm install` 时能正确安装。

### 4.3 安装与脚本

- 在**根目录**执行：
  - `pnpm install`（会安装 frontend 的依赖并生成/更新根目录 `pnpm-lock.yaml`）。
  - `pnpm dev` / `pnpm build` / `pnpm preview` 通过 `--filter` 调用 frontend 脚本。
- 如需单独开发 frontend：`cd frontend && pnpm dev` 仍可用。
- 迁移后可将 **frontend/pnpm-lock.yaml** 删除，仅保留根目录的 **pnpm-lock.yaml**。
- **一键执行迁移**：在仓库根目录执行 `.\scripts\migrate-monorepo.ps1`，脚本会创建根目录配置、执行 `pnpm install` 并删除 `frontend/pnpm-lock.yaml`。

### 4.4 其他需注意

- **.gitignore**：若根目录新增 `node_modules/`，确保已忽略（通常已有）。
- **Docker**：若 Dockerfile 构建 frontend，当前基于 `frontend/` 上下文即可，无需改；若将来用根上下文构建，需在 Dockerfile 里 `cd frontend` 再 `pnpm install` / `pnpm build`。
- **CI**：若有 CI，从根目录执行 `pnpm install` 和 `pnpm build` 即可。

---

## 5. 基础层如何「提供上层服务」

- **当前（方案 A）**  
  - 基础层 = 根目录的 workspace 定义 + 统一安装（根 lockfile）+ 根脚本（`pnpm dev/build`）。  
  - 「提供」体现在：上层（frontend）依赖由根统一解析、版本一致、一处安装。

- **后续可扩展**  
  - **共享 TS 配置**：根目录 `tsconfig.base.json`，frontend 的 `tsconfig.json` 用 `extends` 引用。  
  - **共享类型/常量**：新增 `packages/shared`，导出类型、常量或工具函数；frontend 在 `package.json` 中依赖 `"@mengla/shared": "workspace:*"`，即可被上层消费。  
  - **多应用**：在 `apps/` 下再加应用（如 `apps/admin`），同样依赖根的基础层和（可选）`packages/shared`。

---

## 6. 建议小结

| 项目 | 建议 |
|------|------|
| 是否改造 | 合理，建议做。先方案 A，再按需方案 B。 |
| 依赖位置 | 根目录通过 pnpm workspaces 统一安装；frontend 仍声明自身依赖，由 pnpm 在根 node_modules 提升。 |
| 基础层 | 方案 A：根 = workspaces + 脚本 + 可选 TS/公共 dev 依赖；方案 B 再加 `packages/shared`、多 app。 |
| 后端 | 不纳入 Node workspace，保持独立。 |
| 文档与脚本 | 在 README 或内部文档注明：安装与构建请在根目录执行 `pnpm install` / `pnpm dev` / `pnpm build`。 |

按上述步骤即可在最小改动下，把前端依赖收口到根目录并形成可扩展的 monorepo 基础。
