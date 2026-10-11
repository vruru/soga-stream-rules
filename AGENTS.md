# soga-stream-rules

先读 README.md 确认地区组合、Soga DNS YAML 结构和更新方式。

- 核心入口：scripts/update_rules.py；验证：python -m unittest discover -s tests -v。
- rules/*.yml 是生成产物，修改解析/地区策略后重新生成，不手改。
- 上游来源只使用 README 指定的公开列表；任何未知活动语法、缺失必需分组和已发布国家消失都应失败并保留旧文件。
- 网络生成与本地输入共用同一解析路径；生产仅使用 Python 标准库，PyYAML 是测试依赖。
- GitHub Actions 仅在默认分支更新；生成内容未改变时不提交；不删除非本项目文件，不强推。
- 用户已确认独立公开仓库 vruru/soga-stream-rules；提交前核对远端和本次变更范围，不能归入附近仓库。
- 公开规则使用 example.com DNS 占位地址。DNS 凭据、真实节点配置、缓存和临时输入不得上传。
