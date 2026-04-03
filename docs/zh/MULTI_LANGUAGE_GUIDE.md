---
layout: default
title: 多语言文档指南
language: zh
---

# 多语言文档指南

**语言**: [English (英文)](../MULTI_LANGUAGE_GUIDE.md) | [简体中文](MULTI_LANGUAGE_GUIDE.md)  
**最后更新**: 2026-04-04

本指南说明 OpenSynaptic 文档如何在 GitHub Pages 上支持多种语言。

---

## 概述

OpenSynaptic 项目提供多语言文档支持：

- **English (英文)** (`/en/` 或根目录 `/`) - 原始英文文档
- **简体中文** (`/zh/`) - 中文翻译

### 目录结构

```
docs/
├── index.html              # 语言选择器页面
├── _config.yml             # Jekyll 配置
├── _layouts/
│   └── default.html        # 包含语言切换器的基础布局
├── assets/
│   └── css/style.css       # 共享样式表
├── README.md               # 英文文档中心
├── INDEX.md                # 英文文档索引
├── ARCHITECTURE.md         # 英文架构文档
├── API.md                  # 英文 API 参考
├── [other-docs].md         # 其他英文文档
│
└── zh/                     # 中文翻译
    ├── README.md           # 中文文档中心
    ├── INDEX.md            # 中文文档索引
    ├── ARCHITECTURE.md     # 中文架构文档
    ├── MULTI_LANGUAGE_GUIDE.md  # 本指南的中文版
    └── [other-docs].md     # 其他中文文档
```

---

## 语言切换

### 用户使用

用户可以通过三种方式切换语言：

1. **语言选择器页面**: 访问 [index.html](../index.html) 选择语言
2. **页面头部链接**: 每个页面的头部都有语言切换链接
3. **直接 URL 导航**: 
   - 英文: `/docs/FILENAME.md` 或 `/docs/en/FILENAME.md`
   - 中文: `/docs/zh/FILENAME.md`

### 工作原理

Jekyll `_config.yml` 定义语言设置：

```yaml
languages:
  en:
    name: "English"
    code: "en"
  zh:
    name: "简体中文"
    code: "zh"
    path: "/zh/"
```

每个 markdown 文件的 Front Matter 指定语言：

```yaml
---
layout: default
title: 页面标题
language: zh
---
```

`_layouts/default.html` 模板使用此元数据来：
- 在页面头部显示当前语言
- 提供语言切换链接
- 根据语言上下文自定义导航

---

## 添加翻译

### 第 1 步：创建中文目录结构

在 `docs/zh/` 目录中创建对应文件：

```bash
docs/zh/
├── README.md           # 翻译自 docs/README.md
├── INDEX.md            # 翻译自 docs/INDEX.md
├── ARCHITECTURE.md     # 翻译自 docs/ARCHITECTURE.md
└── ...
```

### 第 2 步：添加 YAML Front Matter

每个 markdown 文件必须以语言规范开头：

```yaml
---
layout: default
title: [当前语言的页面标题]
language: zh
---

# 页面内容
```

### 第 3 步：翻译内容

- 翻译页面标题和所有内容
- 保持与原文相同的 markdown 结构
- 更新所有内部链接路径：
  - 在 `/zh/` 文件中将 `[链接](../README.md)` 改为 `[链接](README.md)`（同目录）
  - 对跨语言链接使用正确的相对路径

### 第 4 步：添加语言切换链接

在翻译页面的顶部/底部添加：

```markdown
**语言**: [English (英文)](../FILENAME.md) | [简体中文](FILENAME.md)
```

或在 Front Matter 中：

```yaml
---
layout: default
title: 页面标题
language: zh
---
```

模板会自动处理语言切换。

### 第 5 步：更新导航

添加新部分时：

1. 同时更新英文和中文 INDEX.md 文件
2. 添加语言切换链接
3. 更新任何受影响的导航页面

---

## 翻译指南

### 语气和风格

- **保持一致性**: 在整个翻译中使用相同的术语
- **准确无误**: 正确翻译技术术语（例如，"Fusion Engine" → "融合引擎"）
- **流畅自然**: 适应中文语法（不是逐字翻译）
- **查看受众**: 假设读者是熟悉物联网和 Python 的技术人员

### 技术术语词汇表

为技术术语保持一致的词汇表：

| 英文 | 中文 | 上下文 |
|------|------|--------|
| Fusion Engine | 融合引擎 | 核心组件 |
| Pipeline | 管道 | 数据处理流程 |
| Transporter | 传输器 / 传输驱动程序 | 插件系统 |
| Base62 Compression | Base62 压缩 | 数据编码 |
| ID Lease System | ID 租赁系统 | 设备管理 |
| Backend | 后端 | Pycore/Rscore 选择 |
| Standardization | 标准化 | UCUM 单位转换 |

### 代码示例

保持代码不变，但翻译注释和周围文本：

```python
# 中文版本（注释已翻译，代码相同）
def compress(data: bytes) -> str:
    """将二进制数据转换为 Base62 格式。"""
    return base62_encode(data)
```

---

## 部署

### GitHub Pages 工作流

`.github/workflows/pages.yml` 会自动：

1. **触发条件**: 推送到 main/master 分支，docs/ 文件夹有变更
2. **构建**: 运行 Jekyll 从 markdown 生成 HTML
3. **部署**: 如果在 main 分支上，上传到 GitHub Pages
4. **验证**: 在 PR 中检查 markdown 语法和链接结构

### 本地测试

推送前在本地测试：

```bash
# 安装 Jekyll
gem install jekyll bundler

# 进入 docs 目录
cd docs

# 安装依赖项
bundle install

# 构建网站
bundle exec jekyll build

# 本地查看（可选）
bundle exec jekyll serve
# 访问 http://localhost:4000
```

---

## 特定于语言的功能

### Front Matter 变量

在任何 markdown 文件中，您可以使用：

```yaml
---
layout: default
title: 页面标题
language: zh
toc: true              # 启用目录
description: 简短描述
---
```

### 条件内容

在 markdown 中使用 Jekyll Liquid 模板：

```liquid
{% if page.language == 'zh' %}
  [仅中文内容]
{% else %}
  [仅英文内容]
{% endif %}
```

### 特定于语言的导航

默认布局自动生成：
- 页面头部的语言切换链接
- 针对当前语言的相应导航菜单
- 页脚中的 GitHub 链接

---

## 最佳实践

### 建议 ✅

- ✅ 保持英文和中文文档同步
- ✅ 使用一致的 Front Matter 结构
- ✅ 提交 PR 前测试链接
- ✅ 使用内部链接的相对路径
- ✅ 在页面顶部/底部添加语言切换链接
- ✅ 修复文档时同时更新两种语言版本
- ✅ 在布局文件中使用语义 HTML

### 不建议 ❌

- ❌ 不要硬编码绝对路径
- ❌ 不要在同一文件中混合英文和中文（代码除外）
- ❌ 不要跳过 YAML Front Matter
- ❌ 不要在新页面中忘记语言链接
- ❌ 不要直接编辑已部署的网站
- ❌ 不要依赖自动翻译工具（质量可能不佳）
- ❌ 不要在不更新配置的情况下更改目录结构

---

## 贡献翻译

要贡献翻译：

1. **Fork 仓库**
2. **创建分支**: `git checkout -b docs/add-zh-translation`
3. **在 `docs/zh/` 中添加/更新翻译文件**
4. **遵循上述指南**
5. **使用 Jekyll 本地测试**（见部署部分）
6. **提交 PR**，附带已翻译页面的描述

### PR 检查清单

- [ ] 所有 YAML Front Matter 正确
- [ ] 语言链接是双向的
- [ ] 相对路径正确
- [ ] 无 HTML/markdown 语法错误
- [ ] 术语一致
- [ ] 链接指向现存文件
- [ ] 代码示例不变（仅翻译注释）
- [ ] 无硬编码的绝对路径

---

## 添加新语言

要添加对新语言（例如西班牙语）的支持：

### 1. 更新 `docs/_config.yml`:

```yaml
languages:
  en:
    name: "English"
    code: "en"
  zh:
    name: "简体中文"
    code: "zh"
  es:
    name: "Español"
    code: "es"
    path: "/es/"
```

### 2. 创建目录和文件:

```bash
mkdir -p docs/es
cp docs/README.md docs/es/README.md
```

### 3. 更新 `docs/index.html`:

在 HTML 语言选择器中添加新语言卡片。

### 4. 更新布局:

编辑 `docs/_layouts/default.html` 在切换器中包含新语言。

### 5. 开始翻译:

为每个文件添加 YAML Front Matter 并翻译内容。

---

## 常见问题解决

### 链接无法工作

**问题**: 发布后链接返回 404  
**解决方案**: 
- 检查相对路径是否正确
- 验证文件在英文和翻译版本中都存在
- 使用 `[文本](filename.md)` 而不是 `[文本](filename)` 或 `[文本](filename.html)`

### 语言切换器未出现

**问题**: 页面头部没有语言选项  
**解决方案**:
- 添加 YAML Front Matter，包含 `language: en` 或 `language: zh`
- 检查 `_layouts/default.html` 是否正确更新
- 验证 Jekyll 本地构建成功

### 中文字符无法显示

**问题**: 中文文本显示为 ???  
**解决方案**:
- 确保文件保存为 UTF-8
- 检查布局中是否有 `<meta charset="utf-8">`
- 验证 _config.yml 未覆盖编码设置

### GitHub Actions 中构建失败

**问题**: GitHub Pages 部署失败  
**解决方案**:
- 检查 `.github/workflows/pages.yml` 是否存在
- 验证 `docs/_config.yml` 存在且有效 YAML
- 确保 Gemfile 在 docs 目录中
- 检查仓库设置中的工作流权限

---

## 资源

- [Jekyll 文档](https://jekyllrb.com/)
- [GitHub Pages 指南](https://docs.github.com/en/pages)
- [Markdown 指南](https://www.markdownguide.org/)
- [OpenSynaptic 主文档](README.md)

---

## 支持和反馈

如果您发现翻译问题或有建议：

1. 在 GitHub 上打开 Issue
2. 提供具体页面和语言
3. 如果适用，建议正确的翻译
4. 如果相关，参考本指南

---

**最后更新**: 2026-04-04  
**由以下机构维护**: OpenSynaptic 社区  
**语言**: [English (英文)](../MULTI_LANGUAGE_GUIDE.md) | [简体中文](MULTI_LANGUAGE_GUIDE.md)
