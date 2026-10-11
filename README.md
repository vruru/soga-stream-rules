# soga-stream-rules

自动把 [1stream 的 Xray 列表](https://raw.githubusercontent.com/1-stream/1stream-public-utils/refs/heads/main/stream.xray.list) 按地区转换成 Soga DNS YAML；GitHub Actions 每 6 小时检测一次，只有生成文件内容发生变化才提交更新。

公开仓库：[vruru/soga-stream-rules](https://github.com/vruru/soga-stream-rules)。

规则目录：[rules/](https://github.com/vruru/soga-stream-rules/tree/main/rules)。原始文件地址格式为 `https://raw.githubusercontent.com/vruru/soga-stream-rules/main/rules/地区代码.yml`，例如 [HK.yml](https://raw.githubusercontent.com/vruru/soga-stream-rules/main/rules/HK.yml)。

## 地区规则

所有文件都排除整个 `China Media` 分组。它与 Global 等分组重复的域名仍保留，例如 Global 的 YouTube 和 iQiyi；不通过全局域名黑名单排除中国分组。

| 地区 | 当前生成文件 | 包含内容 |
| --- | --- | --- |
| 香港 | `HK.yml` | 除 China Media 外的全部分组，包括所有地区、全部 AI、Others |
| 台湾 | `TW.yml` | Global + Taiwan Media + Openai |
| 日本 | `JP.yml` | Global + Japan Media + Openai |
| 美国 | `US.yml` | Global + North America Media + Openai |
| 韩国 | `KR.yml` | Global + Korean Media + Openai |
| 亚太 | `SG.yml`、`TH.yml`、`ID.yml`、`VN.yml`、`MY.yml`、`IN.yml`、`UAE.yml` | Global + SouthEastAsia media 共用组 + 本国组；IN 另加 Indian Media；按当前需求不加 AI |
| 欧洲 | `GB.yml`、`FR.yml`、`DE.yml`、`NL.yml`、`IT.yml`、`RU.yml`、`UA.yml`、`CH.yml`、`TR.yml` | Global + Europe Media 无前缀/EU 共用组 + 本国组 + Openai |
| 大洋洲 | `AU.yml`、`NZ.yml` | Global + `? media` + Oceania Media 共用组 + 本国组 + Openai |

当前共 23 个文件。多国分组的国家代码从上游动态发现，新增国家会自动生成新文件；保留上游的 `UAE` 命名。兼容 `IT Rai Play` 空格前缀，并把 `NBA TV`、`HBO GO Asia` 识别为共用组。共用组出现在国家组之后时仍加入每个国家文件。

冒号国家前缀使用 ISO 两字母代码及 `UAE`；无冒号的两字母空格前缀只兼容已核实的 `IT`，其他形式报错，避免把 `TV 2 Play` 等服务名误当成国家。

保留来源分组注释；每个文件按选取分组的顺序去除完全相同的规则，不合并父域名和子域名。

## Soga YAML 格式

输出结构参考 [上游 Soga 示例](https://raw.githubusercontent.com/1-stream/1stream-public-utils/main/soga.yml)，使用最新 Xray 列表作为规则来源，不从该 Soga 示例抽取规则：

```yaml
"https://example.com/dns-query":
  strategy: ipv4_only
  rules:
    # ---------- > Global Plaform
    # > Netflix
    - "domain:netflix.com"
```

`https://example.com/dns-query` 是占位地址，不提供实际 DNS 服务。使用文件时应替换成实际的 DoH 地址。这些文件是 DNS 分流模板，尚未在运行中的 Soga 上验证加载和解锁效果。

可以通过 `--dns-server` 生成使用实际地址的本地文件。公共仓库中不能保存带凭据的 DNS 地址；脚本拒绝 URL 用户名/密码、查询参数、片段和空白。

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

# 在仓库外生成带实际 DNS 的本地配置
.venv/bin/python scripts/update_rules.py \
  --dns-server https://dns.example.net/dns-query \
  --output-dir /path/to/local-dns-rules
```

未指定输出目录时，写入脚本所属项目的 `rules/`，不依赖当前工作目录。退出码：`0` 为更新成功或无变化，`1` 为 `--check` 检测到差异，`2` 为网络、解析或写入错误。

## 自动更新

`.github/workflows/update-rules.yml` 提供定时和手动触发，也在脚本、测试、依赖或工作流修改后运行。定时表达式 `17 */6 * * *` 对应北京时间约每天 02:17、08:17、14:17、20:17；GitHub 定时执行可能延迟。

GitHub 对连续 60 天没有仓库活动的公开仓库会自动停用定时工作流。长期无规则更新时，可在 Actions 页面重新启用工作流；这是 [GitHub schedule 的平台限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

PR 只运行测试，更新任务仅在仓库默认分支运行。生成任务拥有 `contents: write` 权限，分支保护或账户策略若阻止机器人推送，需要给该任务合适的发布权限。可在 GitHub Actions Variables 设置不含凭据的 `DNS_SERVER`，不设置时沿用占位地址。

只有 `rules/` 的实际内容变化才提交和推送；不把更新时间、上游全文或原文件哈希写入产物。普通注释和 China Media 内容变化不会造成无意义提交。国家/服务标题是输出中保留的注释，标题变化会反映到对应文件。

网络失败、必需分组缺失、无效活动规则、未知国家前缀、跨区国家代码冲突都会报错。活动规则支持 `domain:`、`full:`、`regexp:`、`keyword:`，其他前缀明确失败；未来遇到新的语法需先更新转换器。排除的 China Media 活动内容不参与解析。

已经发布的国家文件若从上游消失，脚本报错并保留所有旧文件，需要维护者确认移除或修正规则后再更新。其他文件不删除。全部输入/目标检查通过后才开始暂存，全部文件暂存成功后逐个原子替换；写盘失败会让任务失败并阻止 Git 提交。替换阶段的硬件故障不保证多个文件作为一个事务同时完成，可排除故障后重新生成。

## 维护入口

- `AGENTS.md`：本项目维护约定。
- `scripts/update_rules.py`：解析、地区组合、生成和文件更新。
- `tests/test_update_rules.py`：地区集合、隔离、动态发现、结构、稳定性和失败保护测试。
- `rules/*.yml`：自动生成的公开规则模板，不手动编辑。

上游未附加到此项目，临时列表、下载文件和本地 DNS 配置不应进入公共仓库。
