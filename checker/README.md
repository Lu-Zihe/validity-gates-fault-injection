# checker/ —— 66 项检查的组成

本目录三个文件是论文"66 项可执行检查"的全部实现。**原文拷贝，未改动。**

| 文件 | 项数 | 作用 |
|---|---|---|
| `test_r1_r8_local.py` | 60 | 零 GPU 基础自检。每条修复配**两个**检查：正常路径必须通过 + 旧实现必须被抓住 |
| `test_guards_meta.py` | 6 | 补测 G1–G6，专治变异测试暴露的盲区（检查器自身被绕过、边界、状态残留、观测一致性、协议指纹） |
| `silent_failure_guards.py` | — | fail-closed 断言模块（`assert_*`，违反即 `raise SilentFailureError`），被上面两个套件调用 |
| **合计** | **66** | 60 + 6，与论文"66 项"一致 |

---

## 一、为什么这样设计

论文第二支柱的主张是：本项目缺陷族的统一形态是**"配置里写的值 ≠ 代码实际执行的值，而且不报错"**。
所以修复不是"把每处改对"（那只修当下这一处），而是把每个关键不变量写成**运行时断言**。
`test_r1_r8_local.py` 的文件头把这条理由写得很直接（见该文件 docstring 前 14 行）。

60 项按修复批次分成 R1–R8 八组（脚本运行时逐组打印标题）：

| 组 | 主题 | 对应缺陷族（见 `../gates/三关定义与矩阵.md` §3） |
|---|---|---|
| R1 | 地形课程：真难度梯度 + 7 个生成器接列 | D1 |
| R2 | 课程等级真正驱动地形配比（不再只写一个行索引） | D1 / D2 |
| R3 | 域随机化真接入（去掉 `hasattr` 守卫、修参数槽位、8 维落地） | D2 / D3 |
| R4 | 三种注入形态的物理语义（`free_swing` / `degrade(k)` / `lock(κ)`） | D3 / D6 |
| R5 | 旧行为复现：名义故障确实存在（反向用例） | D4 |
| R6 | 归一化能耗口径统一（分母 200 W / clamp [0,1] / 阈值 0.7） | D5 |
| R7 | 故障概率口径统一（配置声称值 = 运行时值） | D1 / D6 |
| R8 | 幽灵配置副本（D9）与断言防线接线 | D9 / D10 |

**反向用例是这套自检的关键**：其中 11 条以 `expect="raise"` 注册——喂旧实现/旧参数进去，
断言它**必须**报错或必须被识别为静默无效。只测"新代码能跑"的测试，无法区分"修好了"和"把检查关掉了"。

---

## 二、66 项之外：这套自检也被自检过

`../mutation/` 里的 21 个语义变异体就是"给检查器做变异测试"：
把注入链路的关键语句逐个改坏，看自检是否报警。结果 19/21 被抓（90.5%），2 个存活的是等价变异体。
其中 **M11（把 `if self.strict_checks:` 改成 `if False:`）在补测前 60 项全绿**——
这正是"检查器自身的失效不会报警"的现场证据。补测 G1 就是为了杀它。

详见 `../mutation/reports/报告-20261028.md` §1–§4。

---

## 三、跑它们需要的私有层（本包不含）

这两个套件 import 作者的 `legged_gym`。实测的依赖面（从源码 import 语句与路径字符串里逐条取出）：

**直接 import 的模块（6 个）**：

```python
import legged_gym.utils.curriculum_plan                 # 测试内部的 R1/R2
import legged_gym.utils.domain_randomization            # R3
import legged_gym.utils.fault_detector as fd            # R4–R7 + 补测
import legged_gym.utils.silent_failure_guards as guards # 两个套件都用
import legged_gym.utils.terrain as terrain_mod          # R1 地形几何
import legged_gym.utils.terrain_selector as ts          # R2/R8-6
```

**以文本 / AST 方式读取（不 import，用于静态断言）**：

| 文件 | 谁读它 | 读来判什么 |
|---|---|---|
| `legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py` | 60 项套件 + 补测 G1 | `reset_idx` 的调用顺序（课程 → 标称恢复 → DR → 注入 → 自检） |
| `legged_gym/utils/fault_detector.py` | 60 项套件 + 补测 G1 | `apply` 是否引用 `strict_checks`、是否调用逐腿核对 |
| `legged_gym/utils/terrain.py` | 60 项套件 | 地形生成器接线 |
| `legged_gym/scripts/train.py` | 补测 G6 | `run_meta.seed_effective` 是否绑定变量 |
| `legged_gym/__init__.py` | 60 项套件 | 幽灵副本检查（`assert_no_shadow_module_files`） |

**因此 66 项在本包内跑不起来**——这不是打包遗漏，是有意排除私有代码（见 `../README.md` 已知限制 1）。
注意本包的 `checker/silent_failure_guards.py` 是其中一个被 import 的模块，但它单独存在也不够：
其余 5 个模块仍缺失。

要跑，需满足与 `../USAGE.md` §1 相同的相对布局，并设置：

```powershell
$env:P1R8_PKG_ROOT = "<工作目录>\代码修复-20261012"    # Windows
```
```bash
export P1R8_PKG_ROOT="<工作目录>/代码修复-20261012"     # Linux/macOS
```

`test_guards_meta.py` 还要求自己与 `test_r1_r8_local.py` 在同一个 `tests/` 下（它按
`WORK/tests/test_r1_r8_local.py` 去 import 原自检模块，复用其中的 `FakeEnv`）。
所以把它拷进私有层的 `tests/` 再跑，不要就地跑。

---

## 四、isaacgym 的处理

`test_r1_r8_local.py` 默认**不需要** IsaacGym：它在 `sys.path` 里插入自带替身
（私有层的 `tests/isaacgym_stub/`），并用 `types.ModuleType` 预注册 `legged_gym.envs` 命名空间包，
避免执行真实的 `envs/__init__.py`（那会去 import 本机不存在的任务模块）。

想在云端用真 IsaacGym 验证真实地形几何时，设：

```bash
export P1R8_USE_REAL_ISAACGYM=1      # 此时必须先 import isaacgym 再 import torch
```

这条分支的注意点（`isaacgym` 必须在 `torch` 之前导入、`legged_gym.envs` 要先初始化）写在
`test_r1_r8_local.py` 第 27–38 行的注释里——那是踩过的坑，不是猜测。

---

## 五、实测（2026-11-01，Python 3.10.4 + torch 2.13.0+cpu）

```
合计 60 项：PASS 60 / FAIL 0        # test_r1_r8_local.py，11.50 s（其中 import torch 7.95 s）
META 合计 6 项：PASS 6 / FAIL 0     # test_guards_meta.py，8.54 s
```

两项合计 66/66。`gate_check.py --p1` 会把这两个数字一起报出来（`checks_total` / `meta_checks_total`）。
