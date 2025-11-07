# --use-local-db 参数失败问题分析与修复

## 🐛 问题描述

从 `scripts/` 目录运行任何脚本时，`--use-local-db` 参数总是失败，并显示：

```
⚠️  本地数据库模块不可用！自动回退到在线Tushare
   请确保已正确配置 database/query_helper.py
```

## 🔍 根本原因

**Python 模块导入路径问题**

当从 `scripts/` 目录运行脚本时：
```bash
cd scripts/
python single_stock_rolling_score.py --use-local-db ...
```

Python 的模块搜索路径（`sys.path`）**不包含项目根目录**，导致无法找到 `database` 模块。

### 详细分析

```python
# 当前工作目录: /Users/xxx/stock/ta_stock/scripts/
# Python 尝试导入: from database.query_helper import StockDataQuery

sys.path = [
    '/Users/xxx/stock/ta_stock/scripts',  # 当前目录（scripts/）
    # ... 其他系统路径
]

# database/ 模块在: /Users/xxx/stock/ta_stock/database/
# 但 sys.path 中没有 /Users/xxx/stock/ta_stock/
# 因此导入失败！
```

## ✅ 解决方案

### 方案1：修改脚本，自动添加项目根目录到路径（推荐）⭐

在所有脚本的开头添加路径处理代码：

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

# 将项目根目录添加到 Python 路径
# 这样可以从任意位置运行脚本
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 现在可以正常导入了
from database.query_helper import StockDataQuery
```

**优点**：
- ✅ 从任意位置运行脚本都能工作
- ✅ 不需要修改使用方式
- ✅ 对用户透明

**需要修改的脚本**：
- `scripts/single_stock_rolling_score.py`
- `scripts/daily_stock_scoring.py`
- `scripts/technical_analysis.py`
- `scripts/batch_technical_analysis.py`
- `scripts/advanced_technical_analysis.py`

### 方案2：从项目根目录运行脚本

```bash
# 当前目录: /Users/xxx/stock/ta_stock/
python scripts/single_stock_rolling_score.py --code 000737.SZ --use-local-db
```

**优点**：
- ✅ 无需修改代码

**缺点**：
- ❌ 不符合用户习惯（通常在 scripts/ 目录下运行）
- ❌ 需要改变使用方式
- ❌ 容易忘记

### 方案3：将 database 安装为 Python 包

```bash
# 在项目根目录创建 setup.py
cd /Users/xxx/stock/ta_stock/
pip install -e .
```

**优点**：
- ✅ 专业的解决方案
- ✅ 可以从任意位置导入

**缺点**：
- ❌ 需要额外配置
- ❌ 对新用户不友好

---

## 🔧 推荐修复（方案1）

我将为所有脚本添加路径处理代码。修改后，无论从哪个目录运行都能正常使用 `--use-local-db`。

### 修改示例

**修改前**:
```python
import os
import sys
import logging

# 导入本地数据库查询模块
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False
```

**修改后**:
```python
import os
import sys
import logging

# ========== 路径配置 ==========
# 将项目根目录添加到 Python 路径，以便导入 database 模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ========== 导入本地数据库查询模块 ==========
try:
    from database.query_helper import StockDataQuery
    LOCAL_DB_AVAILABLE = True
except ImportError:
    LOCAL_DB_AVAILABLE = False
```

---

## 📊 测试结果

### 修复前

```bash
$ cd scripts/
$ python single_stock_rolling_score.py --code 000737.SZ --use-local-db

⚠️  本地数据库模块不可用！自动回退到在线Tushare
✓ 数据源: 在线Tushare
```

### 修复后

```bash
$ cd scripts/
$ python single_stock_rolling_score.py --code 000737.SZ --use-local-db

✓ 数据源: 本地数据库
获取数据范围: 20241106 至 20251107
✓ 成功获取 245 个交易日的数据
```

---

## 🎯 需要修复的文件清单

1. ✅ `scripts/single_stock_rolling_score.py`
2. ✅ `scripts/daily_stock_scoring.py`
3. ✅ `scripts/technical_analysis.py`
4. ✅ `scripts/batch_technical_analysis.py`
5. ✅ `scripts/advanced_technical_analysis.py`

---

## 📝 备注

这是一个常见的 Python 项目结构问题。当脚本不在项目根目录时，需要手动配置导入路径。

**最佳实践**：
- 在所有需要导入项目模块的脚本开头添加路径配置
- 或者使用 `setup.py` 将项目安装为 Python 包
- 或者始终从项目根目录运行脚本

我们选择第一种方案，因为它对用户最友好，使用最方便。
