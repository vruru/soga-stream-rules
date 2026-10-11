# soga-stream-rules

先读 README.md 确认地区组合、Soga DNS YAML 结构和更新方式。

- 核心入口：scripts/update_rules.py；验证：python -m unittest discover -s tests -v。
- rules/*.yml 的 rules 列表和分组注释是生成产物；DNS 头部允许手动修改，更新必须原样保留现有头部。
- 上游来源只使用 README 指定的公开列表；任何未知活动语法、缺失必需分组和已发布国家消失都应失败并保留旧文件。
- 网络生成与本地输入共用同一解析路径；生产仅使用 Python 标准库，PyYAML 是测试依赖。
- GitHub Actions 仅在默认分支更新；生成内容未改变时不提交；不删除非本项目文件，不强推。
- 用户已确认独立公开仓库 vruru/soga-stream-rules；提交前核对远端和本次变更范围，不能归入附近仓库。
- 输出为完整的单 DNS 配置，含 DNS 地址、strategy 和 rules；保留原分组注释，不添加 generated/region 注释。用户已授权公开指定的四个 DNS 地址；其他地区初始使用 tcp://example.com。仅新建文件或旧根列表迁移时使用默认头，日常更新只替换 rules 下内容。
- 头部结构异常必须在整批写入前报错，不得用默认值覆盖手工配置。密钥、令牌、缓存和临时输入不得上传。
