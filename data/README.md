# data/ —— 三关检查器的输入数据

两个文件都是**从原始实验目录只读拷贝**来的，内容未改动。它们存在于本包的唯一目的：
让 `gates/gate_check.py --p2` 与 `--p3` 在没有私有代码层的情况下也能跑起来。

| 文件 | 来源（作者本地路径） | 大小 | 谁用它 | 内容 |
|---|---|---|---|---|
| `iter_metrics.csv` | `[workspace]/34-零成本三件套-20261027/data/iter_metrics.csv` | 1 180 714 B | `gate_check.py --p2` | 6000 行 × 27 列；两臂（`free_swing` / `lock`）；含 `Mean_reward` 与 19 个 `Mean_episode_rew_*` 分项列 |
| `ext_full.json` | `[workspace]/35-收敛与种子检验-20261027/data/ext_full.json` | 3 839 B | `gate_check.py --p3` | 4 个臂的 500 迭代块序列（`blocks[].R`） |

---

## 一、P2 的输入：`iter_metrics.csv`

列结构（实测前 6 列）：`arm, iter, Mean_action_noise_std, Mean_episode_length, Mean_episode_rew_action_rate, Mean_episode_rew_ang_vel_xy, …`

`gate_check.py::check_p2()` 只做三件事：

1. 把 19 个 `Mean_episode_rew_*` 求和 × 20.0 得到"未裁剪回报"的复算值；
2. `clip_mass = Mean_reward − 未裁剪`，统计 `clip_mass < 0` 的条数（可加性反例）；
3. 按 `arm` 取末 100 / 300 / 500 行，算 `(lock − free_swing) / |free_swing|` 的百分比。

**注意那个常数 20.0**：它把分项（每步平均）换算成回合量级，是脚本里的硬编码，不是从数据读出来的。
读脚本时不要以为它是自动推断的。

实测输出（见 `../USAGE.md` §5.2）：裁剪质量均值 2.978、三窗口 −11.30/−11.73/−14.17（极差 2.864pp）、
可加性反例 12/6000 = 0.2%。

---

## 二、P3 的输入：`ext_full.json`

结构：顶层 4 个键，每个值是 `{"blocks": [{"R": <float>, …}, …]}`。

| 臂 | 块数 | 块序列（`R`） | 是否参与 P3 判定 |
|---|---|---|---|
| `free_ext2` | 4 | 17.9404, 18.439, 18.8673, 18.2805 | 是（末两块差 **0.587**） |
| `lock_ext` | 4 | 15.3657, 15.6808, 16.6021, 17.7476 | 是（末两块差 1.145，末三块单调） |
| `lock_ext3` | 3 | 17.4892, 18.1423, 18.3929 | 是（末两块差 0.251，末三块单调） |
| `lock_ext_probe` | 1 | 13.3725 | **否**——`gate_check.py` 里 `if len(blocks) < 2: continue` 直接跳过 |

`lock_ext_probe` 只有 1 块，是个探针运行，不足以判平台。它在文件里但被脚本跳过；
`verify_numbers.py` 也只校验参与判定的三个臂，**不**把探针算进"三臂"。

判定阈值：`|末两块差| < 0.5` 且末三块不单向单调。实测三臂**全部不通过**，
其中 `lock_ext3` 的失败原因是"末三块仍单调上升"（不是幅度超阈值）。

---

## 三、`gate_check.py` 期望它们在哪（这是最容易踩的坑）

脚本按自己的位置解析路径，读的是：

```python
E1_CSV   = PRJ / "34-零成本三件套-20261027" / "data" / "iter_metrics.csv"
EXT_JSON = PRJ / "35-收敛与种子检验-20261027" / "data" / "ext_full.json"
```

其中 `PRJ` = 脚本所在目录的**上两级**。所以直接把本包的 `gates/gate_check.py` 拿来跑，
它会去 `repo/../34-零成本三件套-20261027/data/` 找文件——**找不到**。

照 `../USAGE.md` §1 搭好那个目录（把本目录两个文件复制成脚本期望的名字与位置）即可。
`--p3` 缺文件时会返回 `{"gate":"P3","pass":false,"reason":"缺少 <路径>"}`（这是脚本里显式写的一支，
不会崩）；`--p2` 缺文件则会抛 `FileNotFoundError`。

---

## 四、为什么不把这些文件改名成更漂亮的英文名

因为 `gate_check.py` 是**原文拷贝**（论文的数字必须能指到未改动的代码），
它的路径是硬编码的中文目录名。改名会让"脚本原文"与"可跑"二者只能取一。
保持原样 + 在文档里说清，是这里选择的折中。
