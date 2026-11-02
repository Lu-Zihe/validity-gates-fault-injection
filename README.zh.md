# 三关有效性核验工件包（论文配套）

**Validity Gates for Fault-Injection Protocols in Robot Learning Simulations — executable artifacts**

> ⚠️ **发布状态：占位包，尚未推送。** 许可证未定（见 [`LICENSE-DECISION-NEEDED.md`](LICENSE-DECISION-NEEDED.md)），
> 作者信息与引用条目为占位（见 [`CITATION.cff`](CITATION.cff)）。数字口径已核对，见 [`../核验记录.md`](../核验记录.md)。

---

## 这个包是什么

**中文**：这是一篇方法学论文的配套工件包。论文的主张是：机器人学习里的"故障注入协议"会**静默失效**——
配置说注入了 10%，物理量上其实没变，而且不报错。本包含论文提出的**三关可判定判据**
（注入有效性 P1 / 测量有效性 P2 / 收敛有效性 P3）的**可执行实现**、66 项自检、
21 个公开仓库的审计工具与审计原始数据、以及 21 个语义变异体的变异测试数据。
所有数字都能用本包内的脚本从本包内的数据重算，不需要 GPU，不需要数据集。

**English**: Companion artifact for a methodology paper on *silent failure* in fault-injection
protocols for robot-learning experiments — the configuration declares an injection that the physics
never sees, and nothing raises an error. The package holds the executable form of three **decidable
validity gates** (injection validity P1 / measurement validity P2 / convergence validity P3),
a 66-item self-check suite, the static audit tool and raw audit data for 21 public repositories,
and the mutation-testing data for 21 semantic mutants. Every headline number is recomputable from
the files in this package with the scripts in this package; no GPU and no dataset are required.

---

## 三关是什么

判定对象是"一次注入实验是否可被当作证据"。三关的完整定义、阈值与失效矩阵在
[`gates/三关定义与矩阵.md`](gates/三关定义与矩阵.md)（论文 §3 的对应物）。

| 关 | 名称 | 判什么 | 阈值（来自定义文档） | 可执行实现 |
|---|---|---|---|---|
| **P1** | 注入有效性 | 抽样支持集（P1-a）、物理量真变（P1-b）、健康环境未被误标（P1-c）、形态保真（P1-d） | P1-a：单侧精确二项检验 `P(X≤k \| n, p) < 0.01`（`n` = **抽样次数**，不是环境数）；P1-d：`ε = 1e-6` | `gates/gate_check.py --p1`（调用 `checker/` 下的 60+6 项自检） |
| **P2** | 测量有效性 | 口径声明（P2-a）、裁剪质量双报（P2-b）、窗口敏感（P2-c）、可加性（P2-d） | 可加性反例率 ≤ 1%；窗口三档 `W ∈ {100,300,500}`，极差 > 5pp 必须声明主窗口 | `gates/gate_check.py --p2` |
| **P3** | 收敛有效性 | 末两块差 < δ（P3-a）、末三块不单向单调（P3-b）、块序列披露（P3-c） | `δ = 0.5`（回报单位，约 3%） | `gates/gate_check.py --p3` |

三关的**设计意图**是"能咬自己"。本包对作者自己的数据跑三关，结果是
**P1 通过、P2 通过、P3 不通过**（见下节）——P3 拦下的正是论文早期稿里"收敛后 ≤1%"那句解读。

---

## 结果数字（每个都能指到文件）

| 数字 | 含义 | 源头文件 |
|---|---|---|
| **76.9×** | 配置声称注入率 10% vs 实测 0.13%（77 次抽样命中 1 次）：`10 / 0.13 = 76.9` | `gates/三关定义与矩阵.md` §2 P1-a（同处给出精确二项 `P(X≤1 \| n=77, p=0.1) = 0.00286` 与 `n` 必须是抽样次数的论证） |
| **68.8×** | **另一个比值**：修复后 8.94% / 修复前 0.13% = 68.8。与 76.9× 不可混用，**正文标题只用 76.9×** | ⚠️ **待补**：`8.94%` 的源数据在图数据里，而图数据不随本包发布（见「已知限制 6」）。本包内暂无第二个出处，故 `verify_numbers.py` **不**校验此比值 |
| **6/10** | 10 个 legged_gym 血统（判据适用）仓库中 6 个 `--seed` 误路由 | 首轮 4/5：`audit/reports/报告-首轮9仓库-20261028.md` §3；新抓 2/5：`audit/audit_21repos.csv`（`C1` 列 `MISROUTED_seed_to_train_cfg`） |
| **29 文件 / 0 核对** | 唯一专门做故障注入的公开仓库（`iit-DLSLab/fault-locomotion-isaaclab`）里，29 个提及注入的文件中 **0 个**在注入点做生效核对 | `audit/audit_21repos.csv`（`C3_inject_files=29`、`C3=no_audit_signal`）+ `audit/reports/报告-21仓库-20261030.md` §3 |
| **90.5%** | 变异得分：21 个语义变异体中 19 个被 66 项自检捕获（Wilson 95% CI 71.1–97.3%） | `mutation/mutation_results.csv`、`mutation/mutation_summary.json` |
| **66 项** | 60 项基础自检 + 6 项补测（G1–G6）全绿 | `checker/test_r1_r8_local.py`（60）、`checker/test_guards_meta.py`（6） |
| **2** | 存活变异体 = M03、M04，均为**等价变异体**（只差 `r == p1` 的零测集） | `mutation/reports/报告-20261028.md` §3 |
| **P3 不通过** | `free_ext2` 末两块差 **0.587 > 0.5**；`lock_ext3` 末三块仍在单调上升（0.251/块） | `data/ext_full.json`、`gates/gate_check.py --p3` 的输出 |
| **7406** | 21 仓库 `.py` 文件合计（`n_py` 列求和） | `audit/audit_21repos.csv`，由 `verify_numbers.py` 求和 |

> **口径纪律**：6/10 不能读作"社区普遍"——10 个可判仓库里 6–7 个同属 legged_gym 血统，
> 有效独立单位只有 2–3 簇。正确表述是"在 10 个 legged_gym 式仓库中 6 个存在误路由；
> 它们分属 2–3 个独立血统"。同理，`<1%` 的偏差只能陈述为"未检出 >5pp 的差异（TOST 等价界 5pp）"，
> 不得写成"收敛后无差异 / 上界 / 等价"。这两条来自 `audit/reports/报告-21仓库-20261030.md` §2
> 与 `gates/三关定义与矩阵.md` §5 的更正记录。

---

## 目录导航

```
repo/
├── README.md                    本文件
├── USAGE.md                     逐条可复制命令：输入 / 输出 / 判据 / 是否需要 torch
├── verify_numbers.py            纯标准库：把上表每个数字从随包数据重算一遍（28 条断言）
├── requirements.txt             依赖分三档：stdlib / pandas / torch+numpy
├── LICENSE-DECISION-NEEDED.md   许可证候选人选与各自要求，留给作者决定
├── CITATION.cff                 引用元数据（占位）
├── gates/
│   ├── gate_check.py            三关检查器（原文拷贝，未改动）
│   └── 三关定义与矩阵.md          P1/P2/P3 形式化定义、阈值、失效→关卡矩阵
├── checker/
│   ├── test_r1_r8_local.py      60 项零 GPU 自检（含"反向用例"：旧实现必须被抓）
│   ├── test_guards_meta.py      6 项补测 G1–G6（杀掉变异测试暴露的盲区）
│   ├── silent_failure_guards.py fail-closed 断言模块（D1–D10 缺陷族的运行时防线）
│   └── README.md                这三个文件各断言什么、为什么需要私有 legged_gym 层
├── audit/
│   ├── scripts/audit_repo.py    C1/C2/C3 三条静态检查（纯 stdlib，Py3.8+）
│   ├── scripts/summarize_21.py  21 仓库结果汇总 → audit_21repos.csv
│   ├── audit_21repos.csv        21 仓库判定表（本包发布的关键审计数据）
│   ├── audit_12repos.csv        首轮 12 仓库部分抓取结果（含"部分文件不足以判定"的教训）
│   ├── out/*.json               21 个仓库的完整判定 + 证据行（summarize_21.py 的输入）
│   ├── shas.txt                 21 个 repo@sha（固定 ref）
│   ├── repos.csv                21 仓库清单与纳入理由
│   └── reports/                 两轮审计报告（含工具校准四次被"打脸"的记录）
├── mutation/
│   ├── mutation_run.py          变异测试 harness（原文拷贝）
│   ├── mutation_results.csv     21 个变异体逐条判定
│   ├── mutation_summary.json    score / CI / 存活列表 / 基线
│   ├── crash_M07..M10.log       4 个"以崩溃形式被抓"的变异体原始报错
│   └── reports/报告-20261028.md  57.1% → 90.5% 的完整证据链
└── data/
    ├── iter_metrics.csv         P2 关的输入（6000 行，两臂，19 个分项列）
    ├── ext_full.json            P3 关的输入（四臂的 500 迭代块序列，其中 3 臂参与判定）
    └── README.md                这两个文件为什么在这里、gate_check.py 期望它们在哪
```

**本包不含图数据**（`figs/`）：打包期间图正被重新生成，为避免发布半成品，图数据与出图脚本一律不纳入。
需要时由作者把最终 `figs/data/*.json` 单独加成。

---

## 快速开始（30 秒，纯标准库）

```bash
python verify_numbers.py        # 重算 README 里每个数字；28 条断言；退出码 0 = 一致
```

```
断言 28 条：PASS 28 / FAIL 0
```

然后按 [`USAGE.md`](USAGE.md) 逐关跑：`--p3`（纯 stdlib）→ `--p2`（需 pandas）→ `--p1`（需 torch + 私有 legged_gym 层）。

---

## 本包的实测状态（2026-11-01，本机 Windows + Python 3.10.4）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `python verify_numbers.py` | 28 条断言全过 | 0 |
| `python audit/scripts/summarize_21.py` | 重新生成的 `audit_21repos.csv` 与原文件**逐字节相同**（sha256 `7559d287…`） | 0 |
| `gate_check.py --p3` | **FAIL**（`free` 0.587 > 0.5） | 1 |
| `gate_check.py --p2` | PASS（裁剪质量 2.978；三窗口 −11.30/−11.73/−14.17，极差 2.864pp；可加性反例 12/6000 = 0.2%） | 0 |
| `gate_check.py --p1` | PASS（60/60 + 6/6） | 0 |
| `gate_check.py`（三关全跑） | P1 PASS、P2 PASS、P3 FAIL | 1 |

详见 [`../核验记录.md`](../核验记录.md)（每条命令的返回码与关键输出原文）。

---

## 引用

占位。作者、单位、年份、DOI 均待填，见 [`CITATION.cff`](CITATION.cff)。
在作者定稿前，请勿按现有条目引用本包。

论文标题（占位）：*Validity Gates for Fault-Injection Protocols in Robot Learning Simulations*。

---

## 许可证

**未定。** 本包不含任何许可证文件，因此默认"保留所有权利"。候选人选与各自要求
（MIT / Apache-2.0 / 数据部分 CC-BY-4.0）写在 [`LICENSE-DECISION-NEEDED.md`](LICENSE-DECISION-NEEDED.md)，
由作者决定后再加上 `LICENSE`。**在许可证落定之前不要公开推送本仓库。**

---

## 已知限制（读之前先看这一节）

1. **P1 关需要作者的私有代码层**：`checker/test_r1_r8_local.py` 与 `test_guards_meta.py` 要 import
   作者的 `legged_gym`（`fault_detector.py`、`a1_rescue_phase3_env.py`、`train.py` 等），本包**不含**这些
   私有文件。因此 P1 关在只有本包时**跑不起来**，报错形态见 `USAGE.md` §P1。P1 的实现与断言逻辑是公开的，
   可逐条阅读。
2. **变异测试不能公开重跑**：`mutation_run.py` 会复制并改写上述私有源树。本包提供的是**结果数据**与完整
   变异定义（21 条 `old`/`new` 补丁原文都写在 `mutation_run.py` 里），不是可独立运行的 harness。
3. **`gate_check.py` 用相对路径找输入**：它按"脚本所在目录的上一级"（`parents[1]`）解析
   `34-零成本三件套-20261027/data/iter_metrics.csv`、`35-收敛与种子检验-20261027/data/ext_full.json`、
   `代码修复-20261012/`。原文未改动，`USAGE.md` 给了照这个约定搭目录的复制粘贴命令。
4. **单 ref 审计**：每个仓库只取默认分支的一个 SHA（`audit/shas.txt`），不反映历史漂移；
   工具只给信号 + 暂定判定，C1/C3 的终判需人工复核。
5. **P3 是本研究未通过的一关**：本包如实保留这一失败，不做修饰。
6. **图数据不在本包内**：`figs/` 已被排除（打包期间图正在重出，避免发布半成品）。因此
   `8.94%`（修复后注入率）与 `68.8×` 这个比值在本包内**没有第二出处**，数字表里标为待补；
   需要时把最终的 `figs/data/*.json` 加进来，`verify_numbers.py` 会自动接管相关断言（图数据存在时才检）。
