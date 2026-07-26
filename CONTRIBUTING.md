# Contributing to x-cli

Thank you for your interest in contributing to x-cli! This document explains the development workflow and branch strategy.

## 🌿 Branch Strategy

This repository follows a simple branch strategy:

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | Stable release branch | 🔒 Protected - direct push blocked |
| `dev` | Active development branch | ✅ Default branch for contributions |

**Important**: If you fork this repository, please base all your work on the `dev` branch, not `main`.

## 🚀 Getting Started

### 1. Fork the Repository

1. Visit https://github.com/xavier-pen/x-cli
2. Click the "Fork" button (this will fork the entire repository)
3. After forking, your fork will default to the `dev` branch (if set as default)

### 2. Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/x-cli.git
cd x-cli
```

### 3. Add Upstream Remote

```bash
git remote add upstream https://github.com/xavier-pen/x-cli.git
```

### 4. Sync with Upstream (Regularly)

```bash
git checkout dev
git fetch upstream
git merge upstream/dev
```

## 🔧 Development Workflow

### 1. Create a Feature Branch (from `dev`)

```bash
git checkout dev
git pull upstream dev
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Follow the existing code style
- Use the risk-based workflow below
- Add a regression test when behavior changes
- Update documentation if needed
- See [AGENTS.md](AGENTS.md) for development conventions

#### Choose the smallest safe workflow

| Change | Required workflow |
|--------|-------------------|
| Small docs/help/local fix | No plan; BDD optional; focused tests only |
| User-visible feature or multi-module change | Short temporary plan; BDD for new behavior; TDD; focused tests; one full-suite run before handoff |
| Architecture, data, security, background process, packaging, or release | Full temporary plan; ADR when architectural; BDD + TDD as applicable; full suite and relevant build/security checks |

Focused tests should be used while iterating. Do not repeatedly run the full suite or build the Windows EXE when the changed area cannot affect them. Temporary plans belong in `docs/plans/` and are removed after acceptance; permanent decisions stay in behavior specs, ADRs, architecture documentation, or the changelog.

### 3. Commit Your Changes

```bash
git add .
git commit -m "feat: 新增功能描述"
```

**提交信息格式**（统一使用中文）：
- `feat(模块):` 新功能
- `fix(模块):` 修复
- `docs(模块):` 文档变更
- `test(模块):` 测试更新
- `refactor(模块):` 代码重构
- `chore(模块):` 维护任务

### 4. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 5. Create a Pull Request

1. Visit your fork on GitHub
2. Click "Compare & pull request"
3. **Important**: Set the base branch to `dev` (not `main`)
4. Fill in the PR description
5. Submit the PR

## ✅ PR Review Process

1. Maintainers will review your PR
2. Address any feedback or requested changes
3. Once approved, maintainers will merge your PR into `dev`
4. Periodically, maintainers will merge `dev` into `main` for releases

## 🐛 Reporting Bugs

- Use the [GitHub Issues](https://github.com/xavier-pen/x-cli/issues) page
- Include steps to reproduce, expected behavior, and actual behavior
- Mention your OS and Python version

## 💡 Feature Requests

- Open an issue with the "enhancement" label
- Describe the use case and expected behavior
- Wait for maintainer feedback before implementing non-trivial features

## 📝 License

By contributing, you agree that your contributions will be licensed under the MIT License (see [LICENSE](LICENSE)).

---

## ❓ FAQ

**Q: Why can't I push directly to `main`?**  
A: The `main` branch is protected to ensure stability. All changes must go through `dev` and be reviewed.

**Q: Can I fork just the `dev` branch?**  
A: No, GitHub forks the entire repository. But you should base your work on `dev` and set your default branch to `dev` in your fork settings.

**Q: How do I sync my fork with the upstream `dev` branch?**  
A: See step 4 in "Getting Started" above.

**Q: My PR was closed without merge. Why?**  
A: Common reasons:
- PR was based on `main` instead of `dev`
- No tests or incomplete test coverage
- 未遵循中文提交信息格式
- Feature is out of scope (see README.md "Won't" section)

---

Happy coding! 🎉
