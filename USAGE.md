# USAGE —— 逐条可复制命令

每条命令给出：**用途 / 输入 / 命令（Windows + Linux）/ 预期输出 / 判据 / 依赖档 / 退出码**。
依赖分三档，全文用这三个词：

| 档 | 含义 | 需要装什么 | 本机实测 |
|---|---|---|---|
| **轻** | 纯标准库 | 什么都不用装（Python 3.8+） | Python 3.10.4 |
| **中** | + pandas | `pip install pandas` | pandas 2.3.3 / numpy 2.2.6 |
| **重** | + CPU 版 torch，**且**需要作者的私有 `legged_gym` 层（本包不含） | `pip install torch numpy` | torch 2.13.0+cpu |

> 以下所有"实测"均来自 2026-11-01 本机 Windows（`D:\py\python\python.exe`）的一次真实执行，
> 返回码与关键输出原文见 [`../核验记录.md`](../核验记录.md)。
> 命令里的 `python` 请替换成你自己的解释器路径。

---

## 0. 最短路径（三条，约 2 秒）

```bash
# 轻 —— 重算 README 里每个数字
python verify_numbers.py                      # → 28 条断言，PASS 28 / FAIL 0，exit 0

# 轻 —— 从随包的 21 个仓库判定 JSON 重新生成审计 CSV
python audit/scripts/summarize_21.py          # → 覆写 audit/audit_21repos.csv（逐字节相同）

# 轻 —— 第三关（收敛有效性），只有一个输入文件
python gates/gate_check.py --p3               # → [FAIL] P3 ... exit 1（这是真实结论，不是环境问题）
```

---

## 1. 目录约定（先读，否则 P1/P2/P3 会找不到文件）

`gates/gate_check.py` **是原文拷贝，未改动**。它按自己的位置解析输入：

```python
ROOT = Path(__file__).resolve().parents[1]   # 脚本所在目录的上一级
PRJ  = ROOT.parent                            # 再上一级
SELF_CHECK = PRJ / "代码修复-20261012"                          # P1 的私有源树
META_TEST  = PRJ / "39-mutation-20261028/scripts/test_guards_meta.py"
E1_CSV     = PRJ / "34-零成本三件套-20261027/data/iter_metrics.csv"   # P2 输入
EXT_JSON   = PRJ / "35-收敛与种子检验-20261027/data/ext_full.json"     # P3 输入
```

也就是说，脚本期望**下面这个相对布局**（目录名是硬编码的）：

```
<工作目录>/
├── 34-零成本三件套-20261027/data/iter_metrics.csv      ← 来自本包 data/iter_metrics.csv
├── 35-收敛与种子检验-20261027/data/ext_full.json        ← 来自本包 data/ext_full.json
├── 39-mutation-20261028/scripts/test_guards_meta.py    ← 来自本包 checker/test_guards_meta.py（仅 P1 的补测用）
├── 代码修复-20261012/                                    ← 作者的私有层，本包不含
└── 41-三关形式化/scripts/gate_check.py                  ← 来自本包 gates/gate_check.py
    （gate_check.py 会把 gate_report.json 写在这个目录下）
```

**搭这个目录（照抄即可）**——把 `<包>` 换成本包 `repo/` 的路径：

```powershell
# Windows PowerShell
$pkg = "<包>"
$w   = "repro"          # 工作目录，随便取名
New-Item -ItemType Directory -Force -Path "$w\34-零成本三件套-20261027\data",
    "$w\35-收敛与种子检验-20261027\data", "$w\39-mutation-20261028\scripts",
    "$w\41-三关形式化\scripts" | Out-Null
Copy-Item "$pkg\data\iter_metrics.csv"  "$w\34-零成本三件套-20261027\data\"
Copy-Item "$pkg\data\ext_full.json"     "$w\35-收敛与种子检验-20261027\data\"
Copy-Item "$pkg\checker\test_guards_meta.py" "$w\39-mutation-20261028\scripts\"
Copy-Item "$pkg\gates\gate_check.py"    "$w\41-三关形式化\scripts\"
```

```bash
# Linux / macOS bash
pkg="<包>"; w="repro"
mkdir -p "$w/34-零成本三件套-20261027/data" "$w/35-收敛与种子检验-20261027/data" \
         "$w/39-mutation-20261028/scripts" "$w/41-三关形式化/scripts"
cp "$pkg/data/iter_metrics.csv" "$w/34-零成本三件套-20261027/data/"
cp "$pkg/data/ext_full.json"    "$w/35-收敛与种子检验-20261027/data/"
cp "$pkg/checker/test_guards_meta.py" "$w/39-mutation-20261028/scripts/"
cp "$pkg/gates/gate_check.py"   "$w/41-三关形式化/scripts/"
```

搭好后本包自带的数据足以跑 **P2 与 P3**；P1 还需要作者的私有层（见 §5）。

---

## 2. `verify_numbers.py` —— 重算所有关键数字

| 项 | 内容 |
|---|---|
| 用途 | 把 README「结果数字」表里每个数从随包数据重算，并做 28 条一致性断言 |
| 输入 | `audit/audit_21repos.csv`、`audit/shas.txt`、`audit/reports/*.md`、`mutation/mutation_results.csv`、`mutation/mutation_summary.json`、`data/ext_full.json`、`data/iter_metrics.csv`；`figs/data/*.json` 存在时额外检查（本包默认不含） |
| 依赖档 | **轻**（纯标准库） |
| 输出 | 控制台打印 4 个小节 + 断言汇总；不写任何文件 |
| 判据 | `PASS 38 / FAIL 0`，退出码 0 |

```powershell
python verify_numbers.py           # Windows
python verify_numbers.py -v        # 多打明细（idiom 分布、各臂末两块差等）
```
```bash
python verify_numbers.py            # Linux/macOS
python verify_numbers.py -v
```

实测尾部输出：

```
[4] 三关检查器的输入数据
  [PASS] ext_full.json 含 free_ext2 / lock_ext / lock_ext3  free_ext2、lock_ext、lock_ext3
  [PASS] free_ext2 末两块差 = 0.587  0.587
  [PASS] lock_ext3 末两块差 = 0.251  0.251
  [PASS] iter_metrics.csv 有 Mean_reward 列
  [PASS] iter_metrics.csv 有分项列 Mean_episode_rew_*（>0）  19 列
  [PASS] iter_metrics.csv 两臂 = free_swing / lock  ['free_swing', 'lock']
        iter_metrics.csv 行数 = 6000，分项 19 列
==============================================================================
断言 28 条：PASS 28 / FAIL 0
==============================================================================
```

第 3 小节（图数据）在本包里会打印：

```
[3] 图数据（可选；本包默认不含）
        跳过：figs/data 不存在。
        76.9× 的源在 gates/三关定义与矩阵.md §2：配置 10% vs 实测 0.13%（n=77，精确二项 p=0.00286）。
```

**"跳过"不等于"通过"**：本包不发布图数据（见 `../发布说明.md` §5），所以图相关断言被显式跳过并说明，
一旦你把最终的 `figs/data/*.json` 放进去，这些断言会自动生效。

这个脚本会故意做**跨文件的算术**，因此能抓到单文件看不出的矛盾。例：`6/10` 不在任何单个文件里——
脚本把首轮报告表里的 4 个 `MISROUTED` 行与 21 仓库 CSV 里的 2 个相加（4+2=6，5+5=10），
并在打印里点明"21 仓库 CSV 单独只给出 2/5"。**单看 CSV 会得出 2/5，这是个坑。**

---

## 3. `audit/scripts/summarize_21.py` —— 21 仓库汇总

| 项 | 内容 |
|---|---|
| 用途 | 读 `audit/out/*.json`（21 个仓库的完整判定），按"判据是否适用"分类，生成 `audit_21repos.csv` |
| 输入 | `audit/out/*.json`（21 个文件，随包提供）；血统/后端映射表内嵌在脚本 `BACKEND` 字典里（人工标注） |
| 依赖档 | **轻**（纯标准库） |
| 输出 | 覆写 `audit/audit_21repos.csv` + 控制台表 |
| 判据 | 退出码 0；生成文件与随包 CSV **逐字节相同**（sha256 `7559d28796d87765f6a8ff9cc0c69dc9c493fdb562df806a65dab15bbee6b1ef`） |

```powershell
python audit\scripts\summarize_21.py        # Windows
```
```bash
python audit/scripts/summarize_21.py        # Linux/macOS
```

实测尾部输出：

```
C1 适用 5 个，其中 MISROUTED 2 个：['AgibotTech/agibot_x1_train', 'limxdynamics/pointfoot-legged-gym']
总仓库 21；按血统 legged_gym-like 5
```

> 脚本假设自己在 `<某目录>/scripts/` 下、`out/` 是它的同级目录（`ROOT = parents[1]`）。
> 本包已经按这个约定摆好，**在 `repo/` 内直接跑即可**，不会破坏原文件（重跑结果与原 CSV 相同）。

---

## 4. `audit/scripts/audit_repo.py` —— 对任意本地仓库跑 C1/C2/C3

| 项 | 内容 |
|---|---|
| 用途 | 静态审计一个**已解压的源码目录**：C1 `--seed` 是否真进了 `env_cfg`（而非只写 `cfg_train`）、C2 play/eval 脚本是否有确定性开关、C3 注入点是否有生效核对 |
| 输入 | 一个本地目录（`<repo_dir>`）+ 可选 `--name`、`--json` |
| 依赖档 | **轻**（纯标准库，注释声明兼容 Python 3.8） |
| 输出 | 控制台摘要，或 `--json` 完整判定（含证据行 `文件:行号`） |
| 判据 | 退出码 0；判定是**信号 + 暂定**，终判必须人工复核（脚本自带 `manual_review` 提示） |

```powershell
python audit\scripts\audit_repo.py <repo_dir> --name my-repo          # Windows
python audit\scripts\audit_repo.py <repo_dir> --json                  # 完整 JSON
```
```bash
python audit/scripts/audit_repo.py <repo_dir> --name my-repo          # Linux/macOS
```

实测（对作者自己的 legged_gym 覆盖层跑，用来演示工具认得这条真实缺陷）：

```
== my-legged-gym-layer  (38 py) ==
  C1 seed   : MISROUTED_seed_to_train_cfg
              legged_gym\utils\helpers.py:135: cfg_train.seed = args.seed
  C2 eval   : no_eval_entry  []
  C3 inject : has_audit_signal  files=32
```

判读：`C1` 命中"CLI 种子只写进 `cfg_train`"这个 legged_gym 上游缺陷（与
`audit/reports/报告-首轮9仓库-20261028.md` §2 的校准过程一致）；`C3` 报 `has_audit_signal` 是**信号不是结论**——
作者的树里 32 个提及注入的文件带 `assert_*`，而这些断言是真的，所以这里"有核对"成立；
反面例子是 `iit-DLSLab/fault-locomotion-isaaclab` 的 29 个文件 0 个核对（见 README 数字表）。

---

## 5. `gates/gate_check.py` —— 三关检查器

参数只有三个开关（`--help` 实测原文）：

```
usage: gate_check.py [-h] [--p1] [--p2] [--p3]

options:
  -h, --help  show this help message and exit
  --p1
  --p2
  --p3
```

不带参数 = 三关全跑。输出格式固定为 `[PASS]/[FAIL] <关> (threshold: …)` + 每关的数值键值对，
最后一行 `总判定：`；同时在 `ROOT`（即 `scripts/` 的上一级）写 `gate_report.json`。
**退出码 0 = 全部通过，1 = 有未通过项。**

### 5.1 第三关 P3（收敛有效性）—— 轻，只要一个 JSON

| 项 | 内容 |
|---|---|
| 输入 | `<工作目录>/35-收敛与种子检验-20261027/data/ext_full.json`（本包 `data/ext_full.json`） |
| 依赖档 | **轻**（`json` + 路径） |
| 判据 | 每个臂 `\|末两块差\| < 0.5` **且** 末三块不同号单调 |
| 实测 | **FAIL**，exit 1（0.90 s） |

```powershell
python gates\gate_check.py --p3      # Windows（在 §1 的工作目录里跑）
```
```bash
python gates/gate_check.py --p3      # Linux/macOS
```

实测输出（原文）：

```
[FAIL] P3  (threshold: 末两块差 < 0.5 且末三块不单向单调)
        arms: {'free_ext2': {'blocks': [17.94, 18.439, 18.867, 18.28], 'last_two_diff': 0.587, 'monotone_tail': False, 'pass': False}, 'lock_ext': {'blocks': [15.366, 15.681, 16.602, 17.748], 'last_two_diff': 1.145, 'monotone_tail': True, 'pass': False}, 'lock_ext3': {'blocks': [17.489, 18.142, 18.393], 'last_two_diff': 0.251, 'monotone_tail': True, 'pass': False}}
总判定： 存在未通过项
```

**这是真实结论，不是配置错误。** 论文里 P3 不通过：`free` 臂末两块差 0.587 > 0.5（没有平台），
`lock` 臂到 6500 迭代仍以约 0.25/块单调上升。含义见 `gates/三关定义与矩阵.md` §5 与
`README.md` 的"口径纪律"。

### 5.2 第二关 P2（测量有效性）—— 中，需要 pandas

| 项 | 内容 |
|---|---|
| 输入 | `<工作目录>/34-零成本三件套-20261027/data/iter_metrics.csv`（本包 `data/iter_metrics.csv`，6000 行、19 个分项列） |
| 依赖档 | **中**（`pandas`） |
| 判据 | 四项全有值 + 可加性反例率 ≤ 1% |
| 实测 | **PASS**，exit 0（3.05 s，含 pandas 导入） |

```powershell
python gates\gate_check.py --p2
```
```bash
python gates/gate_check.py --p2
```

实测输出（原文）：

```
[PASS] P2  (threshold: 四项全有值；可加性反例 ≤1%)
        P2a_declared_both_calibers: True
        P2b_clip_mass_reported: True
        clip_mass_mean: 2.9782390000000003
        window_deltas_pct: {100: -11.303462927807576, 300: -11.733846048204347, 500: -14.167707433041466}
        P2c_window_range_pp: 2.8642445052338896
        additivity_violations: 12
        additivity_violation_rate: 0.002
总判定： 全部通过
```

判读：裁剪质量均值 2.98；三窗口 −11.30 / −11.73 / −14.17（极差 2.864pp < 5pp，无需声明主窗口的"挑窗口"辩护）；
可加性反例 12/6000 = 0.2% ≤ 1%。这三个数与 `gates/三关定义与矩阵.md` §5 的表逐项一致。

### 5.3 第一关 P1（注入有效性）—— 重，需要私有层

| 项 | 内容 |
|---|---|
| 输入 | `<工作目录>/代码修复-20261012/`（**本包不含**）+ `<工作目录>/39-mutation-20261028/scripts/test_guards_meta.py`（本包 `checker/test_guards_meta.py`） |
| 依赖档 | **重**（`torch` + `numpy` + 私有 `legged_gym` 层） |
| 判据 | 60 项基础自检 `FAIL == 0` **且** 6 项补测 `FAIL == 0` |
| 实测（有私有层时） | **PASS**，exit 0（60/60 + 6/6） |
| 实测（无私有层时） | **崩溃**，exit 1，`NotADirectoryError: [WinError 267] 目录名称无效。` |

有私有层时：

```powershell
python gates\gate_check.py --p1
```
```
[PASS] P1  (threshold: FAIL==0)
        checks_total: 60
        checks_pass: 60
        checks_fail: 0
        meta_checks_total: 6
        meta_checks_pass: 6
总判定： 全部通过
```

**没有私有层时不会给出友好的"自检没跑起来"，而是抛栈**——因为 `subprocess.run(cwd=...)` 的 `cwd`
指向一个不存在的目录。这是原文拷贝的行为，未做修饰；原文报错末尾：

```
File "...\gate_check.py", line 37, in run_script
    p = subprocess.run([PY, str(script)], cwd=str(cwd), ...)
NotADirectoryError: [WinError 267] 目录名称无效。
```

（`gate_check.py` 里"自检没跑起来"那个分支只在**目录存在但测试失败/没输出合计行**时才会走到。）

### 5.4 三关全跑

```powershell
python gates\gate_check.py
```
```bash
python gates/gate_check.py
```

实测：P1 PASS / P2 PASS / **P3 FAIL**，`总判定： 存在未通过项`，**exit 1**（30.3 s）。
`gate_report.json` 写在 `41-三关形式化/`（即 `scripts/` 的上一级），内容为
`{"results": [...], "all_pass": false}`。

---

## 6. 直接跑 66 项自检（不经 gate_check）—— 重

### 6.1 60 项基础自检

| 项 | 内容 |
|---|---|
| 输入 | 私有 `legged_gym` 层；脚本通过 `P1R8_PKG_ROOT` 定位包根，缺省用自身父目录 |
| 依赖档 | **重**（`torch` + `numpy`；`isaacgym` 用脚本自带的替身 `tests/isaacgym_stub/`） |
| 判据 | `合计 60 项：PASS 60 / FAIL 0`，exit 0 |
| 实测 | 11.50 s（其中 `import torch` 7.95 s） |

```powershell
$env:P1R8_PKG_ROOT = "<工作目录>\代码修复-20261012"
python "<工作目录>\代码修复-20261012\tests\test_r1_r8_local.py"
```
```bash
P1R8_PKG_ROOT="<工作目录>/代码修复-20261012" python "<工作目录>/代码修复-20261012/tests/test_r1_r8_local.py"
```

末行实测：`合计 60 项：PASS 60 / FAIL 0`。它还会写
`tests/local_verification_report.json`（落在私有层里，不在本包）。

### 6.2 6 项补测 G1–G6

| 项 | 内容 |
|---|---|
| 输入 | 私有层 + 必须先能用 `P1R8_PKG_ROOT` 找到 `tests/test_r1_r8_local.py`（它 import 原自检模块复用 `FakeEnv`） |
| 依赖档 | **重** |
| 判据 | `META 合计 6 项：PASS 6 / FAIL 0`，exit 0 |
| 实测 | 8.54 s |

```powershell
$env:P1R8_PKG_ROOT = "<工作目录>\代码修复-20261012"
Copy-Item checker\test_guards_meta.py "<工作目录>\代码修复-20261012\tests\"    # 脚本按 WORK/tests/ 找原自检
python "<工作目录>\代码修复-20261012\tests\test_guards_meta.py"
```
```bash
P1R8_PKG_ROOT="<工作目录>/代码修复-20261012" python "<工作目录>/代码修复-20261012/tests/test_guards_meta.py"
```

G1–G6 各断言什么，见 `checker/README.md`。

---

## 7. 变异测试（`mutation/mutation_run.py`）—— 重，本包不能独立重跑

| 项 | 内容 |
|---|---|
| 用途 | 把注入链路的关键语句逐个改坏，重跑 66 项自检：自检失败 = 变异被抓；仍全绿 = 盲区 |
| 输入 | 私有 `代码修复-20261012/`（会被复制到 `39-mutation-*/_work/` 再改写）+ `scripts/test_guards_meta.py` |
| 依赖档 | **重**（`torch`；脚本里 `PY` 硬编码为 `D:\py\python\python.exe`，换机器必须改这一行） |
| 输出 | `mutation_results.csv`、`mutation_summary.json`、`crash_M<id>.log` |
| 判据 | `mutation score ≥ 0.85`（`gates/三关定义与矩阵.md` §4 检查表） |
| 本次是否执行 | **否**——它需要改写私有源树，本包不含该树。随包给出的是**结果数据**与 21 条变异定义原文 |

```powershell
python mutation\mutation_run.py --list          # 只列 21 个变异体（不需要私有层，可跑）
python mutation\mutation_run.py --only M11      # 跑单个（需要私有层）
python mutation\mutation_run.py                 # 全量（需要私有层）
```

`--list` 是本包里**唯一**能跑的 mutation 子命令（它只打印 `MUTANTS` 表）。
全量运行的目录约定：脚本放在 `<工作目录>/39-mutation-<日期>/scripts/`，被测源树是
`<工作目录>/代码修复-20261012/`，补测脚本是 `<工作目录>/39-mutation-<日期>/scripts/test_guards_meta.py`。

---

## 8. 依赖一览（谁重谁轻）

| 命令 | 档 | 需要私有层 | 本次实测结果 |
|---|---|---|---|
| `verify_numbers.py` | 轻 | 否 | 38/38 PASS，exit 0，0.53 s |
| `audit/scripts/summarize_21.py` | 轻 | 否 | 退出 0，CSV 逐字节相同，0.40 s |
| `audit/scripts/audit_repo.py <dir>` | 轻 | 否（对任意目录） | 退出 0，0.51 s |
| `gates/gate_check.py --p3` | 轻 | 否 | **FAIL**，exit 1，0.90 s |
| `gates/gate_check.py --p2` | 中（pandas） | 否 | PASS，exit 0，3.05 s |
| `gates/gate_check.py --p1` | 重（torch） | **是** | 有层：PASS 60+6；无层：`NotADirectoryError`，exit 1 |
| `gates/gate_check.py`（全跑） | 重 | **是**（否则 P1 崩） | P1/P2 PASS、P3 FAIL，exit 1，30.3 s |
| `checker/test_r1_r8_local.py` | 重 | **是** | 60/60，exit 0，11.50 s |
| `checker/test_guards_meta.py` | 重 | **是** | 6/6，exit 0，8.54 s |
| `mutation/mutation_run.py` | 重 | **是** | 本次未执行（见 §7）；`--list` 可跑 |

安装建议（只在需要时装，注意国内源）：

```bash
pip install pandas                                          # 中
pip install torch numpy -i https://pypi.tuna.tsinghua.edu.cn/simple   # 重（CPU 版即可）
```

---

## 9. 排查对照表（这些是真实遇到过的）

| 现象 | 原因 | 处理 |
|---|---|---|
| `--p3` 报 `缺少 ...ext_full.json` | 没按 §1 搭目录 | 照 §1 复制，或把 `data/ext_full.json` 放到脚本期望的位置 |
| `--p1` 抛 `NotADirectoryError: [WinError 267]` | 没有私有 `代码修复-20261012/` 目录 | 这是预期行为；P1 只对作者可跑，读 `checker/` 的代码与 USAGE §5.3 的实测输出即可 |
| `--p2` 报 `ModuleNotFoundError: No module named 'pandas'` | 依赖档"中"没装 | `pip install pandas` |
| `summarize_21.py` 生成空 CSV / 报 `rows[0]` 索引错 | 脚本不在 `<目录>/scripts/` 下，`out/` 找不到 | 保持本包 `audit/scripts/` + `audit/out/` 的摆法，在 `repo/` 内跑 |
| `mutation_run.py` 报 `[FATAL] 基线自检没跑起来` | `PY` 路径或私有层不对 | 改脚本第 30 行 `PY`；确认 `<工作目录>/代码修复-20261012/` 存在 |
| 中文在 Windows 控制台变成乱码 | 控制台默认 GBK | 先 `$env:PYTHONIOENCODING="utf-8"`（脚本内部也已 `reconfigure`，多数情况无需处理） |
