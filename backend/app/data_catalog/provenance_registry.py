"""Static GitHub and producer registry for source provenance.

This registry is deliberately a Python constant so the backend route has no
deployment-time dependency on a root JSON/YAML file.  It records GitHub projects
as reference intelligence only; it must not turn a repository into a true data
producer unless another local evidence source says so.
"""
# ruff: noqa: RUF001

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from urllib.parse import urlparse

GithubReferenceData = dict[str, object]
ProducerData = dict[str, str]


PRODUCERS: dict[str, ProducerData] = {
    "tickflow": {
        "producer_id": "tickflow",
        "name": "TickFlow SDK",
        "kind": "sdk_provider",
        "role": "market_data_provider",
        "access": "configured_provider",
        "note": "Declared or observed local provider; not a GitHub repository.",
    },
    "eastmoney": {
        "producer_id": "eastmoney",
        "name": "EastMoney public endpoints",
        "kind": "public_web_endpoint",
        "role": "market_data_endpoint",
        "access": "http",
        "note": "Public endpoint evidence; rights, rate limits, and field drift require gates.",
    },
    "cls": {
        "producer_id": "cls",
        "name": "财联社公开市场端点",
        "kind": "public_web_endpoint",
        "role": "market_pulse_producer",
        "access": "http",
        "note": "指数分时与板块异动由财联社公开端点返回；接口稳定性、访问限制和数据权利需要持续复核。",
    },
    "sina": {
        "producer_id": "sina",
        "name": "Sina finance endpoints",
        "kind": "public_web_endpoint",
        "role": "market_data_endpoint",
        "access": "http",
        "note": "Public endpoint evidence; not a GitHub project.",
    },
    "tencent": {
        "producer_id": "tencent",
        "name": "Tencent finance endpoints",
        "kind": "public_web_endpoint",
        "role": "market_data_endpoint",
        "access": "http",
        "note": "Public endpoint evidence; not a GitHub project.",
    },
    "tdx_public": {
        "producer_id": "tdx_public",
        "name": "通达信公开行情服务器池",
        "kind": "public_market_data_server_pool",
        "role": "historical_intraday_producer",
        "access": "tdx_tcp_protocol",
        "note": "真实数据由公开 TDX 行情服务器返回；easy_tdx 仅是 one-trading 使用的协议客户端。",
    },
    "cninfo": {
        "producer_id": "cninfo",
        "name": "CNINFO 巨潮资讯",
        "kind": "official_web_endpoint",
        "role": "announcement_metadata_producer",
        "access": "http",
        "note": "Official announcement metadata source when observed in lineage.",
    },
    "exchange_calendar": {
        "producer_id": "exchange_calendar",
        "name": "Exchange calendar pages",
        "kind": "official_web_endpoint",
        "role": "trading_calendar_producer",
        "access": "http",
        "note": "Exchange calendar evidence when observed in lineage.",
    },
    "public_quote": {
        "producer_id": "public_quote",
        "name": "腾讯 / 新浪公开行情端点",
        "kind": "public_web_endpoint",
        "role": "quote_and_eod_fallback",
        "access": "http",
        "note": "one-trading 公开行情链使用的腾讯主源与新浪兜底；不是 GitHub 项目。",
    },
    "csindex": {
        "producer_id": "csindex",
        "name": "中证指数官网 / 新浪成分兜底",
        "kind": "official_and_public_endpoints",
        "role": "index_constituent_producer",
        "access": "http/xlsx",
        "note": "股票池以中证指数公开文件为主，新浪为失败兜底。",
    },
    "tickflow_extension_files": {
        "producer_id": "tickflow_extension_files",
        "name": "TickFlow 扩展文件服务",
        "kind": "configured_file_endpoint",
        "role": "ths_membership_snapshot",
        "access": "https",
        "note": "files.688798.xyz 上的同花顺概念/行业快照；需结合更新时间判断新鲜度。",
    },
    "go_stock_snapshot": {
        "producer_id": "go_stock_snapshot",
        "name": "go-stock 本地历史快照",
        "kind": "local_snapshot_fallback",
        "role": "fund_flow_history_fallback",
        "access": "local SQLite import",
        "note": "只在 lineage 实际观测到 go-stock 本地快照时出现；不是资金流数据集的父母。主路径生产者是东方财富。",
    },
    "public": {
        "producer_id": "public",
        "name": "one-trading public provider",
        "kind": "local_provider_adapter",
        "role": "provider_adapter",
        "access": "local_adapter",
        "note": "Local adapter that may wrap public endpoints; inspect lineage for real producer.",
    },
    "local": {
        "producer_id": "local",
        "name": "one-trading local files",
        "kind": "local_materialization",
        "role": "local_dataset",
        "access": "filesystem",
        "note": "Local materialized data; true upstream producer needs lineage or config evidence.",
    },
    "derived_local": {
        "producer_id": "derived_local",
        "name": "one-trading 本地派生",
        "kind": "local_derivation",
        "role": "derived_reference_dataset",
        "access": "local computation",
        "note": "由本地已落库数据(日线/增强日线/股本/成分池等)派生计算, 构建过程零外部请求; 上游真实生产者见各输入数据集的来源披露。",
    },
    "custom_http": {
        "producer_id": "custom_http",
        "name": "Configured custom HTTP endpoint",
        "kind": "configured_endpoint",
        "role": "extension_pull_endpoint",
        "access": "http",
        "note": "Configured ext_data pull endpoint; not verified as authoritative producer.",
    },
    "user_upload": {
        "producer_id": "user_upload",
        "name": "User-managed external data",
        "kind": "manual_or_local_extension",
        "role": "extension_data",
        "access": "filesystem",
        "note": "User or local extension data without an explicit pull endpoint.",
    },
    "hithink_fuyao": {
        "producer_id": "hithink_fuyao",
        "name": "同花顺官方金融数据服务",
        "kind": "official_api",
        "role": "official_special_data_producer",
        "access": "https_api_key",
        "note": "真实生产者是 fuyao.aicubes.cn；GitHub Financial-API 只是客户端情报。账号、ToS 与配额以官网为准。集合竞价 auction_volume 单位为手。",
    },
}


DECLARED_PRODUCERS_BY_SUBJECT: dict[str, tuple[str, ...]] = {
    "stock_minute": ("tdx_public",),
    "stock_adj_factor": ("sina", "eastmoney"),
    "quote_snapshot": ("public_quote",),
    "sealed_l1": ("public_quote",),
    "pools": ("csindex",),
    "trading_calendar": ("exchange_calendar",),
    "financial_metrics": ("eastmoney",),
    "financial_income": ("eastmoney",),
    "financial_balance_sheet": ("eastmoney",),
    "financial_cash_flow": ("eastmoney",),
    "financial_shares": ("eastmoney",),
    "stock_margin_trading": ("eastmoney",),
    "market_pulse": ("cls",),
    "valuation_daily": ("derived_local",),
    "limit_up_events": ("derived_local",),
    "index_membership_history": ("derived_local", "csindex"),
    "corporate_actions": ("eastmoney", "derived_local"),
    "hithink_limit_pool": ("hithink_fuyao",),
    "hithink_dragon_tiger": ("hithink_fuyao",),
    "hithink_auction_snapshot": ("hithink_fuyao",),
    "hithink_valuation_snapshot": ("hithink_fuyao",),
}


# 数据集"数据说明/提供内容"中文文案。由 /api/data/source-provenance 下发,
# 前端来源追踪面板直接渲染; 新增数据集时必须同步补一条(有守护测试锁定)。
SUBJECT_EXPLANATIONS: dict[str, dict[str, str]] = {
    "stock_instruments": {
        "category": "股票基础资料",
        "cadence": "逐股票快照",
        "description": "A 股股票的基础维表，为证券检索、代码映射以及行情、财务数据关联提供统一标识。",
        "provides": "股票代码、名称、交易所、上市日期、总股本、流通股本、最小价格变动与涨跌停价格。",
    },
    "stock_daily": {
        "category": "股票日线行情",
        "cadence": "日频时序",
        "description": "按股票和交易日保存的日 K 行情，是图表、选股、回测和增强数据计算的基础。",
        "provides": "交易日期、开盘价、最高价、最低价、收盘价、成交量与成交额。",
    },
    "stock_enriched": {
        "category": "股票增强日线",
        "cadence": "日频衍生时序",
        "description": "在股票日 K 基础上形成的持久化增强窄表，用于直接消费复权价格和常用衍生指标。",
        "provides": "日 K 字段、原始高低收价格、换手率以及连续涨跌停等增强字段。",
    },
    "stock_minute": {
        "category": "股票分钟行情",
        "cadence": "分钟时序",
        "description": "按股票和分钟组织的盘中行情，用于分时图、日内观察和分钟级策略研究。",
        "provides": "分钟时间、开盘价、最高价、最低价、收盘价、成交量与成交额。",
    },
    "stock_adj_factor": {
        "category": "股票复权因子",
        "cadence": "日频参考数据",
        "description": "记录股票在各交易日的价格复权系数，用于把原始价格转换为前复权或后复权口径。",
        "provides": "股票标识、交易日期与复权因子，不直接提供完整 K 线。",
    },
    "etf_instruments": {
        "category": "ETF 基础资料",
        "cadence": "逐标的快照",
        "description": "ETF 标的维表，为基金检索、代码映射以及 ETF 行情数据关联提供统一标识。",
        "provides": "ETF 代码、名称与资产分类等基础字段。",
    },
    "etf_daily": {
        "category": "ETF 日线行情",
        "cadence": "日频时序",
        "description": "按 ETF 和交易日保存的日 K 行情，用于 ETF 图表、比较、回测和资产配置研究。",
        "provides": "交易日期、开盘价、最高价、最低价、收盘价、成交量与成交额。",
    },
    "etf_enriched": {
        "category": "ETF 增强日线",
        "cadence": "日频衍生时序",
        "description": "在 ETF 日 K 基础上生成的增强窄表，便于直接使用复权后与原始价格口径。",
        "provides": "日 K 字段以及原始高价、低价和收盘价。",
    },
    "etf_minute": {
        "category": "ETF 分钟行情",
        "cadence": "分钟时序",
        "description": "按 ETF 和分钟组织的盘中行情，用于分时观察和分钟级交易研究。",
        "provides": "分钟时间、开盘价、最高价、最低价、收盘价、成交量与成交额。",
    },
    "etf_adj_factor": {
        "category": "ETF 复权因子",
        "cadence": "日频参考数据",
        "description": "记录 ETF 在各交易日的价格复权系数，用于统一历史价格口径。",
        "provides": "ETF 标识、交易日期与复权因子。",
    },
    "index_instruments": {
        "category": "指数基础资料",
        "cadence": "逐指数快照",
        "description": "市场指数维表，为指数检索、代码映射以及指数行情关联提供统一标识。",
        "provides": "指数代码、名称与资产分类等基础字段。",
    },
    "index_daily": {
        "category": "指数日线行情",
        "cadence": "日频时序",
        "description": "按指数和交易日保存的日 K 行情，用于基准比较、市场趋势观察和指数回测。",
        "provides": "交易日期、开盘点位、最高点位、最低点位、收盘点位、成交量与成交额。",
    },
    "index_enriched": {
        "category": "指数增强日线",
        "cadence": "日频衍生时序",
        "description": "在指数日 K 基础上形成的增强窄表，同时保留当前计算口径与原始价格字段。",
        "provides": "指数日 K 字段以及原始高点、低点和收盘点位。",
    },
    "quote_snapshot": {
        "category": "统一行情快照",
        "cadence": "市场日快照",
        "description": "股票、ETF 和指数的统一行情快照，主要用于当日行情补充、公开源兜底与跨资产快速读取。",
        "provides": "标的、日期、开高低收、成交量、成交额、来源和单位版本。",
    },
    "sealed_l1": {
        "category": "封板 L1 摘要",
        "cadence": "逐次采集快照",
        "description": "利用一级买卖盘数量形成的涨停或跌停封板判断摘要，不等同于真实五档盘口。",
        "provides": "封涨停、封跌停、买一卖一数量、方向状态与采集时间。",
    },
    "depth5": {
        "category": "五档盘口",
        "cadence": "逐报价时点",
        "description": "按标的和报价时间组织的真实五档买卖盘结构，用于盘口深度和流动性研究。",
        "provides": "买卖一至五档价格、对应数量以及报价时间。",
    },
    "pools": {
        "category": "股票池成分",
        "cadence": "成分快照",
        "description": "记录某个股票池在指定日期包含哪些股票，用于指数成分、策略范围和候选集管理。",
        "provides": "股票池标识、股票标识与成分快照日期。",
    },
    "trading_calendar": {
        "category": "交易日历",
        "cadence": "逐交易所逐日",
        "description": "记录沪深北交易所每个自然日是否开市，是同步调度、缺口判断和交易日计算的基础。",
        "provides": "交易所、日期、开闭市状态、交易时段类型、开收盘时间与来源。",
    },
    "ext_data": {
        "category": "扩展数据余项",
        "cadence": "动态结构",
        "description": "只收未单独建目录项的用户自建扩展表；固定资金流和同花顺分类池已拆成独立目录项。",
        "provides": "字段、粒度和更新方式由每个用户扩展配置单独定义。",
    },
    "financial_metrics": {
        "category": "财务指标",
        "cadence": "报告期时序",
        "description": "按股票和报告期整理的财务比率与指标，用于基本面筛选和跨期比较。",
        "provides": "报告期、公告日期以及 ROE 等代表性财务指标。",
    },
    "financial_income": {
        "category": "利润表",
        "cadence": "报告期时序",
        "description": "按股票和报告期保存的利润表数据，用于分析收入、成本和盈利表现。",
        "provides": "报告期、公告日期、营业收入及其他利润表科目。",
    },
    "financial_balance_sheet": {
        "category": "资产负债表",
        "cadence": "报告期时序",
        "description": "按股票和报告期保存的资产负债表数据，用于分析资产、负债和所有者权益结构。",
        "provides": "报告期、公告日期、资产总额及其他资产负债表科目。",
    },
    "financial_cash_flow": {
        "category": "现金流量表",
        "cadence": "报告期时序",
        "description": "按股票和报告期保存的现金流量表数据，用于分析经营、投资和筹资现金流。",
        "provides": "报告期、公告日期、经营活动净现金流及其他现金流科目。",
    },
    "financial_shares": {
        "category": "股本结构",
        "cadence": "报告期时序",
        "description": "按股票和报告期记录总股本与流通股本，为市值、换手率和每股指标计算提供分母。",
        "provides": "报告期、公告日期、总股本与流通股本。",
    },
    "stock_margin_trading": {
        "category": "股票 F10",
        "cadence": "交易日日频",
        "description": "按股票和交易日保存融资融券数据，用于观察杠杆资金、融券活动及两融余额变化。",
        "provides": "融资余额、融资买入与偿还、融资净买入、融券余额与数量，以及两融余额；金额为人民币元，数量为股。",
    },
    "market_pulse": {
        "category": "市场脉搏",
        "cadence": "交易日分钟与事件时序",
        "description": "把上证指数分钟点和财联社板块异动事件锁定在同一交易日，用于盘中主线观察、历史复盘和板块跳转。",
        "provides": "指数点位、分钟成交量与成交额、板块名称、异动方向、事件时间、来源和单位版本。",
    },
    "valuation_daily": {
        "category": "派生估值",
        "cadence": "交易日日频（本地派生）",
        "description": "由本地未复权日线与严格 PIT 股本派生的日频估值表；股本无权威公告日时市值保持诚实空值，PE/PB 等待权威历史估值源接入。",
        "provides": "收盘价、总市值、流通市值、总股本、流通股本、PIT 安全标记与股本来源；覆盖范围随当日日线分区如实披露。",
    },
    "limit_up_events": {
        "category": "派生涨跌停事件",
        "cadence": "交易日事件（本地派生）",
        "description": "按板块与 ST 规则从本地未复权日线推算的收盘口径涨跌停事件，含封板、炸板与跌停状态；不含盘中封单时序。",
        "provides": "事件状态、板块、规则涨跌停价、前收盘、连板高度、同日封单量与规则依据；ST 判定基于当前名称快照。",
    },
    "index_membership_history": {
        "category": "成分观察历史",
        "cadence": "快照差分（本地派生）",
        "description": "基于本地成分池快照差分维护的指数成员区间表；是本地观察历史，不是交易所官方修订史。",
        "provides": "指数代码、成员标的、观察起止日期、快照来源与 snapshot_seed/snapshot_diff 依据。",
    },
    "corporate_actions": {
        "category": "公司行动",
        "cadence": "事件时序",
        "description": "东方财富分红送转批量报表的正式事实，叠加复权因子派生的验证信号并做双向核对；不一致事件被隔离标记。",
        "provides": "事件类型、公告/登记/除权日期、每股派现、送转比例、实施进度、来源与验证状态；金额为税前人民币元。",
    },
    "hithink_limit_pool": {
        "category": "官方涨跌停池",
        "cadence": "交易日全市场快照",
        "description": "同花顺官方涨停、跌停与炸板池的独立事实层，补本地派生涨跌停事件没有的官方原因文本与封板时间；不覆盖 limit_up_events。",
        "provides": "池类别、股票代码、交易日、涨停原因、封板时间、连板天数、封单金额、来源与单位版本。",
    },
    "hithink_dragon_tiger": {
        "category": "官方龙虎榜",
        "cadence": "交易日全市场快照",
        "description": "同花顺官方龙虎榜独立事实层，按交易日保存上榜股票与买卖金额；不并入既有派生表。",
        "provides": "股票代码、交易日、榜单类型、涨跌幅、买卖与净额、机构/游资净额、上榜原因、来源与单位版本。",
    },
    "hithink_auction_snapshot": {
        "category": "官方集合竞价快照",
        "cadence": "自选股按需快照",
        "description": "同花顺官方集合竞价实时或终态快照，默认只同步本地自选股；竞价量单位为手，不是股。",
        "provides": "股票代码、交易日、阶段、竞价价格与涨跌幅、竞价量(手)、竞价额(元)、未匹配量、来源与单位版本。",
    },
    "hithink_valuation_snapshot": {
        "category": "官方最新估值快照",
        "cadence": "自选股最新快照，非历史 PIT",
        "description": "同花顺官方最新五项估值快照，默认只同步本地自选股；不得写入 valuation_daily，也不能冒充历史估值序列。",
        "provides": "股票代码、快照日期、PE TTM/MRQ、PB MRQ、PS TTM、PCF TTM、来源与单位版本；空值和负数原样保留。",
    },
    "ext_fund_flow_bk": {
        "category": "行业资金流快照",
        "cadence": "按需快照",
        "description": "行业板块在当前观察时点的资金流排名，用于快速判断行业资金偏好。",
        "provides": "板块名称、主力净流入、涨跌幅、排名、日期、来源和金额单位。",
    },
    "ext_fund_flow_bk_daily": {
        "category": "行业资金流历史",
        "cadence": "日频时序",
        "description": "行业板块资金流的日级历史序列，用于回看主力与不同订单规模资金的变化。",
        "provides": "板块、日期、主力及小中大单净流入、主力净占比、来源和金额单位。",
    },
    "ext_fund_flow_concept": {
        "category": "概念资金流快照",
        "cadence": "按需快照",
        "description": "概念板块在当前观察时点的资金流排名，用于快速判断主题资金偏好。",
        "provides": "概念名称、主力净流入、涨跌幅、排名、日期、来源和金额单位。",
    },
    "ext_fund_flow_concept_daily": {
        "category": "概念资金流历史",
        "cadence": "日频时序",
        "description": "概念板块资金流的日级历史序列，用于回看主题资金在不同日期的变化。",
        "provides": "概念、日期、主力及小中大单净流入、主力净占比、来源和金额单位。",
    },
    "ext_fund_flow_stock": {
        "category": "个股资金流",
        "cadence": "日频时序",
        "description": "个股资金流的日级历史序列，按需刷新，用于观察单只股票主力与分档资金变化。",
        "provides": "股票、日期、主力及小中大单净流入、主力净占比、来源和金额单位。",
    },
    "ext_gn_ths": {
        "category": "概念归属",
        "cadence": "分类快照",
        "description": "股票与同花顺概念分类的对应关系，用于概念聚合、筛选和概念分析页面。",
        "provides": "股票代码、股票简称与所属概念。",
    },
    "ext_hy_ths": {
        "category": "行业归属",
        "cadence": "分类快照",
        "description": "股票与同花顺行业分类的对应关系，用于行业聚合、筛选和行业分析页面。",
        "provides": "股票代码、股票简称与所属同花顺行业。",
    },
}


def explanation_for_subject(
    subject_id: str,
    *,
    subject_kind: str = "dataset",
    title: str = "",
) -> dict[str, str]:
    """返回数据集/扩展对象的中文说明; 未登记时给出诚实的通用文案。"""
    known = SUBJECT_EXPLANATIONS.get(subject_id)
    if known:
        return dict(known)
    is_extension = subject_kind == "extension"
    display = title or subject_id
    return {
        "category": "扩展数据" if is_extension else "目录数据",
        "cadence": "结构以当前定义为准",
        "description": f"{display} 是数据台中已登记的{'扩展数据对象' if is_extension else '标准数据集'}。",
        "provides": "具体字段、粒度和时间范围以数据目录中的 Schema 与当前物理数据为准。",
    }


GITHUB_PROJECTS: dict[str, GithubReferenceData] = {
    "tickflow-stock-panel": {
        "project_id": "tickflow-stock-panel",
        "name": "shy3130/tickflow-stock-panel",
        "repo_url": "https://github.com/shy3130/tickflow-stock-panel",
        "pinned_ref": "6e4d6b9",
        "commit_url": "https://github.com/shy3130/tickflow-stock-panel/commit/6e4d6b9784c16c3d7306e6c9bc0ca81733c88f2d",
        "reviewed_at": "2026-07-29",
        "roles": ["host", "engineering_mechanism"],
        "contributions": "提供产品宿主、TickFlow 主数据链、Custom HTTP 形态及 Parquet/数据台工程基座；one-trading 运行时由本地代码持有。",
        "runtime_dependency": False,
        "adoption_status": "host_reference_owned_local_runtime",
        "evidence_level": "E3",
    },
    "go-stock": {
        "project_id": "go-stock",
        "name": "ArvinLovegood/go-stock",
        "repo_url": "https://github.com/ArvinLovegood/go-stock",
        "pinned_ref": "40444c76 / 5ba83d42",
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东方财富/新浪/腾讯请求参数、资金流与 F10 字段语义。one-trading 自有 Adapter 持有运行时；仓库不是生产者，行业/概念资金流日线主路径也不再用其本地 stock.db。",
        "runtime_dependency": False,
        "adoption_status": "reference_only_no_gpl_runtime",
        "evidence_level": "E3",
    },
    "akshare": {
        "project_id": "akshare",
        "name": "akfamily/akshare",
        "repo_url": "https://github.com/akfamily/akshare",
        "pinned_ref": "fcdbf25",
        "commit_url": "https://github.com/akfamily/akshare/commit/fcdbf25aa864a218c54864c3f6ab6a2ed19cce28",
        "reviewed_at": "2026-07-20",
        "roles": ["endpoint_intelligence", "field_semantics", "candidate"],
        "contributions": "提供行情、复权、财务、指数成分、事件、基金和期权等公开端点与字段代码地图。",
        "runtime_dependency": False,
        "adoption_status": "rewrite_per_function_no_vendor",
        "evidence_level": "E3",
    },
    "mootdx": {
        "project_id": "mootdx",
        "name": "mootdx/mootdx",
        "repo_url": "https://github.com/mootdx/mootdx",
        "pinned_ref": None,
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["protocol_reference", "field_semantics"],
        "contributions": "提供 TDX/F10 协议与新浪复权因子累计语义的交叉情报。",
        "runtime_dependency": False,
        "adoption_status": "protocol_reference_only",
        "evidence_level": "E3",
    },
    "adata": {
        "project_id": "adata",
        "name": "1nchaos/adata",
        "repo_url": "https://github.com/1nchaos/adata",
        "pinned_ref": "b14f4e57",
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东方财富资金流、财务指标与指数成分字段情报。",
        "runtime_dependency": False,
        "adoption_status": "endpoint_field_reference",
        "evidence_level": "E3",
    },
    "finshare": {
        "project_id": "finshare",
        "name": "finvfamily/finshare",
        "repo_url": "https://github.com/finvfamily/finshare",
        "pinned_ref": "5038f8aa / 2.1.0",
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["engineering_mechanism"],
        "contributions": "只借鉴来源健康、冷却、陈旧缓存、部分响应与多源路由机制；不贡献独立数据池。",
        "runtime_dependency": False,
        "adoption_status": "mechanism_reference_only",
        "evidence_level": "E3",
    },
    "easy_tdx": {
        "project_id": "easy_tdx",
        "name": "handsomejustin/easy_tdx",
        "repo_url": "https://github.com/handsomejustin/easy_tdx",
        "pinned_ref": "513ee15c83ca14b81de1b2890c2369b6456bc864 / 1.20.6",
        "commit_url": "https://github.com/handsomejustin/easy_tdx/commit/513ee15c83ca14b81de1b2890c2369b6456bc864",
        "reviewed_at": "2026-08-06",
        "roles": ["protocol_reference", "engineering_mechanism"],
        "contributions": "提供 TDX host、协议与历史行情请求情报；是否作为运行时依赖由具体数据集条目决定。",
        "runtime_dependency": False,
        "adoption_status": "protocol_reference_by_default",
        "evidence_level": "E3",
    },
    "dean-stack-sector-flow": {
        "project_id": "dean-stack-sector-flow",
        "name": "dean-stack/a-share-sector-flow-visualizer",
        "repo_url": "https://github.com/dean-stack/a-share-sector-flow-visualizer",
        "pinned_ref": None,
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["endpoint_intelligence", "field_semantics", "local_fallback"],
        "contributions": "提供东方财富 clist/fflow 端点、板块分钟资金流序列及本地快照/回放方法。",
        "runtime_dependency": False,
        "adoption_status": "fund_flow_endpoint_reference",
        "evidence_level": "E3",
    },
    "flowlens": {
        "project_id": "flowlens",
        "name": "shenjing023/flowlens",
        "repo_url": "https://github.com/shenjing023/flowlens",
        "pinned_ref": None,
        "commit_url": None,
        "reviewed_at": "2026-07-19",
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东方财富 fflow/daykline 板块与概念日级资金流历史回补情报。",
        "runtime_dependency": False,
        "adoption_status": "fund_flow_history_reference",
        "evidence_level": "E3",
    },
    "free-stockdb": {
        "project_id": "free-stockdb",
        "name": "hello245m/free-stockdb",
        "repo_url": "https://github.com/hello245m/free-stockdb",
        "pinned_ref": "dd067ba",
        "commit_url": "https://github.com/hello245m/free-stockdb/commit/dd067bac589d5c204b5ab8b9882bbdb2d3941c6a",
        "reviewed_at": "2026-07-20",
        "roles": ["engineering_mechanism"],
        "contributions": "只借鉴 manifest、hash、原子下载和离线镜像机制；不采用不可追溯的 opaque 数据库。",
        "runtime_dependency": False,
        "adoption_status": "mechanism_only_no_opaque_data",
        "evidence_level": "E3",
    },
    "a-share-kline-puller": {
        "project_id": "a-share-kline-puller",
        "name": "Zealous1219/a-share-kline-puller",
        "repo_url": "https://github.com/Zealous1219/a-share-kline-puller",
        "pinned_ref": "92416f2",
        "commit_url": "https://github.com/Zealous1219/a-share-kline-puller/commit/92416f25e91782793807c9b3f43644886643770b",
        "reviewed_at": "2026-07-20",
        "roles": ["engineering_mechanism", "candidate"],
        "contributions": "只借鉴租约、进度、无数据审核队列和原子写入机制；排除 Wind/Windows 强耦合运行时。",
        "runtime_dependency": False,
        "adoption_status": "mechanism_candidate_only",
        "evidence_level": "E3",
    },
    "a-stock-data": {
        "project_id": "a-stock-data",
        "name": "simonlin1212/a-stock-data",
        "repo_url": "https://github.com/simonlin1212/a-stock-data",
        "pinned_ref": "9ed665c",
        "commit_url": None,
        "reviewed_at": "2026-07-30",
        "roles": ["endpoint_intelligence", "field_semantics", "candidate"],
        "contributions": "提供事件、研报、公告、热度与行情端点情报，目前仍是候选而非运行时依赖。",
        "runtime_dependency": False,
        "adoption_status": "candidate_intelligence_no_runtime",
        "evidence_level": "E3",
    },
    "astock-data-toolkit": {
        "project_id": "astock-data-toolkit",
        "name": "tiantianlaolao/astock-data-toolkit",
        "repo_url": "https://github.com/tiantianlaolao/astock-data-toolkit",
        "pinned_ref": "55b2004",
        "commit_url": None,
        "reviewed_at": "2026-07-30",
        "roles": ["endpoint_intelligence", "field_semantics", "candidate"],
        "contributions": "提供估值、公告、增减持、分红与公司行动字段/端点情报，目前仍是候选。",
        "runtime_dependency": False,
        "adoption_status": "candidate_intelligence_no_runtime",
        "evidence_level": "E3",
    },
    "efinance": {
        "project_id": "efinance",
        "name": "Micro-sheep/efinance",
        "repo_url": "https://github.com/Micro-sheep/efinance",
        "pinned_ref": None,
        "commit_url": None,
        "reviewed_at": "2026-07-20",
        "roles": ["endpoint_intelligence", "field_semantics", "candidate"],
        "contributions": "提供东方财富股东、龙虎榜、基金、债券、期货和快照 getter 情报，目前仍是候选。",
        "runtime_dependency": False,
        "adoption_status": "candidate_intelligence_no_runtime",
        "evidence_level": "E3",
    },
    "hithink-financial-api": {
        "project_id": "hithink-financial-api",
        "name": "HiThink-Tech/Financial-API",
        "repo_url": "https://github.com/HiThink-Tech/Financial-API",
        "pinned_ref": "9dbef74d",
        "commit_url": "https://github.com/HiThink-Tech/Financial-API/commit/9dbef74d2ce535857e610eec265bcb9302942d48",
        "reviewed_at": "2026-08-25",
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供同花顺官方 REST 契约、涨跌停池/龙虎榜/竞价/估值字段与错误码情报；one-trading 自有 Adapter 直接请求 fuyao.aicubes.cn，不 vendor CLI/DuckDB/MCP。",
        "runtime_dependency": False,
        "adoption_status": "official_source_intelligence_account_gated",
        "evidence_level": "E3",
    },
}


# Adapter 对照：这段本地 Adapter 当初对照谁写的。不是数据集父母，也不表示池子属于该仓库。
SUBJECT_REFERENCES: dict[str, tuple[str, ...]] = {
    "stock_instruments": ("tickflow-stock-panel",),
    "stock_daily": ("tickflow-stock-panel", "go-stock"),
    "stock_enriched": ("tickflow-stock-panel",),
    "stock_minute": ("easy_tdx", "tickflow-stock-panel"),
    "stock_adj_factor": ("akshare", "mootdx", "tickflow-stock-panel"),
    "etf_instruments": ("tickflow-stock-panel",),
    "etf_daily": ("tickflow-stock-panel",),
    "etf_enriched": ("tickflow-stock-panel",),
    "etf_minute": ("tickflow-stock-panel",),
    "etf_adj_factor": ("akshare", "mootdx"),
    "index_instruments": ("tickflow-stock-panel",),
    "index_daily": ("tickflow-stock-panel",),
    "index_enriched": ("tickflow-stock-panel",),
    "quote_snapshot": ("go-stock", "tickflow-stock-panel"),
    "sealed_l1": ("tickflow-stock-panel",),
    "depth5": ("tickflow-stock-panel",),
    "pools": ("tickflow-stock-panel", "akshare", "adata"),
    "trading_calendar": ("akshare", "a-stock-data"),
    "ext_data": ("tickflow-stock-panel",),
    "financial_metrics": ("akshare", "adata"),
    "financial_income": ("akshare",),
    "financial_balance_sheet": ("akshare",),
    "financial_cash_flow": ("akshare",),
    "financial_shares": ("akshare", "astock-data-toolkit"),
    "stock_margin_trading": ("go-stock",),
    "market_pulse": ("go-stock",),
    "valuation_daily": ("astock-data-toolkit",),
    "limit_up_events": ("a-stock-data",),
    "index_membership_history": ("akshare", "adata"),
    "corporate_actions": ("astock-data-toolkit", "akshare"),
    "hithink_limit_pool": ("hithink-financial-api",),
    "hithink_dragon_tiger": ("hithink-financial-api",),
    "hithink_auction_snapshot": ("hithink-financial-api",),
    "hithink_valuation_snapshot": ("hithink-financial-api",),
    "ext_fund_flow_bk": (),
    "ext_fund_flow_bk_daily": (),
    "ext_fund_flow_concept": (),
    "ext_fund_flow_concept_daily": (),
    "ext_fund_flow_stock": (),
    "ext_gn_ths": (),
    "ext_hy_ths": (),
}

SUBJECT_REFERENCE_OVERRIDES: dict[tuple[str, str], GithubReferenceData] = {
    ("stock_daily", "go-stock"): {
        "roles": ["endpoint_intelligence"],
        "contributions": (
            "提供腾讯/新浪公开快照参数，供当天 public_quote_eod 补丁对照；"
            "历史日 K Adapter 对照的是 tickflow-stock-panel，生产者仍是 TickFlow。"
        ),
    },
    ("quote_snapshot", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供腾讯主源、新浪兜底的公开行情参数；不是行情权利方。",
    },
    ("stock_minute", "easy_tdx"): {
        "contributions": "作为薄运行时 Adapter，按 symbol + YYYYMMDD 读取自选股单日 240 点历史分时；落库、日期门和日线对账由 one-trading 自有模块负责。真实生产者是公开 TDX 行情服务器。",
        "runtime_dependency": True,
        "adoption_status": "adopted_watchlist_on_demand",
    },
    ("ext_fund_flow_bk_daily", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东财 bkzj 请求参数与展示语义。行业窗口回补已强制 H5，不再用 go-stock stock.db 做主路径。",
    },
    ("ext_fund_flow_concept_daily", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东财概念资金流参数情报。概念窗口回补已强制 H5，不再用 go-stock stock.db 做主路径。",
    },
    ("ext_fund_flow_bk", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东财 bkzj 当日排行参数；空了再 push2 clist 的对照来自 dean-stack。",
    },
    ("ext_fund_flow_concept", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供东财概念当日排行参数情报。",
    },
    ("stock_margin_trading", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": (
            "提供东方财富融资融券 F10 请求参数、字段名称与展示语义；"
            "one-trading 自行实现 Adapter、质量门和 Parquet，不采用 go-stock 运行时或本地快照。"
        ),
    },
    ("market_pulse", "go-stock"): {
        "roles": ["endpoint_intelligence", "field_semantics", "engineering_mechanism"],
        "contributions": (
            "提供财联社指数分时、板块异动端点及时间轴叠加产品形态；"
            "one-trading 自行实现同日期质量门、Parquet、lineage、本地 API 与用户台组件，"
            "不采用 go-stock Runtime。"
        ),
    },
    ("hithink_limit_pool", "hithink-financial-api"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": (
            "提供官方涨跌停/炸板池字段与分页契约；"
            "one-trading 自行实现 Adapter、独立 Parquet 与 lineage，不覆盖 limit_up_events。"
        ),
    },
    ("hithink_dragon_tiger", "hithink-financial-api"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供官方龙虎榜字段契约；one-trading 自行落独立数据集。",
    },
    ("hithink_auction_snapshot", "hithink-financial-api"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供集合竞价快照契约，并明确 auction_volume 单位为手。",
    },
    ("hithink_valuation_snapshot", "hithink-financial-api"): {
        "roles": ["endpoint_intelligence", "field_semantics"],
        "contributions": "提供最新五项估值快照契约；不得冒充历史 valuation_daily。",
    },
    ("corporate_actions", "astock-data-toolkit"): {
        "contributions": (
            "提供分红送转/公司行动的字段与端点情报；"
            "one-trading 正式事实来自东方财富分红送转批量报表, 由自有 Adapter 采集并与复权因子双向核对。"
        ),
    },
    ("valuation_daily", "astock-data-toolkit"): {
        "contributions": (
            "提供历史日频估值的字段与口径情报；"
            "one-trading 当前估值由本地未复权日线 x 严格 PIT 股本派生, 不采用该仓库运行时。"
        ),
    },
}

REPLACEMENT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "stock_daily": ("akshare", "easy_tdx", "a-share-kline-puller"),
    "stock_minute": ("easy_tdx", "mootdx", "a-stock-data"),
    "stock_adj_factor": ("akshare", "mootdx"),
    "financial_metrics": ("adata", "efinance", "a-stock-data"),
    "financial_income": ("efinance", "a-stock-data"),
    "financial_balance_sheet": ("efinance", "a-stock-data"),
    "financial_cash_flow": ("efinance", "a-stock-data"),
    "quote_snapshot": ("go-stock", "akshare", "efinance"),
    "ext_data": ("a-stock-data", "astock-data-toolkit", "efinance"),
}

FUND_FLOW_REFERENCE_IDS = (
    "go-stock",
    "dean-stack-sector-flow",
    "flowlens",
    "adata",
)

FUND_FLOW_CANDIDATE_IDS = ("a-stock-data", "efinance", "free-stockdb")

GENERIC_ENGINEERING_REFERENCE_IDS = ("finshare", "free-stockdb", "a-share-kline-puller")


def github_reference(project_id: str) -> GithubReferenceData:
    return deepcopy(GITHUB_PROJECTS[project_id])


def references_for_subject(subject_id: str) -> list[GithubReferenceData]:
    project_ids = list(SUBJECT_REFERENCES.get(subject_id, ()))
    if subject_id.startswith("ext_fund_flow"):
        project_ids = list(dict.fromkeys([*project_ids, *FUND_FLOW_REFERENCE_IDS]))
    elif subject_id.startswith("ext_"):
        project_ids = list(dict.fromkeys([*project_ids, "tickflow-stock-panel", "go-stock"]))
    references: list[GithubReferenceData] = []
    for project_id in project_ids:
        reference = github_reference(project_id)
        reference.update(deepcopy(SUBJECT_REFERENCE_OVERRIDES.get((subject_id, project_id), {})))
        references.append(reference)
    return references


def replacement_candidates_for_subject(subject_id: str) -> list[GithubReferenceData]:
    project_ids = list(REPLACEMENT_CANDIDATES.get(subject_id, ()))
    if subject_id.startswith("ext_fund_flow"):
        project_ids = list(dict.fromkeys([*project_ids, *FUND_FLOW_CANDIDATE_IDS]))
    elif subject_id.startswith("ext_"):
        project_ids = list(dict.fromkeys([*project_ids, "a-stock-data", "efinance"]))
    return [github_reference(project_id) for project_id in project_ids]


def producer_for_id(producer_id: str) -> ProducerData:
    return deepcopy(PRODUCERS.get(producer_id, PRODUCERS["local"]))


def producer_id_for_lineage_source(source: str) -> str:
    lowered = source.strip().lower()
    if "tdx_public" in lowered:
        return "tdx_public"
    if "tickflow" in lowered:
        return "tickflow"
    if "go_stock" in lowered:
        return "go_stock_snapshot"
    if "public_quote" in lowered:
        return "public_quote"
    # 本地派生数据集的 lineage source(reference_derived / corporate_actions 闭环)
    if any(
        token in lowered
        for token in (
            "raw_daily_x_pit_safe_shares",
            "raw_daily_board_rules",
            "pools_snapshot_seed",
            "corporate_actions_v2",
        )
    ):
        return "derived_local"
    if any(token in lowered for token in ("eastmoney", "em_", "fund_flow", "financial-pit")):
        return "eastmoney"
    if "sina" in lowered:
        return "sina"
    if "tencent" in lowered:
        return "tencent"
    if "cninfo" in lowered:
        return "cninfo"
    if any(token in lowered for token in ("sse", "szse", "exchange", "calendar")):
        return "exchange_calendar"
    if "csindex" in lowered:
        return "csindex"
    if lowered == "public":
        return "public"
    return lowered or "local"


def producer_id_for_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    lowered = host.lower()
    if "eastmoney" in lowered or "eastmoney" in url.lower():
        return "eastmoney"
    if "sina" in lowered:
        return "sina"
    if "qq.com" in lowered or "tencent" in lowered:
        return "tencent"
    if "cninfo" in lowered:
        return "cninfo"
    if "files.688798.xyz" in lowered:
        return "tickflow_extension_files"
    return "custom_http"


def producer_ids_for_subject(subject_id: str, provider: str | None = None) -> list[str]:
    if subject_id.startswith("ext_fund_flow"):
        return ["eastmoney"]
    if subject_id in {"ext_gn_ths", "ext_hy_ths"}:
        return ["tickflow_extension_files"]
    declared = DECLARED_PRODUCERS_BY_SUBJECT.get(subject_id)
    if declared:
        return list(declared)
    if provider == "tickflow":
        return ["tickflow"]
    return []


def adapter_paths_for_subject(subject_id: str) -> list[str]:
    paths: list[str] = []
    if subject_id in {"stock_daily", "stock_enriched", "etf_daily", "etf_enriched", "index_daily", "index_enriched"}:
        paths.append("backend/app/services/kline_sync.py")
    if subject_id.endswith("_instruments"):
        paths.append("backend/app/services/instrument_sync.py")
    if subject_id.endswith("_adj_factor"):
        paths.append("backend/app/services/free_sources/adj_factor_public.py")
    if subject_id == "stock_minute" or subject_id == "etf_minute":
        paths.append("backend/app/services/free_sources/intraday_public.py")
    if subject_id == "stock_minute":
        paths.append("backend/app/services/free_sources/tdx_history_minute.py")
    if subject_id == "quote_snapshot":
        paths.extend(
            [
                "backend/app/services/quote_service.py",
                "backend/app/services/free_sources/quote_fallback.py",
            ]
        )
    if subject_id in {"sealed_l1", "depth5"}:
        paths.append("backend/app/services/depth_service.py")
    if subject_id == "pools":
        paths.append("backend/app/services/free_sources/pools_public.py")
    if subject_id.startswith("financial_"):
        paths.extend(
            [
                "backend/app/services/financial_sync.py",
                "backend/app/services/free_sources/financials_public.py",
            ]
        )
    if subject_id == "financial_shares":
        paths.append("backend/app/services/free_sources/share_capital_public.py")
    if subject_id in {"valuation_daily", "limit_up_events", "index_membership_history"}:
        paths.append("backend/app/services/reference_derived.py")
    if subject_id == "valuation_daily":
        paths.append("backend/app/services/financial_pit.py")
    if subject_id == "limit_up_events":
        paths.append("backend/app/price_limits.py")
    if subject_id == "corporate_actions":
        paths.extend(
            [
                "backend/app/services/corporate_actions_sync.py",
                "backend/app/services/free_sources/adj_factor_public.py",
            ]
        )
    if subject_id == "stock_margin_trading":
        paths.extend(
            [
                "backend/app/services/free_sources/margin_trading_public.py",
                "backend/app/api/stock_f10.py",
            ]
        )
    if subject_id == "market_pulse":
        paths.extend(
            [
                "backend/app/services/free_sources/market_pulse_public.py",
                "backend/app/api/market_pulse.py",
            ]
        )
    if subject_id in {
        "hithink_limit_pool",
        "hithink_dragon_tiger",
        "hithink_auction_snapshot",
        "hithink_valuation_snapshot",
    }:
        paths.extend(
            [
                "backend/app/services/free_sources/hithink_finance.py",
                "backend/app/api/hithink.py",
            ]
        )
    if subject_id == "ext_data" or subject_id.startswith("ext_"):
        paths.extend(
            [
                "backend/app/services/ext_data.py",
                "backend/app/api/ext_data.py",
            ]
        )
    if subject_id.startswith("ext_fund_flow"):
        paths.append("backend/app/services/free_sources/fund_flow.py")
    if subject_id == "trading_calendar":
        paths.append("backend/app/data_lab/sources/calendar_probe.py")
    return list(dict.fromkeys(paths))


def known_project_ids() -> Iterable[str]:
    return GITHUB_PROJECTS.keys()
