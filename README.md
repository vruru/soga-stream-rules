# soga-stream-rules

自动把 [1stream 的 Xray 列表](https://raw.githubusercontent.com/1-stream/1stream-public-utils/refs/heads/main/stream.xray.list) 按地区转换成 Soga DNS YAML；GitHub Actions 每 5 分钟检测一次，只有生成文件内容发生变化才提交更新。

公开仓库：[vruru/soga-stream-rules](https://github.com/vruru/soga-stream-rules)。

规则目录：[rules/](https://github.com/vruru/soga-stream-rules/tree/main/rules)。原始文件地址格式为 `https://raw.githubusercontent.com/vruru/soga-stream-rules/main/rules/地区代码.yml`，例如 [HK.yml](https://raw.githubusercontent.com/vruru/soga-stream-rules/main/rules/HK.yml)。

## 地区规则

所有文件都排除整个 `China Media` 分组。它与 Global 等分组重复的域名仍保留，例如 Global 的 YouTube 和 iQiyi；不通过全局域名黑名单排除中国分组。

| 地区 | 当前生成文件 | 包含内容 |
| --- | --- | --- |
| 香港 | `HK.yml` | 除 China Media 外的全部分组，包括所有地区、全部 AI、Others |
| 台湾 | `TW.yml` | Global + Taiwan Media + Openai |
| 加拿大 | `CA.yml` | Global + Canada Media + Openai |
| 南美 | `SA.yml` | Global + South America Media + Openai |
| 日本 | `JP.yml` | Global + Japan Media + Openai |
| 美国 | `US.yml` | Global + North America Media + Openai |
| 韩国 | `KR.yml` | Global + Korean Media + Openai |
| 亚太 | `SG.yml`、`TH.yml`、`ID.yml`、`VN.yml`、`MY.yml`、`IN.yml`、`UAE.yml` | Global + SouthEastAsia media 共用组 + 本国组；IN 另加 Indian Media；按当前需求不加 AI |
| 欧洲 | `GB.yml`、`FR.yml`、`DE.yml`、`NL.yml`、`IT.yml`、`RU.yml`、`UA.yml`、`CH.yml`、`TR.yml` | Global + Europe Media 无前缀/EU 共用组 + 本国组 + Openai |
| 大洋洲 | `AU.yml`、`NZ.yml` | Global + `? media` + Oceania Media 共用组 + 本国组 + Openai |

当前共 25 个文件。`SA.yml` 表示南美。多国分组的国家代码从上游动态发现，新增国家会自动生成新文件；保留上游的 `UAE` 命名。兼容 `IT Rai Play` 空格前缀，并把 `NBA TV`、`HBO GO Asia` 识别为共用组。共用组出现在国家组之后时仍加入每个国家文件。

冒号国家前缀使用 ISO 两字母代码及 `UAE`；无冒号的两字母空格前缀只兼容已核实的 `IT`，其他形式报错，避免把 `TV 2 Play` 等服务名误当成国家。

保留来源分组注释；每个文件按选取分组的顺序去除完全相同的规则，不合并父域名和子域名。

## 规则 YAML 格式

规则字符串采用 [上游 Soga 示例](https://raw.githubusercontent.com/1-stream/1stream-public-utils/main/soga.yml) 中的写法，使用最新 Xray 列表作为规则来源。每个文件输出完整的单 DNS 配置，保留原分组注释，例如日本：

```yaml
tcp://nrt.core.access.zznet.fun:
  strategy: ipv4_first
  rules:
    # ---------- > Global Plaform
    # > Netflix
    - "domain:netflix.com"
```

初始头部默认 `strategy: ipv4_first`，DNS 地址如下：

| 文件 | 初始 DNS 地址 |
| --- | --- |
| HK.yml | `tcp://hkg.core.access.zznet.fun` |
| JP.yml | `tcp://nrt.core.access.zznet.fun` |
| SG.yml | `tcp://sin2.edge.access.zznet.fun` |
| US.yml | `tcp://lax.core.access.zznet.fun` |
| 其他地区及未来新增国家 | `tcp://example.com` |

**可以手动修改仓库中某个文件的 DNS 地址、strategy 和头部注释。自动更新原样保留现有文件从开头到 `  rules:` 行（含该行注释和换行）的内容，只替换下方规则与分组注释。** 默认头仅用于新文件以及旧版根列表的一次迁移；以后更改脚本默认值也不会重置现有文件头。

头部须保持单个 DNS 地址作为顶层键，`strategy` 和 `rules:` 缩进两格，规则缩进四格。支持头部注释、空行、端口、引号包裹的 DNS 地址和额外的简单标量字段；复杂嵌套字段、多个 DNS 顶层键不支持。不要删除 `rules:`，也不要在同一行填入规则列表。结构异常时整批更新报错并保留原文件，修正后下次任务继续更新。

不添加 `# generated` 或 `# region` 注释。`tcp://example.com` 是占位地址，使用其他地区文件前需要替换成你的 DNS 上游。Soga 实际加载和解锁效果尚未现场验证。

## 使用和验证

需要 Python 3.12 或更新版本。生产转换只用标准库；PyYAML 仅用于测试。

在本项目目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v

# 拉取上游并生成 rules/*.yml
.venv/bin/python scripts/update_rules.py

# 只比较，绝不写文件
.venv/bin/python scripts/update_rules.py --check

# 用已经下载的列表离线生成
.venv/bin/python scripts/update_rules.py --source-file /path/to/stream.xray.list

# 指定其他规则输出目录
.venv/bin/python scripts/update_rules.py \
  --output-dir /path/to/local-dns-rules
```

未指定输出目录时，写入脚本所属项目的 `rules/`，不依赖当前工作目录。退出码：`0` 为更新成功或无变化，`1` 为 `--check` 检测到差异，`2` 为网络、解析或写入错误。

## 自动更新

`.github/workflows/update-rules.yml` 提供定时和手动触发，也在脚本、测试、依赖或工作流修改后运行。定时表达式 `2-57/5 * * * *` 表示每小时第 2、7、12、17、22、27、32、37、42、47、52、57 分钟检查，间隔 5 分钟；GitHub 定时执行可能延迟。

GitHub 对连续 60 天没有仓库活动的公开仓库会自动停用定时工作流。长期无规则更新时，可在 Actions 页面重新启用工作流；这是 [GitHub schedule 的平台限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

PR 只运行测试，更新任务仅在仓库默认分支运行。生成任务拥有 `contents: write` 权限，分支保护或账户策略若阻止机器人推送，需要给该任务合适的发布权限。

只有 `rules/` 的实际内容变化才提交和推送；不把更新时间、上游全文或原文件哈希写入产物。普通注释和 China Media 内容变化不会造成无意义提交。国家/服务标题是输出中保留的注释，标题变化会反映到对应文件。

网络失败、必需分组缺失、无效活动规则、未知国家前缀、跨区国家代码冲突都会报错。活动规则支持 `domain:`、`full:`、`regexp:`、`keyword:`，其他前缀明确失败；未来遇到新的语法需先更新转换器。排除的 China Media 活动内容不参与解析。

已经发布的国家文件若从上游消失，脚本报错并保留所有旧文件，需要维护者确认移除或修正规则后再更新。其他文件不删除。全部输入/目标检查通过后才开始暂存，全部文件暂存成功后逐个原子替换；写盘失败会让任务失败并阻止 Git 提交。替换阶段的硬件故障不保证多个文件作为一个事务同时完成，可排除故障后重新生成。

## 维护入口

- `AGENTS.md`：本项目维护约定。
- `scripts/update_rules.py`：解析、地区组合、生成和文件更新。
- `tests/test_update_rules.py`：地区集合、隔离、动态发现、结构、稳定性和失败保护测试。
- `rules/*.yml`：公开的完整 DNS 配置；允许手动修改头部，rules 下内容由脚本生成。

上游未附加到此项目，临时列表、下载文件、密钥和令牌不应进入公共仓库。
