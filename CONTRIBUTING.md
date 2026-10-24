# 参与 SelfLearn 开发

本仓库是基于 [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) 的独立定制分支。
有关本分支的问题和改进，请使用 [Albertanda/selflearn Issues](https://github.com/Albertanda/selflearn/issues)。
保留原代码的署名与 Apache-2.0 许可；上游功能说明见 `UPSTREAM.md`。

## 开始修改

1. 按 [README](README.md) 完成源码安装。
2. 阅读 [AGENTS.md](AGENTS.md) 的架构、数据保护和测试约束。
3. 从 `main` 创建工作分支，完成后向本仓库的 `main` 提交 Pull Request。
4. 在 PR 中说明具体问题、最终行为、验证结果以及剩余限制。

```bash
git switch -c fix/describe-the-change
```

不要自动将本分支硬重置为上游；同步上游应作为独立变更审查。
`plans/` 中包含历史阶段规划，不应把旧开工指令或归档文档视作当前执行授权。

## 验证

Python 测试必须使用隔离入口，避免读取真实配置、修改学习数据或请求真实模型：

```bash
# 完整测试
.venv/bin/python scripts/run_tests_isolated.py

# 指定测试范围
.venv/bin/python scripts/run_tests_isolated.py tests/services/config/test_custom_providers.py

# 前端静态检查和 Node 测试
cd web
npm run test:node
npx tsc --noEmit
npm run i18n:parity
```

不要直接运行未隔离的 pytest，也不要绕过测试网络保护。默认使用确定性的本地模型替身。
真实供应商 smoke 必须获得明确授权，限定请求次数、输出预算和超时，不回退其他付费供应商。

浏览器测试配置位于 `web/playwright.*.config.ts`，运行前按对应阶段说明设置新的证据目录。
不要复用封存目录，也不要让隔离测试指向真实数据目录。若依赖媒体工具或系统沙箱，
按 README 和阶段契约先配置，再准确报告通过、跳过与未验收项目。

仓库基础检查：

```bash
git diff --check
python3 scripts/check_repo_hygiene.py
```

可选的本地安全 hook：`git config core.hooksPath scripts/hooks`。
该 hook 默认阻止直接提交 `main`；维护者明确发布时可使用单次命令配置
`git -c deeptutor.allowMainCommit=true commit`，无需长期关闭保护。

## 数据与提交范围

- 不提交 `data/`、环境变量文件、API Key、个人教材/录音、模型回复原文和登录凭据。
- 不提交 `.venv/`、`node_modules/`、Next.js 构建结果、工具二进制和字体。
- `.phase1-evidence/` 是本机原始验收记录；对外只提供经过检查的摘要或经授权脱敏的证据。
- 不删除真实数据来“恢复测试”，不重写历史收据、数据基线或已批准的例外。
- 不使用 `git reset --hard` 或 `git clean` 作为例行清理方式；保留他人的未提交修改。

报告问题时给出系统、Python / Node 版本、复现步骤和脱敏日志。
不要上传完整 `model_catalog.json`、Authorization header、密钥文件或未经检查的截图。
